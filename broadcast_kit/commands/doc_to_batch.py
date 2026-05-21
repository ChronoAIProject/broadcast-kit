from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from broadcast_kit.contracts import PLATFORMS, ContractError, validate_content_batch, validate_douyin_caption, write_json


def run(input_path: Path, output_dir: Path, platform: str, dry_run: bool) -> dict:
    if platform not in PLATFORMS:
        raise ContractError(f"platform must be one of {sorted(PLATFORMS)}")
    if not input_path.exists():
        raise ContractError(f"input path does not exist: {input_path}")

    now = datetime.now(timezone.utc)
    source_type = "directory" if input_path.is_dir() else "markdown" if input_path.suffix.lower() in {".md", ".markdown"} else "repo"
    content_id = hashlib.sha1(str(input_path.resolve()).encode("utf-8")).hexdigest()[:12]
    targets = ["douyin", "xhs", "x"] if platform == "all" else [platform]
    title = input_path.stem.replace("-", " ").replace("_", " ").strip() or "broadcast item"
    caption = f"{title} #Broadcast"
    if "douyin" in targets:
        validate_douyin_caption(caption)

    batch = {
        "batch_id": now.strftime("%Y-%m-%dT%H-%M-%SZ") + "_" + content_id,
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "source": {"type": source_type, "path": str(input_path)},
        "items": [
            {
                "content_id": content_id,
                "source_path": str(input_path),
                "language": "zh",
                "title": title,
                "caption": caption,
                "hashtags": ["#Broadcast"],
                "chapters": [],
                "visual_direction": "Validate source material and provide one highlighted keyword per beat.",
                "platform_targets": targets,
            }
        ],
    }
    validate_content_batch(batch)
    output_path = output_dir / "content-batch.json"
    if not dry_run:
        write_json(output_path, batch)
    return {"status": "dry_run" if dry_run else "ok", "output": str(output_path), "content_batch": batch}
