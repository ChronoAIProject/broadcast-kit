from __future__ import annotations

from pathlib import Path

from broadcast_kit.contracts import ContractError, read_structured_file, validate_content_batch, validate_storyboard, write_json


def run(batch: Path, item_id: str, variant: str, dry_run: bool) -> dict:
    data = read_structured_file(batch)
    validate_content_batch(data, batch)
    item = next((candidate for candidate in data["items"] if candidate["content_id"] == item_id), None)
    if item is None:
        raise ContractError(f"item_id not found in batch: {item_id}")
    if variant not in {"hook-a", "hook-b", "brand", "opening"}:
        raise ContractError("variant must be hook-a, hook-b, brand, or opening")

    storyboard = {
        "storyboard_id": f"{item_id}_{variant}",
        "content_id": item_id,
        "duration_seconds": 72,
        "format": {
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "language_profile": "zh-primary bilingual",
        },
        "beats": [
            {
                "start": 0,
                "duration": 9,
                "scene": variant,
                "narration_zh": item["caption"],
                "narration_en": "",
            }
        ],
        "artifacts": {
            "storyboard_json": str(batch.parent / f"{item_id}_{variant}_storyboard.json"),
            "hyperframes_html": str(batch.parent / "index.html"),
            "preview_image": str(batch.parent / "preview.jpg"),
            "audio_file": None,
        },
    }
    validate_storyboard(storyboard)
    output_path = Path(storyboard["artifacts"]["storyboard_json"])
    if not dry_run:
        write_json(output_path, storyboard)
    return {"status": "dry_run" if dry_run else "ok", "output": str(output_path), "storyboard": storyboard}
