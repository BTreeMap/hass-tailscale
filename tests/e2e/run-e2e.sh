#!/usr/bin/env bash
# End-to-end test for the hass-tailscale add-on image.
#
# Runs the real image (s6 + bashio + tailscaled) against a local headscale
# control server and a mock Home Assistant Supervisor API, then checks every
# feature the add-on scripts use. Needs: docker (daemon running), go, jq, curl,
# python3, and network access to pkgs.tailscale.com, Alpine mirrors and ghcr.io.
#
# Usage:
#   tests/e2e/run-e2e.sh [path/to/hass-tailscale]   (default: this checkout)
# Environment:
#   NEW_IMAGE      image under test; built from the repo if unset
#   OLD_IMAGE      released image for the upgrade/rollback test
#                  (default ghcr.io/btreemap/tailscale/amd64:<version on origin main's last tag>)
#   HEADSCALE_VERSION  default v0.29.7
#   EXTRA_CA       PEM file to trust inside the build (for TLS-intercepting proxies)
#   KEEP=1         leave containers, network and headscale running afterwards
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "${1:-$HERE/../..}" && pwd)"
WORK="${WORK:-$HERE/work}"  # git-ignored
NET=hst-e2e
SUBNET=172.31.250.0
GW=172.31.250.1
HEADSCALE_VERSION="${HEADSCALE_VERSION:-v0.29.7}"
PREFIX=hst-e2e
PASS=0
FAIL=0
declare -a RESULTS=()

log() { printf '\n== %s\n' "$*"; }
check() { # check "<name>" <command...>
  local name=$1; shift
  if "$@" >>"$WORK/checks.log" 2>&1; then
    RESULTS+=("PASS  $name"); PASS=$((PASS + 1))
  else
    RESULTS+=("FAIL  $name"); FAIL=$((FAIL + 1))
  fi
}
dx() { docker exec "$PREFIX-$1" "${@:2}"; }
strip() { sed 's/\x1b\[[0-9;]*m//g'; }

cleanup() {
  [[ "${KEEP:-0}" == 1 ]] && { echo "KEEP=1: leaving environment up (work dir $WORK)"; return; }
  docker ps -aq --filter "name=^$PREFIX-" | xargs -r docker rm -f >/dev/null 2>&1
  docker network rm "$NET" >/dev/null 2>&1
  [[ -n "${HS_PID:-}" ]] && kill "$HS_PID" 2>/dev/null
  [[ -n "${SUP_PID:-}" ]] && kill "$SUP_PID" 2>/dev/null
}
trap cleanup EXIT

rm -rf "$WORK" && mkdir -p "$WORK"/{hs,nodes,vol,bin}
: >"$WORK/checks.log"

# ---------------------------------------------------------------- images
VERSION_IN_REPO=$(sed -nE 's/^version:[[:space:]]*([^[:space:]#]+).*/\1/p' "$REPO/tailscale/config.yaml")
TS_PIN=$(sed -nE 's/^ARG TAILSCALE_VERSION="([^"]+)"/\1/p' "$REPO/tailscale/Dockerfile")
log "repo $REPO: add-on $VERSION_IN_REPO, Tailscale pin $TS_PIN"

if [[ -z "${NEW_IMAGE:-}" ]]; then
  NEW_IMAGE="hass-tailscale-e2e:$VERSION_IN_REPO"
  ctx="$WORK/ctx"; cp -r "$REPO/tailscale" "$ctx"
  if [[ -n "${EXTRA_CA:-}" ]]; then
    # Test-only: trust a TLS-intercepting proxy during apk/curl. The shipped
    # Dockerfile is not modified.
    cp "$EXTRA_CA" "$ctx/extra-ca.crt"
    python3 - "$ctx/Dockerfile" <<'PY'
