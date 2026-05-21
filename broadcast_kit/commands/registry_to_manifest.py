from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from broadcast_kit.adapters.content_registry import read_publish_registry
from broadcast_kit.contracts import ContractError, validate_douyin_caption, write_json

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


def _item_by_id(registry: dict[str, Any], content_id: str) -> dict[str, Any]:
    for item in registry.get("items", []):
        if str(item.get("content_id")) == content_id:
            return item
    raise ContractError(f"content_id not found in registry: {content_id}")


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("metadata") or {}
    if not isinstance(value, dict):
        raise ContractError("publish-registry item metadata must be an object when present")
    return value


def _artifacts(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("artifacts") or {}
    if not isinstance(value, dict):
        raise ContractError("publish-registry item artifacts must be an object")
    return value


def _hashtags(item: dict[str, Any]) -> list[str]:
    meta = _metadata(item)
    raw = item.get("hashtags") or item.get("topics") or meta.get("hashtags") or meta.get("topics") or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise ContractError("hashtags/topics must be a list or string")
    return [str(tag).strip() for tag in raw if str(tag).strip()]


def _caption(item: dict[str, Any]) -> str:
    meta = _metadata(item)
    value = item.get("caption") or item.get("body") or meta.get("caption") or meta.get("summary") or item.get("title")
    text = str(value or "").strip()
    if not text:
        raise ContractError("registry item needs caption/body/metadata.caption/metadata.summary/title")
    tags = _hashtags(item)
    if tags and not any(tag in text for tag in tags):
        text = text.rstrip() + " " + " ".join(tags)
    return text


def _douyin_manifest(item: dict[str, Any], schedule_at: str | None, douyin_schedule_at: str | None) -> dict[str, Any]:
    artifacts = _artifacts(item)
    caption = _caption(item)
    validate_douyin_caption(caption)
    video_file = artifacts.get("video_file")
    video_url = artifacts.get("video_url")
    if bool(video_file) == bool(video_url):
        raise ContractError("douyin manifest needs exactly one of artifacts.video_file or artifacts.video_url")
    if not douyin_schedule_at:
        raise ContractError("--douyin-schedule-publish-at is required for douyin manifests")
    return {
        "id": str(item["content_id"]),
        "platform": "douyin",
        "title": str(item["title"]),
        "caption": caption,
        "publish_mode": "scheduled",
        **({"video_file": str(video_file)} if video_file else {"video_url": str(video_url)}),
        **({"cover_horizontal_file": str(artifacts["cover_horizontal_file"])} if artifacts.get("cover_horizontal_file") else {}),
        **({"cover_vertical_file": str(artifacts["cover_vertical_file"])} if artifacts.get("cover_vertical_file") else {}),
        "topics": [tag.lstrip("#") for tag in _hashtags(item)],
        "schedule_at": schedule_at,
        "douyin_schedule_publish_at": douyin_schedule_at,
        "status": "pending",
        "publish_enabled": True,
        "enabled": True,
    }


def _xhs_manifest(item: dict[str, Any]) -> dict[str, Any]:
    artifacts = _artifacts(item)
    assets = artifacts.get("asset_paths") or artifacts.get("image_files") or artifacts.get("images") or artifacts.get("video_file")
    if isinstance(assets, str):
        assets = [assets]
    if not assets:
        raise ContractError("xhs manifest needs artifacts.asset_paths/image_files/images/video_file")
    asset_kind = "video" if len(assets) == 1 and str(assets[0]).lower().endswith((".mp4", ".mov", ".m4v")) else "image"
    return {
        "id": str(item["content_id"]),
        "platform": "xhs",
        "title": str(item["title"])[:20],
        "body": _caption(item),
        "topics": [tag.lstrip("#") for tag in _hashtags(item)],
        "asset_paths": [str(path) for path in assets],
        "asset_kind": asset_kind,
        "status": "draft",
    }


def _x_job(item: dict[str, Any], account_label: str | None, source_path: str | None, dry_run: bool) -> dict[str, Any]:
    return {
        "publish_job_id": f"x_{item['content_id']}",
        "platform": "x",
        "account_label": account_label or "default",
        "content_id": str(item["content_id"]),
        "title": str(item["title"]),
        "body": _caption(item),
        "source_path": source_path or str(_metadata(item).get("source_path") or ""),
        "dry_run": dry_run,
    }


def _write_structured(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:
            raise ContractError("PyYAML is required to write YAML manifests")
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    else:
        write_json(path, data)


def run(
    registry: Path,
    content_id: str,
    platform: str,
    output: Path,
    schedule_at: str | None,
    douyin_schedule_publish_at: str | None,
    account_label: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    if platform not in {"douyin", "xhs", "x"}:
        raise ContractError("platform must be douyin, xhs, or x")
    data = read_publish_registry(registry)
    item = _item_by_id(data, content_id)
    if item.get("ready") is not True:
        raise ContractError(f"registry item is not ready: {content_id}")
    targets = item.get("platform_targets") or []
    if targets and platform not in targets:
        raise ContractError(f"registry item does not target platform {platform}: {targets}")

    if platform == "douyin":
        manifest = _douyin_manifest(item, schedule_at, douyin_schedule_publish_at)
    elif platform == "xhs":
        manifest = _xhs_manifest(item)
    else:
        manifest = _x_job(item, account_label, item.get("source_path") or data.get("source", {}).get("path"), dry_run)

    manifest.setdefault("generated_at", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    if not dry_run:
        _write_structured(output, manifest)
    return {
        "status": "dry_run" if dry_run else "ok",
        "platform": platform,
        "registry": str(registry),
        "content_id": content_id,
        "output": str(output),
        "manifest": manifest,
    }
