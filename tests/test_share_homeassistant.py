import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_SCRIPT = REPO_ROOT / "tailscale/rootfs/etc/s6-overlay/s6-rc.d/share-homeassistant/run"
FIXTURES = REPO_ROOT / "tests/fixtures"
ASSETLINKS_PATH = Path("/data/digital-asset-links/www/.well-known/assetlinks.json")


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
    env.update(
        {
            "PATH": f"{FIXTURES}:{env['PATH']}",
            "BASH_ENV": str(FIXTURES / "bashio.sh"),
            "BASHIO_CONFIG_JSON": str(config_path),
            "TAILSCALE_BIN": str(FIXTURES / "tailscale_stub.sh"),
            "TAILSCALE_LOG": str(tmp_path / "tailscale.log"),
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
    return result


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
    result = run_share(tmp_path, config_path)
    assert result.returncode != 0


def test_rejects_origin_with_path(tmp_path):
    config_path = write_config(tmp_path, sites=["https://example.com/path"])
    result = run_share(tmp_path, config_path)
    assert result.returncode != 0


def test_rejects_port_out_of_range(tmp_path):
    config_path = write_config(tmp_path, sites=["https://example.com:65536"])
    result = run_share(tmp_path, config_path)
    assert result.returncode != 0


def test_accepts_valid_port_and_writes_assetlinks(tmp_path):
    config_path = write_config(tmp_path, sites=["https://example.com:444"])
    result = run_share(tmp_path, config_path)
    assert result.returncode == 0
    assert ASSETLINKS_PATH.exists()
    data = json.loads(ASSETLINKS_PATH.read_text())
    assert data[0]["target"]["site"] == "https://example.com:444"


def test_deduplicates_and_sorts_sites(tmp_path):
    config_path = write_config(
        tmp_path,
        sites=["https://b.example.com", "https://a.example.com", "https://b.example.com"],
    )
    result = run_share(tmp_path, config_path)
    assert result.returncode == 0
    data = json.loads(ASSETLINKS_PATH.read_text())
    sites = [entry["target"]["site"] for entry in data]
    assert sites == ["https://a.example.com", "https://b.example.com"]


def test_share_mode_matches_dal(tmp_path):
    config_path = write_config(tmp_path, share_mode="serve", sites=["https://example.com"])
    result = run_share(tmp_path, config_path)
    assert result.returncode == 0
    assert share_commands(tmp_path / "tailscale.log") == ["serve", "serve"]


def test_share_mode_matches_dal_funnel(tmp_path):
    config_path = write_config(tmp_path, share_mode="funnel", sites=["https://example.com"])
    status_json = json.dumps({"Self": {"CapMap": {"https": True, "funnel": True}}})
    result = run_share(tmp_path, config_path, status_json=status_json)
    assert result.returncode == 0
    assert share_commands(tmp_path / "tailscale.log") == ["funnel", "funnel"]


def test_funnel_requires_capability(tmp_path):
    config_path = write_config(tmp_path, share_mode="funnel")
    status_json = json.dumps({"Self": {"CapMap": {"https": True}}})
    result = run_share(tmp_path, config_path, status_json=status_json)
    assert result.returncode != 0


def test_creates_data_directory(tmp_path):
    data_dir = Path("/data")
    if data_dir.exists():
        if not data_dir.is_dir():
            pytest.skip("/data is not a directory")
        try:
            if any(data_dir.iterdir()):
                pytest.skip("/data not empty")
            data_dir.rmdir()
        except Exception:
            pytest.skip("/data not removable or not empty")
    config_path = write_config(tmp_path, sites=["https://example.com"])
    result = run_share(tmp_path, config_path)
    assert result.returncode == 0
    assert data_dir.exists()
