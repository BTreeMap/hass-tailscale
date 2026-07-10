#!/usr/bin/env python3
"""Validate Home Assistant add-on metadata and emit workflow outputs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_ARCHITECTURES = {"aarch64", "amd64"}
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def load_addon_info(config_path: Path) -> dict[str, str]:
    """Load and validate fields consumed by build and release workflows."""
    config = yaml.safe_load(config_path.read_text())
    if not isinstance(config, dict):
        raise ValueError("add-on configuration must be a mapping")

    values: dict[str, Any] = {}
    for field in ("name", "slug", "description", "version"):
        value = config.get(field)
        if not isinstance(value, str) or not value.strip() or "\n" in value:
            raise ValueError(f"{field} must be a non-empty single-line string")
        values[field] = value

    if not VERSION_PATTERN.fullmatch(values["version"]):
        raise ValueError("version must use stable X.Y.Z format")
    if not SLUG_PATTERN.fullmatch(values["slug"]):
        raise ValueError("slug contains unsupported characters")

    architectures = config.get("arch")
    if not isinstance(architectures, list) or not architectures:
        raise ValueError("arch must be a non-empty list")
    if len(architectures) != len(set(architectures)):
        raise ValueError("arch must not contain duplicates")
    unsupported = set(architectures) - SUPPORTED_ARCHITECTURES
    if unsupported:
        raise ValueError(f"unsupported architectures: {', '.join(sorted(unsupported))}")

    target = config_path.parent
    if not (target / "Dockerfile").is_file():
        raise ValueError(f"missing Dockerfile in {target}")

    return {
        "architectures": json.dumps(architectures, separators=(",", ":")),
        "description": values["description"],
        "name": values["name"],
        "slug": values["slug"],
        "target": target.as_posix(),
        "version": values["version"],
    }


def write_github_outputs(outputs: dict[str, str], output_path: Path) -> None:
    """Append validated, single-line values to a GitHub Actions output file."""
    with output_path.open("a") as output_file:
        for key, value in outputs.items():
            output_file.write(f"{key}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    outputs = load_addon_info(args.config)
    if args.github_output:
        write_github_outputs(outputs, args.github_output)
    else:
        print(json.dumps(outputs, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
