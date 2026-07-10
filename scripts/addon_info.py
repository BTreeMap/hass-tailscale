#!/usr/bin/env python3
"""Validate Home Assistant add-on metadata and emit workflow outputs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

import yaml

SUPPORTED_ARCHITECTURES: Final = frozenset({"aarch64", "amd64"})
VERSION_PATTERN: Final = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
SLUG_PATTERN: Final = re.compile(r"[a-z0-9][a-z0-9_-]*")


class ConfigurationError(ValueError):
    """Raised when add-on metadata violates a required invariant."""


@dataclass(frozen=True, slots=True)
class AddonInfo:
    """Validated metadata consumed by build and release workflows."""

    architectures: tuple[str, ...]
    description: str
    name: str
    slug: str
    target: Path
    version: str

    def as_outputs(self) -> dict[str, str]:
        """Encode metadata as deterministic, single-line workflow outputs."""
        return {
            "architectures": json.dumps(self.architectures, separators=(",", ":")),
            "description": self.description,
            "name": self.name,
            "slug": self.slug,
            "target": self.target.as_posix(),
            "version": self.version,
        }


def _required_string(config: Mapping[object, object], field: str) -> str:
    value = config.get(field)
    if not isinstance(value, str) or not value.strip() or "\n" in value:
        raise ConfigurationError(f"{field} must be a non-empty single-line string")
    return value


def load_addon_info(config_path: Path) -> AddonInfo:
    """Load and validate fields consumed by build and release workflows."""
    document: object = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ConfigurationError("add-on configuration must be a mapping")
    config = cast(Mapping[object, object], document)

    name = _required_string(config, "name")
    slug = _required_string(config, "slug")
    description = _required_string(config, "description")
    version = _required_string(config, "version")

    if VERSION_PATTERN.fullmatch(version) is None:
        raise ConfigurationError("version must use stable X.Y.Z format")
    if SLUG_PATTERN.fullmatch(slug) is None:
        raise ConfigurationError("slug contains unsupported characters")

    raw_architectures = config.get("arch")
    if not isinstance(raw_architectures, list) or not raw_architectures:
        raise ConfigurationError("arch must be a non-empty list")
    if not all(isinstance(item, str) for item in raw_architectures):
        raise ConfigurationError("arch entries must be strings")
    architectures = tuple(cast(list[str], raw_architectures))
    if len(architectures) != len(set(architectures)):
        raise ConfigurationError("arch must not contain duplicates")
    unsupported = set(architectures) - SUPPORTED_ARCHITECTURES
    if unsupported:
        names = ", ".join(sorted(unsupported))
        raise ConfigurationError(f"unsupported architectures: {names}")

    target = config_path.parent
    if not (target / "Dockerfile").is_file():
        raise ConfigurationError(f"missing Dockerfile in {target}")

    return AddonInfo(
        architectures=architectures,
        description=description,
        name=name,
        slug=slug,
        target=target,
        version=version,
    )


def write_github_outputs(outputs: Mapping[str, str], output_path: Path) -> None:
    """Append validated, single-line values to a GitHub Actions output file."""
    with output_path.open("a", encoding="utf-8") as output_file:
        for key, value in outputs.items():
            output_file.write(f"{key}={value}\n")


def _parse_args() -> tuple[Path, Path | None]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    return args.config, args.github_output


def main() -> int:
    """Run the command-line interface and return a process exit status."""
    config_path, output_path = _parse_args()
    try:
        outputs = load_addon_info(config_path).as_outputs()
    except (ConfigurationError, OSError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if output_path is not None:
        write_github_outputs(outputs, output_path)
    else:
        print(json.dumps(outputs, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
