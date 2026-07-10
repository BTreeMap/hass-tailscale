from pathlib import Path

import pytest
import yaml

from scripts.addon_info import load_addon_info

CONFIG_PATH = Path(__file__).parents[1] / "tailscale" / "config.yaml"
ROOTFS_PATH = CONFIG_PATH.parent / "rootfs"
DOCKERFILE_PATH = CONFIG_PATH.parent / "Dockerfile"
APPARMOR_PATH = CONFIG_PATH.parent / "apparmor.txt"
POST_TAILSCALED_PATH = ROOTFS_PATH / "etc/s6-overlay/s6-rc.d/post-tailscaled/run"


def test_repository_addon_configuration() -> None:
    info = load_addon_info(CONFIG_PATH)

    assert info.architectures == ("aarch64", "amd64")
    assert info.slug == "tailscale"
    assert info.target.resolve() == CONFIG_PATH.parent.resolve()
    assert info.as_outputs()["architectures"] == '["aarch64","amd64"]'


def test_runtime_uses_current_bashio_app_api() -> None:
    deprecated_references = [
        path.relative_to(ROOTFS_PATH)
        for path in ROOTFS_PATH.rglob("*")
        if path.is_file()
        and "bashio::addon." in path.read_text(encoding="utf-8", errors="strict")
    ]

    assert deprecated_references == []


def test_runtime_permanently_rejects_tailnet_dns_and_routes() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
    apparmor = APPARMOR_PATH.read_text(encoding="utf-8")
    post_tailscaled = POST_TAILSCALED_PATH.read_text(encoding="utf-8")
    rootfs_files = tuple(path for path in ROOTFS_PATH.rglob("*") if path.is_file())
    rootfs_contents = tuple(
        path.read_text(encoding="utf-8", errors="strict").lower()
        for path in rootfs_files
    )

    assert config["options"]["accept_dns"] is False
    assert config["schema"]["accept_dns"] == "bool"
    assert config["options"]["accept_routes"] is False
    assert config["schema"]["accept_routes"] == "bool"
    assert "host_dbus" not in config
    assert "SYS_ADMIN" not in config["privileged"]
    assert "--accept-dns=false" in post_tailscaled
    assert "--accept-routes=false" in post_tailscaled
    assert "accept_dns" not in post_tailscaled
    assert "accept_routes" not in post_tailscaled
    assert "dnsmasq" not in dockerfile
    assert "bind-tools" not in dockerfile
    assert "networkmanager" not in dockerfile.lower()
    assert "sys_admin" not in apparmor
    assert all(
        "magicdns" not in path.relative_to(ROOTFS_PATH).as_posix().lower()
        and "protect-subnet" not in path.relative_to(ROOTFS_PATH).as_posix().lower()
        for path in rootfs_files
    )
    assert all(
        "magicdns" not in content
        and "dnsmasq" not in content
        and "nm-dispatcher" not in content
        for content in rootfs_contents
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("version", "latest", "stable X.Y.Z"),
        ("slug", "Tailscale!", "unsupported characters"),
        ("arch", ["amd64", "riscv64"], "unsupported architectures"),
        ("arch", ["amd64", "amd64"], "must not contain duplicates"),
    ],
)
def test_invalid_addon_configuration(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    config[field] = value
    config_path = tmp_path / "addon" / "config.yaml"
    config_path.parent.mkdir()
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    (config_path.parent / "Dockerfile").touch()

    with pytest.raises(ValueError, match=message):
        load_addon_info(config_path)
