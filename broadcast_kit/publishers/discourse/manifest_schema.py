"""Discourse publisher manifest schema."""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from broadcast_kit.public_guard import PublicContentError, assert_manifest_public_ready


class ManifestError(ValueError):
    pass


_TOPIC_URL_RE = re.compile(
    r"^https?://[^/]+/t/[^/]+/\d+",
    re.IGNORECASE,
)


class DiscourseManifestItem(BaseModel):
    """Discourse reply manifest.

    Required:
        id: caller identifier
        platform: "discourse"
        instance_url: Discourse instance base URL · e.g. "https://community.n8n.io"
        topic_url: full topic URL on that instance · e.g. ".../t/some-slug/12345"
        body: reply markdown(≤32768 per default Discourse cap)
        account: account label · resolves to state/discourse/<account>__<instance_slug>/auth.json

    Optional:
        expected_topic_id: if set · publish fails when URL topic_id ≠ this(typo catcher)
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str | int
    platform: Literal["discourse"] = "discourse"
    instance_url: str = Field(min_length=10, max_length=200)
    topic_url: str = Field(min_length=20, max_length=500)
    body: str = Field(min_length=10, max_length=32768)
    account: str | None = None
    expected_topic_id: int | None = None
    status: str = "draft"

    @field_validator("instance_url")
    @classmethod
    def validate_instance_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            raise ManifestError(f"instance_url must be a full URL · got: {value!r}")
        return value.rstrip("/")

    @field_validator("topic_url")
    @classmethod
    def validate_topic_url(cls, value: str) -> str:
        if not _TOPIC_URL_RE.match(value):
            raise ManifestError(
                f"topic_url must match <instance>/t/<slug>/<topic_id> pattern · got: {value[:80]}"
            )
        return value

    @model_validator(mode="after")
    def validate_topic_under_instance(self) -> "DiscourseManifestItem":
        # Cross-check: topic_url host should equal instance_url host
        topic_host = urlparse(self.topic_url).netloc.lower()
        instance_host = urlparse(self.instance_url).netloc.lower()
        if topic_host != instance_host:
            raise ManifestError(
                f"topic_url host ({topic_host}) does not match instance_url host ({instance_host})"
            )
        if self.expected_topic_id is not None:
            actual = _extract_topic_id(self.topic_url)
            if actual != self.expected_topic_id:
                raise ManifestError(
                    f"topic_url has topic_id={actual} but expected_topic_id={self.expected_topic_id}"
                )
        return self


def parse_manifest(data: dict[str, Any]) -> DiscourseManifestItem:
    try:
        assert_manifest_public_ready(data, "discourse")
    except PublicContentError as exc:
        raise ManifestError(str(exc)) from exc
    try:
        return DiscourseManifestItem.model_validate(data)
    except ManifestError:
        raise
    except ValidationError as exc:
        raise ManifestError(str(exc)) from exc


def _extract_topic_id(topic_url: str) -> int | None:
    m = re.search(r"/t/[^/]+/(\d+)", topic_url)
    return int(m.group(1)) if m else None


__all__ = ["DiscourseManifestItem", "ManifestError", "parse_manifest"]
