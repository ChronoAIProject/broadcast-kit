from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


PublishVerdict = Literal["success", "not_submitted", "failed"]


class PublishResult(BaseModel):
    id: str | int | None = None
    manifest_path: str | None = None
    video_path: str
    cover_horizontal_path: str | None = None
    cover_vertical_path: str | None = None
    verdict: PublishVerdict
    detail: str
    cover_verified: bool = False
    queue_verified: str = "not_checked"
    queue_evidence_txt: str | None = None
    queue_evidence_png: str | None = None
    screenshots: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def write_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return path

    def write_summary(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Publish Summary",
            "",
            f"- verdict: `{self.verdict}`",
            f"- detail: {self.detail}",
            f"- id: `{self.id or ''}`",
            f"- manifest: `{self.manifest_path or ''}`",
            f"- video: `{self.video_path}`",
            f"- cover_horizontal: `{self.cover_horizontal_path or ''}`",
            f"- cover_vertical: `{self.cover_vertical_path or ''}`",
            f"- cover_verified: `{self.cover_verified}`",
            f"- queue_verified: `{self.queue_verified}`",
            "",
            "## Screenshots",
            "",
        ]
        lines.extend(f"- `{item}`" for item in self.screenshots)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
