from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from .manifest_schema import ManifestError, ManifestItem, parse_manifest


logger = logging.getLogger(__name__)


def read_manifest(path: str | Path) -> ManifestItem:
    manifest_path = Path(path).expanduser().resolve()
    if not manifest_path.exists():
        raise ManifestError(f"manifest not found: {manifest_path}")
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ManifestError(f"manifest yaml parse failed: {manifest_path}") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"manifest root must be mapping: {manifest_path}")
    item = parse_manifest(raw)
    logger.info("manifest loaded: %s", manifest_path)
    return item


def write_manifest(item: ManifestItem | dict[str, Any], path: str | Path) -> Path:
    manifest_path = Path(path).expanduser().resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    model = item if isinstance(item, ManifestItem) else parse_manifest(item)
    data = model.model_dump(exclude_none=True, mode="json")
    manifest_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    logger.info("manifest written: %s", manifest_path)
    return manifest_path


def resolve_manifest_path(manifest_path: str | Path, maybe_relative: str | None) -> Path | None:
    if not maybe_relative:
        return None
    path = Path(maybe_relative).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (Path(manifest_path).expanduser().resolve().parent / path).resolve()