import sys
p = sys.argv[1]; s = open(p).read()
s = s.replace("# Setup base\n", "COPY extra-ca.crt /tmp/extra-ca.crt\nRUN cat /tmp/extra-ca.crt >> /etc/ssl/certs/ca-certificates.crt\n# Setup base\n", 1)
open(p, "w").write(s)
PY
  fi
  log "building $NEW_IMAGE"
  docker build --network host \
    --build-arg HTTPS_PROXY="${HTTPS_PROXY:-}" --build-arg https_proxy="${HTTPS_PROXY:-}" \
    --build-arg BUILD_ARCH=amd64 --build-arg BUILD_VERSION="$VERSION_IN_REPO" \
    -t "$NEW_IMAGE" "$ctx" >"$WORK/build.log" 2>&1 || { echo "build failed, see $WORK/build.log"; exit 1; }
fi
check "image runs pinned Tailscale $TS_PIN" \
  bash -c "docker run --rm --entrypoint /opt/tailscale '$NEW_IMAGE' version | head -1 | grep -qx '$TS_PIN'"

if [[ -z "${OLD_IMAGE:-}" ]]; then
  last_tag=$(git -C "$REPO" ls-remote --tags origin 2>/dev/null | sed -nE 's#.*refs/tags/v([0-9.]+)$#\1#p' | sort -V | tail -1)
  OLD_IMAGE="ghcr.io/btreemap/tailscale/amd64:${last_tag:-1.0.18}"
fi
log "old (released) image: $OLD_IMAGE"
docker pull -q "$OLD_IMAGE" >/dev/null || { echo "cannot pull $OLD_IMAGE"; exit 1; }

# ---------------------------------------------------------------- headscale
log "building headscale $HEADSCALE_VERSION"
GOBIN="$WORK/bin" go install "github.com/juanfont/headscale/cmd/headscale@$HEADSCALE_VERSION" >"$WORK/hs-build.log" 2>&1 \
  || { echo "headscale build failed, see $WORK/hs-build.log"; exit 1; }
HS=("$WORK/bin/headscale" -c "$WORK/hs/config.yaml")
sed -e "s#@WORK@#$WORK#g" -e "s#@GW@#$GW#g" "$HERE/headscale.yaml.tmpl" >"$WORK/hs/config.yaml"
sed -e "s#@SUBNET@#$SUBNET#g" "$HERE/acl.hujson" >"$WORK/hs/acl.hujson"

docker network create --subnet "$SUBNET/24" --gateway "$GW" "$NET" >/dev/null
"${HS[@]}" serve >"$WORK/headscale.log" 2>&1 & HS_PID=$!
python3 -I "$HERE/mock_supervisor.py" 18099 "$WORK/nodes" "$WORK/supervisor.log" & SUP_PID=$!
for _ in $(seq 30); do curl -sf --noproxy '*' "http://$GW:8080/health" >/dev/null && break; sleep 1; done
"${HS[@]}" users create test >/dev/null

