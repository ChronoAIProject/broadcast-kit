"""Small runtime contract validators used by the CLI.

The repository also ships JSON Schema files for agents and future tests. These
validators intentionally cover only the v0 fields that the CLI needs to protect
before delegating to existing external tools.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised only in minimal envs
    yaml = None  # type: ignore[assignment]


class ContractError(ValueError):
    """Raised when a Broadcast Kit contract is invalid."""


@dataclass(frozen=True)
class ContractResult:
    name: str
    path: Path | None
    data: dict[str, Any]


PLATFORMS = {"douyin", "xhs", "x", "all"}
METRIC_PLATFORMS = {"douyin", "xhs", "x", "youtube", "all"}
FORBIDDEN_DOUYIN_CAPTION_TERMS = ("来源", "*", "notebooklm", "slidesync", "#notebooklm")


def read_structured_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ContractError(f"file does not exist: {path}")
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix == ".json":
        data = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise ContractError("PyYAML is required to read YAML manifests")
        data = yaml.safe_load(text)
    else:
        raise ContractError(f"unsupported structured file type: {path.suffix}")
    if not isinstance(data, dict):
        raise ContractError(f"expected object at top level in {path}")
    return data


def ensure_keys(data: dict[str, Any], required: list[str], label: str) -> None:
    missing = [key for key in required if key not in data or data[key] in (None, "")]
    if missing:
        raise ContractError(f"{label} missing required field(s): {', '.join(missing)}")


def ensure_enum(value: str, allowed: set[str], label: str) -> None:
    if value not in allowed:
        raise ContractError(f"{label} must be one of {sorted(allowed)}, got {value!r}")


def validate_content_batch(data: dict[str, Any], path: Path | None = None) -> ContractResult:
    ensure_keys(data, ["batch_id", "generated_at", "source", "items"], "content-batch")
    if not isinstance(data["source"], dict):
        raise ContractError("content-batch source must be an object")
    if not isinstance(data["items"], list):
        raise ContractError("content-batch items must be an array")
    for index, item in enumerate(data["items"]):
        if not isinstance(item, dict):
            raise ContractError(f"content-batch item {index} must be an object")
        ensure_keys(
            item,
            [
                "content_id",
                "source_path",
                "language",
                "title",
                "caption",
                "hashtags",
                "chapters",
                "visual_direction",
                "platform_targets",
            ],
            f"content-batch item {index}",
        )
        if not isinstance(item["hashtags"], list) or not isinstance(item["chapters"], list):
            raise ContractError(f"content-batch item {index} hashtags and chapters must be arrays")
        if not isinstance(item["platform_targets"], list):
            raise ContractError(f"content-batch item {index} platform_targets must be an array")
    return ContractResult("content-batch", path, data)


def validate_storyboard(data: dict[str, Any], path: Path | None = None) -> ContractResult:
    ensure_keys(data, ["storyboard_id", "content_id", "duration_seconds", "format", "beats", "artifacts"], "storyboard")
    if not isinstance(data["format"], dict) or not isinstance(data["beats"], list) or not isinstance(data["artifacts"], dict):
        raise ContractError("storyboard format/artifacts must be objects and beats must be an array")
    ensure_keys(data["format"], ["width", "height", "fps", "language_profile"], "storyboard.format")
    return ContractResult("storyboard", path, data)


def validate_slidesync_job(data: dict[str, Any], path: Path | None = None) -> ContractResult:
    ensure_keys(data, ["job_id", "status", "work_dir", "output_dir", "artifacts"], "slidesync-job")
    if data["status"] not in {"draft", "reviewed", "final", "error", "dry_run"}:
        raise ContractError("slidesync-job status must be draft, reviewed, final, error, or dry_run")
    if not isinstance(data["artifacts"], dict):
        raise ContractError("slidesync-job artifacts must be an object")
    return ContractResult("slidesync-job", path, data)


def validate_publish_job(data: dict[str, Any], path: Path | None = None, platform: str | None = None) -> ContractResult:
    ensure_keys(data, ["publish_job_id", "platform", "account_label", "content_id", "title", "source_path"], "publish-job")
    ensure_enum(str(data["platform"]), PLATFORMS - {"all"}, "publish-job platform")
    if platform is not None and data["platform"] != platform:
        raise ContractError(f"publish-job platform {data['platform']!r} does not match CLI platform {platform!r}")
    if data["platform"] == "douyin":
        ensure_keys(
            data,
            ["caption", "hashtags", "video_file", "cover_horizontal_file", "cover_vertical_file", "schedule_at", "douyin_schedule_publish_at"],
            "publish-job",
        )
        validate_douyin_caption(str(data["caption"]))
    elif data["platform"] == "xhs":
        ensure_keys(data, ["caption", "hashtags", "schedule_at"], "publish-job")
    elif data["platform"] == "x":
        ensure_keys(data, ["body"], "publish-job")
    return ContractResult("publish-job", path, data)


def validate_publish_result(data: dict[str, Any], path: Path | None = None) -> ContractResult:
    ensure_keys(data, ["platform", "status"], "publish-result")
    if data["platform"] == "douyin" and data["status"] == "success":
        ensure_douyin_success_triple(data)
    return ContractResult("publish-result", path, data)


def validate_metrics_snapshot(data: dict[str, Any], path: Path | None = None) -> ContractResult:
    ensure_keys(
        data,
        ["schema_version", "record_type", "snapshot_at", "date", "platform", "account_label", "metrics", "partial", "status", "source"],
        "metrics-snapshot",
    )
    if data["schema_version"] != "broadcast.metrics.v0":
        raise ContractError("metrics-snapshot schema_version must be broadcast.metrics.v0")
    ensure_enum(str(data["platform"]), METRIC_PLATFORMS - {"all"}, "metrics-snapshot platform")
    if not isinstance(data["metrics"], dict) or not isinstance(data["source"], dict):
        raise ContractError("metrics-snapshot metrics and source must be objects")
    return ContractResult("metrics-snapshot", path, data)


def validate_publish_registry(data: dict[str, Any], path: Path | None = None) -> ContractResult:
    ensure_keys(data, ["schema_version", "registry_id", "generated_at", "items"], "publish-registry")
    if not isinstance(data["items"], list):
        raise ContractError("publish-registry items must be an array")
    for index, item in enumerate(data["items"]):
        if not isinstance(item, dict):
            raise ContractError(f"publish-registry item {index} must be an object")
        ensure_keys(item, ["content_id", "title", "ready", "artifacts"], f"publish-registry item {index}")
        if not isinstance(item["artifacts"], dict):
            raise ContractError(f"publish-registry item {index} artifacts must be an object")
    return ContractResult("publish-registry", path, data)


def validate_douyin_caption(caption: str) -> None:
    lowered = caption.lower()
    matches = [term for term in FORBIDDEN_DOUYIN_CAPTION_TERMS if term.lower() in lowered]
    if matches:
        raise ContractError(f"Douyin caption contains forbidden term(s): {', '.join(matches)}")


def ensure_douyin_success_triple(data: dict[str, Any]) -> None:
    if data.get("judgement") != "success" or data.get("cover_verify") is not True or data.get("queue_verify") is not True:
        raise ContractError("Douyin success requires judgement=success, cover_verify=true, and queue_verify=true")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
