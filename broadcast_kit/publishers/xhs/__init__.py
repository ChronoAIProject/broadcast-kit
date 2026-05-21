"""Xiaohongshu (XHS) publisher: Playwright-based note upload.

Self-contained inside broadcast-kit. First-time login: `python -m broadcast_kit.publishers.xhs.cli login --fresh`.

Scope: minimal portable publisher. No dbskill content brain, no learning loop,
no daemon scheduler. Callers who want those layers should build them on top.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_settings, setup_logging
from .manifest import read_manifest, resolve_asset_paths
from .manifest_schema import ManifestError, parse_manifest
from .publish import XhsError, upload_note


def publish(job: dict[str, Any], *, dry_run: bool, config: dict[str, Any]) -> dict[str, Any]:
    setup_logging()
    settings = load_settings()

    manifest_path = Path(str(config.get("manifest") or job.get("_manifest") or ""))
    if manifest_path and manifest_path.exists():
        try:
            item = read_manifest(manifest_path)
        except ManifestError as exc:
            return {"platform": "xhs", "status": "manifest_invalid", "reason": str(exc)}
        asset_paths = resolve_asset_paths(manifest_path, item.asset_paths)
    else:
        try:
            item = parse_manifest(job)
        except ManifestError as exc:
            return {"platform": "xhs", "status": "manifest_invalid", "reason": str(exc)}
        asset_paths = [Path(p).expanduser().resolve() for p in item.asset_paths]

    missing = [str(p) for p in asset_paths if not p.exists()]
    if missing:
        return {"platform": "xhs", "status": "asset_missing", "missing": missing}

    try:
        result = upload_note(
            settings=settings,
            asset_paths=asset_paths,
            title=item.title,
            body=item.body,
            topics=item.topics,
            asset_kind=item.asset_kind,
            submit_publish=not dry_run,
        )
    except XhsError as exc:
        return {"platform": "xhs", "status": "failed", "judgement": "failed", "detail": str(exc)}

    return {
        "platform": "xhs",
        "status": "success" if result.verdict == "success" else result.verdict,
        "judgement": result.verdict,
        "detail": result.detail,
        "note_url": result.note_url,
        "screenshots": [str(p) for p in result.screenshots],
        "manifest_path": str(manifest_path) if manifest_path else None,
    }


def fetch(*, account: str | None, since: str | None, days: int | None, dry_run: bool, config: dict[str, Any]) -> dict[str, Any]:
    """XHS metrics are not implemented in this kit yet. Returns a stub."""
    return {
        "platform": "xhs",
        "status": "stub",
        "account_label": account or "default",
        "reason": "XHS metrics scraping not implemented in this kit",
        "dry_run": dry_run,
    }


__all__ = ["publish", "fetch"]