# ---------------------------------------------------------------- nodes
# node <name> <ip> <options-json-patch (jq)>
mknode() {
  python3 - "$REPO/tailscale/config.yaml" "$WORK/nodes/$1.json" "$1" "$2" "$3" <<'PY'
import json, subprocess, sys, yaml
cfg, out, name, ip, patch = sys.argv[1:]
opts = yaml.safe_load(open(cfg))["options"]
opts = json.loads(subprocess.run(["jq", "-c", patch], input=json.dumps(opts), capture_output=True, text=True, check=True).stdout)
json.dump({"hostname": f"ha-{name}", "ip": ip, "options": opts}, open(out, "w"), indent=1)
PY
}
run() { # run <name> <ip> <image>  (fresh container each time, like Supervisor)
  local n=$1 ip=$2 img=$3 v="$WORK/vol/$1"
  docker rm -f "$PREFIX-$n" >/dev/null 2>&1
  for d in data share media backup ssl config addons addon_configs; do mkdir -p "$v/$d"; done
  [[ -f "$v/share/hello.txt" ]] || echo "hello from $n" >"$v/share/hello.txt"
  docker run -d --name "$PREFIX-$n" --hostname "$n" --network "$NET" --ip "$ip" \
    --cap-add NET_ADMIN --cap-add NET_RAW --device /dev/net/tun \
    --add-host "supervisor:$GW" -e SUPERVISOR_API="http://supervisor:18099" -e SUPERVISOR_TOKEN="$n" \
    -e TS_DEBUG_USE_DERP_HTTP=1 -e NO_PROXY='*' -e no_proxy='*' \
    -v "$v/data:/data" -v "$v/share:/share" -v "$v/media:/media" -v "$v/backup:/backup" \
    -v "$v/ssl:/ssl" -v "$v/addons:/addons" -v "$v/addon_configs:/addon_configs" -v "$v/config:/config" \
    "$img" >/dev/null
}
register() { # approve the interactive login printed by `tailscale up`
  local k=""
  for _ in $(seq 60); do
    k=$(docker logs "$PREFIX-$1" 2>&1 | grep -oE 'hskey-authreq-[A-Za-z0-9_-]{24}' | tail -1)
    [[ -n "$k" ]] && break; sleep 1
  done
  "${HS[@]}" auth register --auth-id "$k" --user test >/dev/null
}
wait_running() {
  for _ in $(seq 90); do
    [[ "$(dx "$1" /opt/tailscale status --json --self --peers=false 2>/dev/null | jq -r .BackendState)" == Running ]] && return 0
    sleep 1
  done
  return 1
}
logs() { docker logs "$PREFIX-$1" 2>&1 | strip; }
state() { docker inspect -f '{{.State.Status}}' "$PREFIX-$1"; }
wait_log() { for _ in $(seq 60); do logs "$1" | grep -qE "$2" && return 0; sleep 1; done; return 1; }

IP_A=172.31.250.11; IP_B=172.31.250.12; IP_C=172.31.250.13
# A: defaults (userspace networking, exit node, app connector, local_subnets),
#    plus Taildrive and Serve with Digital Asset Links.
mknode a $IP_A '.login_server="http://'$GW':8080" | .log_level="debug" | .taildrive.share=true | .taildrive.media=true'
# B: kernel networking (tailscale0, forwarding, MSS clamping, UDP GRO).
mknode b $IP_B '.login_server="http://'$GW':8080" | .log_level="debug" | .userspace_networking=false | .advertise_exit_node=false | .advertise_connector=false'
# C: upgrade/rollback between the released image and the new one.
mknode c $IP_C '.login_server="http://'$GW':8080" | .taildrive.share=true'

log "node A (userspace)"
run a $IP_A "$NEW_IMAGE"; register a; check "A: login via interactive auth URL and reaches Running" wait_running a
check "A: Taildrive shares configured" wait_log a 'Taildrive: (sharing|/share is already shared)'
check "A: container still running after startup" bash -c "sleep 5; [[ \$(docker inspect -f '{{.State.Status}}' $PREFIX-a) == running ]]"

log "node B (kernel networking)"
run b $IP_B "$NEW_IMAGE"; register b; check "B: reaches Running" wait_running b
check "B: UDP GRO forwarding tuned via localapi check" wait_log b 'Enabling UDP GRO for forwarding'
check "B: MSS clamping applied" wait_log b 'Clamping the MSS to the MTU for interface tailscale0'
check "B: tailnet->host forwarding applied" wait_log b 'Forwarding incoming tailnet connections'

TS_A=$(dx a /opt/tailscale ip -4); TS_B=$(dx b /opt/tailscale ip -4)
check "advertised routes reach control (exit node + local subnet)" \
  bash -c "'${HS[0]}' -c '$WORK/hs/config.yaml' nodes list-routes | sed 's/\x1b\[[0-9;]*m//g' | grep -q '$SUBNET/24' && '${HS[0]}' -c '$WORK/hs/config.yaml' nodes list-routes | grep -q '0.0.0.0/0'"
