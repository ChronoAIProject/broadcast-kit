"""Douyin publisher: Playwright-based upload + scheduled publish + queue verify + metrics.

Self-contained inside broadcast-kit. First-time login: `python -m broadcast_kit.publishers.douyin.cli login --fresh`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .config import is_auth_state_present, list_accounts, load_settings, setup_logging
from .cover_gen import MediaError, generate_covers_from_video
from .manifest import read_manifest, resolve_manifest_path
from .manifest_schema import ManifestError
from .publish import DouyinError, upload_video


_FORBIDDEN_CAPTION_TERMS = ("来源", "*", "notebooklm", "slidesync", "#notebooklm")


def _scan_caption(caption: str) -> list[str]:
    lowered = caption.lower()
    return [term for term in _FORBIDDEN_CAPTION_TERMS if term.lower() in lowered]


def publish(job: dict[str, Any], *, dry_run: bool, config: dict[str, Any]) -> dict[str, Any]:
    """Dispatcher entry. `job` is either a broadcast-kit publish-job dict or a BRIEF v2 manifest dict."""

    setup_logging()
    account = str(config.get("account", "default"))
    settings = load_settings(account=account)

    manifest_path = Path(str(config.get("manifest") or job.get("_manifest") or ""))
    if manifest_path and manifest_path.exists():
        item = read_manifest(manifest_path)
    else:
        from .manifest_schema import parse_manifest

        item = parse_manifest(job)
        manifest_path = Path(str(job.get("_manifest") or "")).resolve() if job.get("_manifest") else Path.cwd()

    hits = _scan_caption(item.caption)
    if hits:
        return {
            "platform": "douyin",
            "status": "forbidden_caption",
            "forbidden_terms": hits,
            "manifest_path": str(manifest_path),
        }

    video_path = resolve_manifest_path(manifest_path, item.video_file)
    if not (video_path and video_path.exists()):
        return {
            "platform": "douyin",
            "status": "video_missing",
            "video_file": item.video_file,
            "manifest_path": str(manifest_path),
        }

    cover_h = resolve_manifest_path(manifest_path, item.cover_horizontal_file)
    cover_v = resolve_manifest_path(manifest_path, item.cover_vertical_file)
    autogen = bool(config.get("autogen_cover", True))
    if (cover_h is None or not cover_h.exists() or cover_v is None or not cover_v.exists()):
        if autogen:
            cover_h, cover_v = generate_covers_from_video(
                video_path,
                manifest_path.parent,
                at_seconds=float(config.get("cover_at_seconds", 6.0)),
            )
        else:
            return {
                "platform": "douyin",
                "status": "cover_missing",
                "manifest_path": str(manifest_path),
            }

    schedule_iso = job.get("douyin_schedule_publish_at") or item.douyin_schedule_publish_at
    if not schedule_iso:
        return {
            "platform": "douyin",
            "status": "schedule_missing",
            "reason": "douyin_schedule_publish_at is required",
        }
    scheduled_at = datetime.fromisoformat(
        schedule_iso[:-1] + "+00:00" if schedule_iso.endswith("Z") else schedule_iso
    )

    submit = not dry_run

    try:
        result = upload_video(
            settings=settings,
            video_path=video_path,
            title=item.title,
            description=item.caption,
            cover_horizontal=cover_h,
            cover_vertical=cover_v,
            submit_publish=submit,
            scheduled_publish_at=scheduled_at,
            queue_verify_title=item.title,
            queue_verify_slug=str(item.id),
        )
    except DouyinError as exc:
        return {
            "platform": "douyin",
            "status": "failed",
            "judgement": "failed",
            "detail": str(exc),
        }

    return {
        "platform": "douyin",
        "status": "success" if result.verdict == "success" else result.verdict,
        "judgement": result.verdict,
        "detail": result.detail,
        "cover_verify": result.cover_verified,
        "queue_verify": result.queue_verified == "true",
        "screenshots": [str(p) for p in result.screenshots],
        "queue_evidence_txt": str(result.queue_evidence_txt) if result.queue_evidence_txt else None,
        "queue_evidence_png": str(result.queue_evidence_png) if result.queue_evidence_png else None,
        "manifest_path": str(manifest_path),
    }


def fetch(*, account: str | None, since: str | None, days: int | None, dry_run: bool, config: dict[str, Any]) -> dict[str, Any]:
    """Metrics dispatcher entry."""
    from .metrics import MetricsError, fetch_metrics

    setup_logging()
    account_label = account or str(config.get("account", "default"))
    settings = load_settings(account=account_label)
    effective_days = days if days is not None else (int(since) if since and since.isdigit() else 7)

    if dry_run:
        return {
            "platform": "douyin",
            "status": "dry_run",
            "plan": {
                "command": "douyin metrics scrape",
                "account": account_label,
                "days": effective_days,
                "metrics_dir": str(settings.metrics_dir),
            },
        }
    try:
        out_path = fetch_metrics(settings, days=effective_days, account=account_label)
    except MetricsError as exc:
        return {
            "platform": "douyin",
            "status": "error",
            "reason": str(exc),
        }
    return {
        "platform": "douyin",
        "status": "ok",
        "account_label": account_label,
        "days": effective_days,
        "metrics_path": str(out_path),
    }


__all__ = ["publish", "fetch", "list_accounts", "is_auth_state_present"]
