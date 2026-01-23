import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_SCRIPT = REPO_ROOT / "tailscale/rootfs/etc/s6-overlay/s6-rc.d/share-homeassistant/run"
FIXTURES = REPO_ROOT / "tests/fixtures"


def write_config(tmp_path, *, share_mode="serve", sites=None, share_port=443):
    if sites is None:
        sites = []
    config = {
        "share_homeassistant": share_mode,
        "share_on_port": share_port,
        "digital_asset_links_sites": sites,
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path


def run_share(tmp_path, config_path, *, status_json=None, extra_env=None, capture_serve_config=False):
    env = os.environ.copy()
    bashio_dir = tmp_path / "bashio"
    if not bashio_dir.exists():
        subprocess.run(
            ["git", "clone", "--depth", "1", "https://github.com/hassio-addons/bashio", str(bashio_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
    if status_json is None:
        status_json = json.dumps({"Self": {"CapMap": {"https": True, "funnel": True}, "DNSName": "test-device.tailnet.ts.net."}})
    data_root = tmp_path / "data"
    serve_config_path = tmp_path / "serve_config.json" if capture_serve_config else None
    env.update(
        {
            "PATH": f"{FIXTURES}:{env['PATH']}",
            "BASH_ENV": str(FIXTURES / "bashio_env.sh"),
            "BASHIO_DIR": str(bashio_dir),
            "BASHIO_CONFIG_JSON": str(config_path),
            "TAILSCALE_BIN": str(FIXTURES / "tailscale_stub.sh"),
            "TAILSCALE_LOG": str(tmp_path / "tailscale.log"),
            "DATA_DIR": str(data_root),
            "SHARE_HOMEASSISTANT_TEST_MODE": "1",
        }
    )
    if serve_config_path:
        env["TAILSCALE_SERVE_CONFIG_OUT"] = str(serve_config_path)
    if status_json is not None:
        env["TAILSCALE_STATUS_JSON"] = status_json
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        ["bash", "-c", f"exec 3>/dev/null; bash {RUN_SCRIPT}"],
        env=env,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    return result, data_root, serve_config_path


def share_commands(log_path):
    """Extract tailscale commands from the log file.

    Returns a list of command tuples (e.g., ['serve', 'set-raw'] for set-raw,
    or ['serve'] for regular serve commands).
    """
    log_lines = log_path.read_text().splitlines()
    commands = []
    for line in log_lines:
        parts = line.split()
        if len(parts) > 1:
            cmd = parts[1]
            if cmd in ("serve", "funnel"):
                # Check if this is a set-raw command
                if len(parts) > 2 and parts[2] == "set-raw":
                    commands.append((cmd, "set-raw"))
                else:
                    commands.append((cmd,))
    return commands


def test_accepts_http_origin_with_warning(tmp_path):
    config_path = write_config(tmp_path, sites=["http://example.com"])
    result, data_root, _ = run_share(tmp_path, config_path)
    assert result.returncode == 0
    assetlinks_path = data_root / "digital-asset-links/www/.well-known/assetlinks.json"
    assert assetlinks_path.exists()
    data = json.loads(assetlinks_path.read_text())
    assert data[0]["target"]["site"] == "http://example.com"


def test_accepts_origin_with_path(tmp_path):
    config_path = write_config(tmp_path, sites=["https://example.com/path"])
    result, data_root, _ = run_share(tmp_path, config_path)
    assert result.returncode == 0
    assetlinks_path = data_root / "digital-asset-links/www/.well-known/assetlinks.json"
    assert assetlinks_path.exists()
    data = json.loads(assetlinks_path.read_text())
    assert data[0]["target"]["site"] == "https://example.com/path"


def test_accepts_port_out_of_range(tmp_path):
    config_path = write_config(tmp_path, sites=["https://example.com:65536"])
    result, data_root, _ = run_share(tmp_path, config_path)
    assert result.returncode == 0
    assetlinks_path = data_root / "digital-asset-links/www/.well-known/assetlinks.json"
    assert assetlinks_path.exists()
    data = json.loads(assetlinks_path.read_text())
    assert data[0]["target"]["site"] == "https://example.com:65536"


def test_accepts_valid_port_and_writes_assetlinks(tmp_path):
    config_path = write_config(tmp_path, sites=["https://example.com:444"])
    result, data_root, _ = run_share(tmp_path, config_path)
    assert result.returncode == 0
    assetlinks_path = data_root / "digital-asset-links/www/.well-known/assetlinks.json"
    assert assetlinks_path.exists()
    data = json.loads(assetlinks_path.read_text())
    assert data[0]["target"]["site"] == "https://example.com:444"


def test_deduplicates_and_sorts_sites(tmp_path):
    config_path = write_config(
        tmp_path,
        sites=["https://b.example.com", "https://a.example.com", "https://b.example.com"],
    )
    result, data_root, _ = run_share(tmp_path, config_path)
    assert result.returncode == 0
    data = json.loads(
        (data_root / "digital-asset-links/www/.well-known/assetlinks.json").read_text()
    )
    sites = [entry["target"]["site"] for entry in data]
    assert sites == ["https://a.example.com", "https://b.example.com"]


def test_share_mode_matches_dal(tmp_path):
    config_path = write_config(tmp_path, share_mode="serve", sites=["https://example.com"])
    result, _, _ = run_share(tmp_path, config_path)
    assert result.returncode == 0
    # Now we use a single serve set-raw command instead of two serve commands
    assert share_commands(tmp_path / "tailscale.log") == [("serve", "set-raw")]


def test_share_mode_matches_dal_funnel(tmp_path):
    config_path = write_config(tmp_path, share_mode="funnel", sites=["https://example.com"])
    status_json = json.dumps({"Self": {"CapMap": {"https": True, "funnel": True}, "DNSName": "test-device.tailnet.ts.net."}})
    result, _, _ = run_share(tmp_path, config_path, status_json=status_json)
    assert result.returncode == 0
    # Now we use a single serve set-raw command (even for funnel mode)
    assert share_commands(tmp_path / "tailscale.log") == [("serve", "set-raw")]


def test_funnel_requires_capability(tmp_path):
    config_path = write_config(tmp_path, share_mode="funnel")
    status_json = json.dumps({"Self": {"CapMap": {"https": True}}})
    result, _, _ = run_share(tmp_path, config_path, status_json=status_json)
    assert result.returncode != 0


def test_creates_data_directory(tmp_path):
    config_path = write_config(tmp_path, sites=["https://example.com"])
    result, data_root, _ = run_share(tmp_path, config_path)
    assert result.returncode == 0
    assert data_root.exists()


def test_empty_sites_no_assetlinks(tmp_path):
    """When no digital_asset_links_sites are configured, assetlinks.json should not exist."""
    config_path = write_config(tmp_path, sites=[])
    result, data_root, _ = run_share(tmp_path, config_path)
    assert result.returncode == 0
    assetlinks_path = data_root / "digital-asset-links/www/.well-known/assetlinks.json"
    assert not assetlinks_path.exists()


def test_empty_sites_no_dal_serve_handler(tmp_path):
    """When no sites are configured, serve config should not include DAL path handler."""
    config_path = write_config(tmp_path, sites=[])
    result, data_root, serve_config_path = run_share(tmp_path, config_path, capture_serve_config=True)
    assert result.returncode == 0
    # The serve set-raw should still be called (for HA proxy), verify no DAL path in config
    log_path = tmp_path / "tailscale.log"
    assert log_path.exists()
    # Verify the ServeConfig does not contain the DAL handler
    assert serve_config_path.exists()
    serve_config = json.loads(serve_config_path.read_text())
    handlers = serve_config["Web"]["test-device.tailnet.ts.net:443"]["Handlers"]
    assert "/.well-known/" not in handlers


def test_dal_serve_config_includes_handler(tmp_path):
    """When DAL sites are configured, serve config should include the DAL directory handler."""
    config_path = write_config(tmp_path, sites=["https://example.com"])
    result, data_root, serve_config_path = run_share(tmp_path, config_path, capture_serve_config=True)
    assert result.returncode == 0
    # Verify the ServeConfig contains the DAL handler for the .well-known directory
    assert serve_config_path.exists()
    serve_config = json.loads(serve_config_path.read_text())
    handlers = serve_config["Web"]["test-device.tailnet.ts.net:443"]["Handlers"]
    # The handler serves the .well-known directory, not the specific file
    assert "/.well-known/" in handlers
    dal_handler = handlers["/.well-known/"]
    assert "Path" in dal_handler
    # Verify the path points to the .well-known directory
    assert dal_handler["Path"].endswith("/digital-asset-links/www/.well-known")


def test_dal_serve_config_has_correct_structure(tmp_path):
    """Verify the full ServeConfig structure when DAL is configured."""
    config_path = write_config(tmp_path, share_mode="serve", sites=["https://example.com"], share_port=443)
    result, data_root, serve_config_path = run_share(tmp_path, config_path, capture_serve_config=True)
    assert result.returncode == 0
    assert serve_config_path.exists()
    serve_config = json.loads(serve_config_path.read_text())
    # Verify TCP listener
    assert "TCP" in serve_config
    assert "443" in serve_config["TCP"]
    assert serve_config["TCP"]["443"]["HTTPS"] is True
    # Verify Web handlers
    assert "Web" in serve_config
    hostport = "test-device.tailnet.ts.net:443"
    assert hostport in serve_config["Web"]
    handlers = serve_config["Web"][hostport]["Handlers"]
    # Verify both handlers are present
    assert "/" in handlers
    assert "Proxy" in handlers["/"]
    # The handler serves the .well-known directory
    assert "/.well-known/" in handlers
    assert "Path" in handlers["/.well-known/"]
    # Verify AllowFunnel
    assert "AllowFunnel" in serve_config
    assert serve_config["AllowFunnel"][hostport] is False
