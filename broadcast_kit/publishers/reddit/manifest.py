"""Reddit manifest file reader(yaml or json)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from .manifest_schema import ManifestError, RedditManifestItem, parse_manifest


def read_manifest(manifest_path: Path) -> RedditManifestItem:
    """Load + validate a Reddit manifest file. Returns parsed item.

    Supported formats: .yaml / .yml / .json
    """
    suffix = manifest_path.suffix.lower()
    text = manifest_path.read_text(encoding="utf-8")
    if suffix in (".yaml", ".yml"):
        data = yaml.safe_load(text)
    elif suffix == ".json":
        data = json.loads(text)
    else:
        raise ManifestError(f"unsupported manifest extension: {suffix} (expected .yaml/.yml/.json)")
    if not isinstance(data, dict):
        raise ManifestError(f"manifest must be a dict at top level · got {type(data).__name__}")
    return parse_manifest(data)
