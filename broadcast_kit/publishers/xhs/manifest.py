from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from .manifest_schema import ManifestError, XhsManifestItem, parse_manifest


logger = logging.getLogger(__name__)


def read_manifest(path: str | Path) -> XhsManifestItem:
    manifest_path = Path(path).expanduser().resolve()
    if not manifest_path.exists():
        raise ManifestError(f"manifest not found: {manifest_path}")
    suffix = manifest_path.suffix.lower()
    text = manifest_path.read_text(encoding="utf-8")
    try:
        if suffix in {".yaml", ".yml"}:
            raw = yaml.safe_load(text) or {}
        else:
            import json
            raw = json.loads(text)
    except (yaml.YAMLError, ValueError) as exc:
        raise ManifestError(f"manifest parse failed: {manifest_path}") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"manifest root must be mapping: {manifest_path}")
    item = parse_manifest(raw)
    logger.info("xhs manifest loaded: %s", manifest_path)
    return item


def resolve_manifest_path(manifest_path: str | Path, maybe_relative: str) -> Path:
    path = Path(maybe_relative).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (Path(manifest_path).expanduser().resolve().parent / path).resolve()


def resolve_asset_paths(manifest_path: str | Path, asset_paths: list[str]) -> list[Path]:
    resolved: list[Path] = []
    for raw in asset_paths:
        resolved.append(resolve_manifest_path(manifest_path, raw))
    return resolved
