from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from broadcast_kit.adapters.content_registry import read_publish_registry
from broadcast_kit.contracts import ContractError, read_structured_file


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ContractError(f"metrics jsonl not found: {path}")
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ContractError(f"invalid jsonl at {path}:{lineno}: {exc}") from exc
        if not isinstance(row, dict):
            raise ContractError(f"jsonl row must be object at {path}:{lineno}")
        rows.append(row)
    return rows


def _registry_items(registry_path: Path | None) -> list[dict[str, Any]]:
    if registry_path is None:
        return []
    registry = read_publish_registry(registry_path)
    return [item for item in registry.get("items", []) if isinstance(item, dict)]


def _manifest_items(manifest_paths: list[Path]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in manifest_paths:
        data = read_structured_file(path)
        data["_manifest_path"] = str(path)
        if "id" in data and "content_id" not in data:
            data["content_id"] = str(data["id"])
        items.append(data)
    return items


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _match_source(row: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    row_title = _norm(row.get("title"))
    row_time = _norm(row.get("publish_time") or row.get("published_at"))
    for item in candidates:
        title = _norm(item.get("title"))
        if title and row_title and (title == row_title or title in row_title or row_title in title):
            return item
    for item in candidates:
        scheduled = _norm(item.get("douyin_schedule_publish_at") or item.get("schedule_at") or item.get("published_at"))
        if scheduled and row_time and scheduled[:10].replace("-", "年", 1)[:4] in row_time:
            return item
    return None


def _num(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _duration_seconds(row: dict[str, Any]) -> float | None:
    value = _norm(row.get("duration") or row.get("video_duration"))
    if not value:
        return None
    parts = value.split(":")
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None
    if len(numbers) == 2:
        return float(numbers[0] * 60 + numbers[1])
    if len(numbers) == 3:
        return float(numbers[0] * 3600 + numbers[1] * 60 + numbers[2])
    return None


def _safe_rate(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _score(row: dict[str, Any]) -> dict[str, float | None]:
    views = _num(row, "play_count_value", "views")
    likes = _num(row, "likes_value", "likes")
    comments = _num(row, "comments_count_value", "comments")
    shares = _num(row, "shares_value", "shares")
    favorites = _num(row, "favorites_value", "favorites", "saves")
    avg = _num(row, "avg_play_duration_value", "avg_play_duration")
    duration = _duration_seconds(row)
    weighted = None
    if any(value is not None for value in (views, likes, comments, shares, favorites)):
        weighted = (views or 0) + 20 * (likes or 0) + 50 * (comments or 0) + 30 * (shares or 0) + 30 * (favorites or 0)
    engagement_total = sum(value or 0 for value in (likes, comments, shares, favorites))
    return {
        "weighted_score": weighted,
        "retention_proxy": _safe_rate(avg, duration),
        "engagement_rate": _safe_rate(engagement_total, views),
        "share_rate": _safe_rate(shares, views),
        "save_rate": _safe_rate(favorites, views),
    }


def _experiment_fields(item: dict[str, Any] | None) -> dict[str, Any]:
    if not item:
        return {}
    meta = item.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = {}
    fields = {}
    for key in (
        "experiment_id",
        "variant_id",
        "template_id",
        "hook_variant",
        "cover_variant",
        "duration_variant",
        "brand_frame_variant",
        "caption_variant",
    ):
        if item.get(key) is not None:
            fields[key] = item[key]
        elif meta.get(key) is not None:
            fields[key] = meta[key]
    return fields


def run(
    metrics: Path,
    output: Path,
    registry: Path | None,
    manifests: list[Path],
    dry_run: bool,
) -> dict[str, Any]:
    rows = _iter_jsonl(metrics)
    candidates = _registry_items(registry) + _manifest_items(manifests)
    enriched: list[dict[str, Any]] = []
    snapshot_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for row in rows:
        item = _match_source(row, candidates)
        content_id = _norm((item or {}).get("content_id") or (item or {}).get("id") or row.get("content_id"))
        record = {
            "schema_version": "broadcast.feedback.v0",
            "record_type": "post_feedback",
            "enriched_at": snapshot_at,
            "content_id": content_id or None,
            "title": row.get("title"),
            "publish_time": row.get("publish_time") or row.get("published_at"),
            "status": row.get("status"),
            "platform": row.get("platform") or "douyin",
            "account": row.get("account") or row.get("account_label"),
            "source_metrics_path": str(metrics),
            "source_manifest_path": (item or {}).get("_manifest_path"),
            "matched": item is not None,
            "experiment": _experiment_fields(item),
            "metrics": row,
            "scores": _score(row),
        }
        enriched.append(record)
    if not dry_run:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as fh:
            for record in enriched:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {
        "status": "dry_run" if dry_run else "ok",
        "input": str(metrics),
        "output": str(output),
        "records": len(enriched),
        "matched": sum(1 for row in enriched if row["matched"]),
        "preview": enriched[:3],
    }
