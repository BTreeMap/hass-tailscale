from pathlib import Path

import pytest
import yaml

from scripts.addon_info import load_addon_info

CONFIG_PATH = Path(__file__).parents[1] / "tailscale" / "config.yaml"
ROOTFS_PATH = CONFIG_PATH.parent / "rootfs"


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
