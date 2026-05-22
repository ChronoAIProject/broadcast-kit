from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from broadcast_kit.public_guard import PublicContentError, assert_manifest_public_ready


class ManifestError(ValueError):
    pass


class XhsManifestItem(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str | int
    platform: Literal["xhs"] = "xhs"
    title: str = Field(min_length=1, max_length=20, description="XHS title (<=20 chars)")
    body: str = Field(min_length=1, max_length=1000, description="Post body text")
    topics: list[str] = Field(default_factory=list, description="Topic strings; click-selected through topic UI, not raw hashtags in body")
    asset_paths: list[str] = Field(default_factory=list, description="Image or video file paths to upload")
    asset_kind: Literal["image", "video"] = "image"
    target_entry: str | None = None
    status: str = "draft"

    @field_validator("topics", mode="before")
    @classmethod
    def normalize_topics(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("asset_paths", mode="before")
    @classmethod
    def normalize_asset_paths(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value

    @model_validator(mode="after")
    def validate_assets(self) -> XhsManifestItem:
        if not self.asset_paths:
            raise ManifestError("xhs manifest requires at least one asset_path")
        if self.asset_kind == "image" and len(self.asset_paths) > 18:
            raise ManifestError("xhs image post supports at most 18 assets")
        if self.asset_kind == "video" and len(self.asset_paths) != 1:
            raise ManifestError("xhs video post requires exactly one asset_path")
        return self


def parse_manifest(data: dict[str, Any]) -> XhsManifestItem:
    try:
        assert_manifest_public_ready(data, "xhs")
    except PublicContentError as exc:
        raise ManifestError(str(exc)) from exc
    try:
        return XhsManifestItem.model_validate(data)
    except ManifestError:
        raise
    except ValidationError as exc:
        raise ManifestError(str(exc)) from exc
