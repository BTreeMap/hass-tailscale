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
    config_path.write_text(json.dumps(config))
    return config_path


def run_share(tmp_path, config_path, *, status_json=None, extra_env=None):
    env = os.environ.copy()
    bashio_dir = tmp_path / "bashio"
    if not bashio_dir.exists():
        subprocess.run(
            ["git", "clone", "--depth", "1", "https://github.com/hassio-addons/bashio", str(bashio_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
    data_root = tmp_path / "data"
    env.update(
        {
            "PATH": f"{FIXTURES}:{env['PATH']}",
            "BASH_ENV": str(FIXTURES / "bashio_env.sh"),
            "BASHIO_DIR": str(bashio_dir),
            "BASHIO_CONFIG_JSON": str(config_path),
            "TAILSCALE_BIN": str(FIXTURES / "tailscale_stub.sh"),
            "TAILSCALE_LOG": str(tmp_path / "tailscale.log"),
            "DATA_DIR": str(data_root),
        }
    )
    if status_json is not None:
        env["TAILSCALE_STATUS_JSON"] = status_json
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        ["bash", str(RUN_SCRIPT)],
        env=env,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    return result, data_root


def share_commands(log_path):
    log_lines = log_path.read_text().splitlines()
    commands = []
    for line in log_lines:
        parts = line.split()
        if len(parts) > 1:
            commands.append(parts[1])
    return [cmd for cmd in commands if cmd in ("serve", "funnel")]


def test_rejects_http_origin(tmp_path):
    config_path = write_config(tmp_path, sites=["http://example.com"])
    result, _ = run_share(tmp_path, config_path)
    assert result.returncode != 0


def test_rejects_origin_with_path(tmp_path):
    config_path = write_config(tmp_path, sites=["https://example.com/path"])
    result, _ = run_share(tmp_path, config_path)
    assert result.returncode != 0


def test_rejects_port_out_of_range(tmp_path):
    config_path = write_config(tmp_path, sites=["https://example.com:65536"])
    result, _ = run_share(tmp_path, config_path)
    assert result.returncode != 0


def test_accepts_valid_port_and_writes_assetlinks(tmp_path):
    config_path = write_config(tmp_path, sites=["https://example.com:444"])
    result, data_root = run_share(tmp_path, config_path)
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
    result, data_root = run_share(tmp_path, config_path)
    assert result.returncode == 0
    data = json.loads(
        (data_root / "digital-asset-links/www/.well-known/assetlinks.json").read_text()
    )
    sites = [entry["target"]["site"] for entry in data]
    assert sites == ["https://a.example.com", "https://b.example.com"]


def test_share_mode_matches_dal(tmp_path):
    config_path = write_config(tmp_path, share_mode="serve", sites=["https://example.com"])
    result, _ = run_share(tmp_path, config_path)
    assert result.returncode == 0
    assert share_commands(tmp_path / "tailscale.log") == ["serve", "serve"]


def test_share_mode_matches_dal_funnel(tmp_path):
    config_path = write_config(tmp_path, share_mode="funnel", sites=["https://example.com"])
    status_json = json.dumps({"Self": {"CapMap": {"https": True, "funnel": True}}})
    result, _ = run_share(tmp_path, config_path, status_json=status_json)
    assert result.returncode == 0
    assert share_commands(tmp_path / "tailscale.log") == ["funnel", "funnel"]


def test_funnel_requires_capability(tmp_path):
    config_path = write_config(tmp_path, share_mode="funnel")
    status_json = json.dumps({"Self": {"CapMap": {"https": True}}})
    result, _ = run_share(tmp_path, config_path, status_json=status_json)
    assert result.returncode != 0


def test_creates_data_directory(tmp_path):
    config_path = write_config(tmp_path, sites=["https://example.com"])
    result, data_root = run_share(tmp_path, config_path)
    assert result.returncode == 0
    assert data_root.exists()