check "B -> A: tailscale ping direct path" bash -c "docker exec $PREFIX-b /opt/tailscale ping -c 3 $TS_A | grep -q pong"
check "B -> A: ICMP over tailscale0" dx b ping -c 2 -W 3 "$TS_A"
check "B -> A: Taildrive read" bash -c "docker exec $PREFIX-b curl -sf http://100.100.100.100:8080/$GW/ha-a/share/hello.txt | grep -qx 'hello from a'"
check "B -> A: Taildrive write" bash -c "docker exec $PREFIX-b sh -c 'echo wdav > /tmp/w && curl -sf -T /tmp/w http://100.100.100.100:8080/$GW/ha-a/share/written-by-b.txt' && grep -qx wdav '$WORK/vol/a/share/written-by-b.txt'"
check "B -> A: Taildrop lands in /share/taildrop" bash -c "docker exec $PREFIX-b sh -c 'echo drop > /tmp/drop.txt && /opt/tailscale file cp /tmp/drop.txt ha-a:' && for i in \$(seq 15); do [[ -f '$WORK/vol/a/share/taildrop/drop.txt' ]] && exit 0; sleep 1; done; exit 1"
dnat_probe() { # listener bound only to B's host address; A dials B's tailnet IP
  local i
  for i in 1 2 3 4 5; do
    docker exec "$PREFIX-b" sh -c "pkill -f 'nc -l -s' ; rm -f /tmp/recv.txt"
    docker exec -d "$PREFIX-b" sh -c "nc -l -s $IP_B -p 9998 > /tmp/recv.txt"; sleep 1
    docker exec "$PREFIX-a" sh -c "echo through-dnat | timeout 5 /opt/tailscale nc $TS_B 9998"
    sleep 1
    docker exec "$PREFIX-b" cat /tmp/recv.txt | grep -qx through-dnat && { echo "ok on try $i"; return 0; }
    echo "try $i: nothing received"; sleep 2
  done
  return 1
}
check "A -> B: tailnet IP DNAT to host address" dnat_probe

for n in a b; do
  ip_var="IP_${n^^}"; ipx=${!ip_var}
  check "$n: ingress nginx -> tailscale web (from Supervisor IP)" bash -c \
    "docker exec $PREFIX-$n sh -c 'ip addr add 172.30.32.2/32 dev lo 2>/dev/null; curl -sf --interface 172.30.32.2 http://$ipx:8099/ | grep -q \"<title>Tailscale\"'"
  check "$n: ingress refuses other sources (403)" bash -c \
    "[[ \$(docker exec $PREFIX-$n curl -s -o /dev/null -w '%{http_code}' http://$ipx:8099/) == 403 ]]"
  check "$n: healthcheck script exits 0" dx "$n" healthcheck
done

log "Serve: run the add-on's share-homeassistant script for real"
dx a sh -c 'mkdir -p /tmp/ha && echo "<html>fake-ha</html>" > /tmp/ha/index.html && printf "%s\n" "pid /tmp/ha.pid; error_log /tmp/ha.err; events {} http { access_log /tmp/ha.acc; server { listen 127.0.0.1:8123; root /tmp/ha; } }" > /tmp/ha.conf && nginx -c /tmp/ha.conf'
jq '.options.share_homeassistant="serve" | .options.digital_asset_links_sites=["https://example.com","https://example.org"]' \
  "$WORK/nodes/a.json" >"$WORK/nodes/a.json.new" && mv "$WORK/nodes/a.json.new" "$WORK/nodes/a.json"
