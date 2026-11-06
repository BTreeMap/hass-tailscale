"""Minimal mock of the Home Assistant Supervisor API for bashio, keyed by token.

Usage: mock_supervisor.py <port> <nodes dir> <log file>

Each add-on container sets SUPERVISOR_TOKEN=<node name>; its hostname, IP and
options come from <nodes dir>/<node>.json and are re-read on every request. Unknown paths are logged and answered with empty data.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

NODES = (
    Path(sys.argv[2])
    if len(sys.argv) > 2
    else Path(__file__).resolve().parent / "nodes"
)
LOG = Path(sys.argv[3]) if len(sys.argv) > 3 else NODES / "supervisor-requests.log"


def node_cfg(token: str) -> dict:
    return json.loads((NODES / f"{token}.json").read_text())


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, data, code=200):
        body = json.dumps({"result": "ok", "data": data}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_any(self):
        token = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        path = self.path.split("?")[0]
        with LOG.open("a") as f:
            f.write(f"{token} {self.command} {path}\n")
        try:
            cfg = node_cfg(token)
        except FileNotFoundError:
            return self.reply({}, 401)
        ip = cfg["ip"]
        if path == "/addons/self/options/config":
            return self.reply(cfg["options"])
        if path == "/addons/self/info":
            return self.reply(
                {
                    "name": "Tailscale",
                    "slug": "tailscale",
                    "version": "1.0.18",
                    "network": {"41641/udp": cfg.get("udp_port", 41641)},
                    "ip_address": ip,
                    "ingress_port": 8099,
                    "ingress_entry": "/api/hassio_ingress/x",
                    "options": cfg["options"],
                }
            )
        if path == "/info":
            return self.reply({"hostname": cfg["hostname"], "arch": "amd64"})
        if path == "/core/info":
            return self.reply({"port": 8123, "ssl": False, "version": "2026.11.0"})
        if path in ("/network/info",):
            return self.reply(
                {
                    "interfaces": [
                        {
                            "interface": "eth0",
                            "primary": True,
                            "ipv4": {
                                "address": [f"{ip}/24"],
                                "gateway": ip.rsplit(".", 1)[0] + ".1",
                            },
                            "ipv6": {"address": []},
                        }
                    ]
                }
            )
        if path == "/network/interface/default/info":
            return self.reply(
                {
                    "interface": "eth0",
                    "primary": True,
                    "ipv4": {
                        "address": [f"{ip}/24"],
                        "gateway": ip.rsplit(".", 1)[0] + ".1",
                    },
                    "ipv6": {"address": []},
                }
            )
        if path.startswith("/network/interface/") and path.endswith("/info"):
            return self.reply(
                {
                    "interface": "eth0",
                    "ipv4": {"address": [f"{ip}/24"]},
                    "ipv6": {"address": []},
                }
            )
        return self.reply({})

    do_GET = do_POST = do_PUT = do_DELETE = handle_any


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(sys.argv[1])), H).serve_forever()
