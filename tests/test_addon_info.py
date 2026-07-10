from pathlib import Path

import pytest
import yaml

from scripts.addon_info import load_addon_info


CONFIG_PATH = Path(__file__).parents[1] / "tailscale" / "config.yaml"


def test_repository_addon_configuration() -> None:
    info = load_addon_info(CONFIG_PATH)

    assert info["architectures"] == '["aarch64","amd64"]'
    assert info["slug"] == "tailscale"
    assert Path(info["target"]).resolve() == CONFIG_PATH.parent.resolve()


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
    config = yaml.safe_load(CONFIG_PATH.read_text())
    config[field] = value
    config_path = tmp_path / "addon" / "config.yaml"
    config_path.parent.mkdir()
    config_path.write_text(yaml.safe_dump(config))
    (config_path.parent / "Dockerfile").touch()

    with pytest.raises(ValueError, match=message):
        load_addon_info(config_path)