dx a rm -rf /tmp/.bashio
# with-contenv drops docker-exec env, so the script ends in `tail -f`; stop it once ServeConfig is applied.
dx a sh -c 'exec 3>/dev/null; timeout 60 /command/with-contenv bashio /etc/s6-overlay/s6-rc.d/share-homeassistant/run' >"$WORK/serve-run.log" 2>&1
check "Serve: script applied ServeConfig via set-raw" grep -q 'ServeConfig applied successfully' "$WORK/serve-run.log"
check "Serve: tailscaled holds proxy + /.well-known/ path handlers" bash -c \
  "docker exec $PREFIX-a /opt/tailscale serve status --json | jq -e '.TCP[\"443\"].HTTPS and (.Web|to_entries[0].value.Handlers[\"/\"].Proxy==\"http://127.0.0.1:8123\") and (.Web|to_entries[0].value.Handlers[\"/.well-known/\"].Path|endswith(\"/.well-known\"))'"
# headscale cannot issue Tailscale HTTPS certs, so exercise the same handlers on plain HTTP :80.
dx a sh -c '/opt/tailscale serve status --json | jq "(.Web|keys[0]|sub(\":443$\";\":80\")) as \$h | .TCP={\"80\":{\"HTTP\":true}} | .Web={(\$h): (.Web|to_entries[0].value)} | .AllowFunnel={}" | /opt/tailscale serve set-raw'
HOSTHDR=$(dx a /opt/tailscale status --json --self --peers=false | jq -r '.Self.DNSName|rtrimstr(".")')
check "Serve: B gets Home Assistant through the proxy handler" bash -c "docker exec $PREFIX-b curl -sf -m 5 -H 'Host: $HOSTHDR' http://$TS_A/ | grep -q fake-ha"
check "Serve: B gets assetlinks.json through the path handler" bash -c \
  "docker exec $PREFIX-b curl -sf -m 5 -H 'Host: $HOSTHDR' http://$TS_A/.well-known/assetlinks.json | jq -e 'map(.target.site)==[\"https://example.com\",\"https://example.org\"]'"
dx a /opt/tailscale serve reset >/dev/null

log "graceful stop (finish scripts)"
t0=$(date +%s); docker stop -t 30 "$PREFIX-b" >/dev/null; t1=$(date +%s)
check "B: stops within 10s ($((t1 - t0))s)" test $((t1 - t0)) -le 10
check "B: forwarding and MSS rules removed on stop" bash -c \
  "docker logs $PREFIX-b 2>&1 | grep -q 'Removing the forwarding' && docker logs $PREFIX-b 2>&1 | grep -q 'Removing the MSS clamping'"

log "node C: upgrade from released image, roll back, upgrade again"
run c $IP_C "$OLD_IMAGE"; register c; wait_running c
ID0=$(dx c /opt/tailscale status --json --self --peers=false | jq -r '[.Self.ID,.Self.TailscaleIPs[0]]|join(" ")')
for step in new:"$NEW_IMAGE" rollback:"$OLD_IMAGE" new-again:"$NEW_IMAGE"; do
  docker stop -t 30 "$PREFIX-c" >/dev/null; run c $IP_C "${step#*:}"
  check "C ${step%%:*}: Running with same node identity, no re-login" bash -c \
    "for i in \$(seq 60); do s=\$(docker exec $PREFIX-c /opt/tailscale status --json --self --peers=false 2>/dev/null | jq -r '[.Self.ID,.Self.TailscaleIPs[0]]|join(\" \")'); [[ \$s == '$ID0' ]] && ! docker logs $PREFIX-c 2>&1 | grep -q 'To authenticate' && exit 0; sleep 1; done; exit 1"
  check "C ${step%%:*}: Taildrive share restored" wait_log c 'Taildrive: (sharing|/share is already shared)'
done

# ---------------------------------------------------------------- report
for n in a b c; do logs "$n" >"$WORK/node-$n.log" 2>/dev/null; done
log "results ($NEW_IMAGE vs $OLD_IMAGE)"
printf '%s\n' "${RESULTS[@]}"
printf '\n%d passed, %d failed. Logs: %s\n' "$PASS" "$FAIL" "$WORK"
[[ $FAIL -eq 0 ]]
