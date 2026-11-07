# hass-tailscale end-to-end harness

Runs the add-on image for real (s6, bashio, tailscaled, nginx) against a local
headscale control server and a mock Supervisor API, then checks the features
the add-on scripts depend on. It was written to validate Tailscale bumps, where
the unit tests (which stub `tailscale`) cannot catch changes in the binary.

## Requirements

Linux host with a running Docker daemon, `/dev/net/tun`, Go, jq, curl,
python3 with PyYAML. Network access to pkgs.tailscale.com, the Alpine mirrors,
ghcr.io and the Go module proxy (headscale is built from source with
`go install`).

## Usage

```sh
tests/e2e/run-e2e.sh            # tests this checkout
tests/e2e/run-e2e.sh /other/checkout
```

The script builds the image from the repo (amd64), pulls the last released
image from GHCR for the upgrade test, starts headscale on a private Docker
network, runs three add-on containers and prints a PASS/FAIL table. Exit code
is non-zero if any check fails. Logs and per-node output go to `tests/e2e/work/`, which is git-ignored.

Environment variables:

- `NEW_IMAGE`: test an existing image instead of building one.
- `OLD_IMAGE`: released image for the upgrade/rollback test (default: the
  newest `v*` tag on the repo's origin).
- `EXTRA_CA`: PEM file to trust during the image build, for TLS-intercepting
  proxies. Only the build context copy of the Dockerfile is changed.
- `HEADSCALE_VERSION`: default `v0.29.7`.
- `KEEP=1`: leave everything running for manual poking.

## What it covers

Node A uses the default options (userspace networking, exit node, app
connector, `local_subnets`) plus Taildrive and Serve. Node B uses kernel
networking. Node C goes released image, new image, released image, new image
on the same `/data`.

- Interactive login through `tailscale up`, approved in headscale.
- Advertised exit node and local subnet reach the control server.
- Direct path between nodes; ICMP over `tailscale0`.
- Taildrive: shares configured by the add-on, read and write from a peer.
- Taildrop: `tailscale file cp` lands in `/share/taildrop`.
- Kernel mode: UDP GRO tuning (via the localapi check), MSS clamping, DNAT of
  the tailnet IP to the host address, and rule removal on stop.
- Ingress nginx to `tailscale web` from the Supervisor address, 403 otherwise.
- `healthcheck` script.
- The add-on's own `share-homeassistant/run` script: ServeConfig applied with
  `serve set-raw`, then the same proxy and `/.well-known/` handlers fetched by
  a peer.
- Graceful stop time and finish scripts.
- Upgrade and rollback keep node identity without a new login.

## Known gaps

- headscale cannot issue Tailscale HTTPS certificates, so Serve is exercised
  on plain HTTP port 80 with the same handlers. The HTTPS listener config is
  only checked as stored config.
- headscale rejects the `funnel` node attribute, so Funnel is not covered.
- amd64 only. The aarch64 image is not run.
- The mock Supervisor answers only the endpoints the add-on uses; it does not
  model ingress tokens or Supervisor restarts.
