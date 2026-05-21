from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class ManifestError(ValueError):
    pass


class ManifestItem(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str | int
    platform: Literal["douyin"] = "douyin"
    title: str = Field(min_length=1)
    caption: str = Field(min_length=1)
    publish_mode: Literal["manual", "scheduled"] = "scheduled"
    video_file: str | None = None
    video_url: str | None = None
    cover_horizontal_file: str | None = Field(default=None, alias="cover_file")
    cover_vertical_file: str | None = Field(default=None, alias="cover_file_vertical")
    topics: list[str] = Field(default_factory=list)
    schedule_at: str | None = None
    douyin_schedule_publish_at: str | None = None
    status: str = "pending"
    publish_enabled: bool | None = None
    enabled: bool | None = None

    @field_validator("topics", mode="before")
    @classmethod
    def normalize_topics(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value

    @model_validator(mode="after")
    def validate_video_source(self) -> ManifestItem:
        has_file = bool(self.video_file)
        has_url = bool(self.video_url)
        if has_file == has_url:
            raise ManifestError("manifest must contain exactly one of video_file or video_url")
        return self

    @staticmethod
    def _parse_tz_iso(raw: str | None, field_name: str) -> datetime:
        if not raw:
            raise ManifestError(f"{field_name} is required")
        value = raw.strip()
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ManifestError(f"{field_name} is not valid ISO 8601: {raw}") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ManifestError(f"{field_name} must include timezone: {raw}")
        return parsed

    def require_timezone_schedule(self) -> datetime:
        return self._parse_tz_iso(self.schedule_at, "schedule_at")

    def require_douyin_schedule(self) -> datetime:
        return self._parse_tz_iso(self.douyin_schedule_publish_at, "douyin_schedule_publish_at")


def parse_manifest(data: dict[str, Any]) -> ManifestItem:
    try:
        return ManifestItem.model_validate(data)
    except ManifestError:
        raise
    except ValidationError as exc:
        raise ManifestError(str(exc)) from exc
