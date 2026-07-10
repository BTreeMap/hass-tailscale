from pathlib import Path

import pytest
import yaml

from scripts.addon_info import load_addon_info

CONFIG_PATH = Path(__file__).parents[1] / "tailscale" / "config.yaml"
STAGE2_HOOK_PATH = CONFIG_PATH.parent / "rootfs/etc/s6-overlay/scripts/stage2_hook.sh"


def test_repository_addon_configuration() -> None:
    info = load_addon_info(CONFIG_PATH)

    assert info.architectures == ("aarch64", "amd64")
    assert info.slug == "tailscale"
    assert info.target.resolve() == CONFIG_PATH.parent.resolve()
    assert info.as_outputs()["architectures"] == '["aarch64","amd64"]'


def test_stage2_hook_does_not_call_deprecated_option_api() -> None:
    hook = STAGE2_HOOK_PATH.read_text(encoding="utf-8")

    assert "bashio::addon.options" not in hook
    assert "bashio::addon.option " not in hook


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
