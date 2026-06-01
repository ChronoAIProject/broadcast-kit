"""Reddit publisher manifest schema."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from broadcast_kit.public_guard import PublicContentError, assert_manifest_public_ready


class ManifestError(ValueError):
    pass


_REDDIT_THREAD_RE = re.compile(
    r"^https?://(?:www\.|old\.|new\.|np\.)?reddit\.com/r/[^/]+/comments/[a-z0-9]+(?:/[^?#]*)?",
    re.IGNORECASE,
)


class RedditManifestItem(BaseModel):
    """Reddit comment-reply manifest.

    Minimal shape · suitable for one comment per call:
        id: caller-supplied identifier(also written as deduplication anchor)
        platform: "reddit"
        thread_url: full Reddit thread URL
        body: comment text(markdown allowed · ≤10000 chars per Reddit cap)
        account: account label · resolves to state/reddit/<account>/auth.json

    Optional:
        expected_subreddit: if set · publish will fail if URL is not under that sub
                            (catches manifest copy-paste mistakes)
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str | int
    platform: Literal["reddit"] = "reddit"
    thread_url: str = Field(min_length=20, max_length=500)
    body: str = Field(min_length=10, max_length=10000)
    account: str | None = None
    expected_subreddit: str | None = None
    status: str = "draft"

    @field_validator("thread_url")
    @classmethod
    def validate_thread_url(cls, value: str) -> str:
        if not _REDDIT_THREAD_RE.match(value):
            raise ManifestError(
                f"thread_url must match reddit.com/r/<sub>/comments/<id>/... pattern · got: {value[:80]}"
            )
        return value


def parse_manifest(data: dict[str, Any]) -> RedditManifestItem:
    try:
        assert_manifest_public_ready(data, "reddit")
    except PublicContentError as exc:
        raise ManifestError(str(exc)) from exc
    try:
        item = RedditManifestItem.model_validate(data)
    except ManifestError:
        raise
    except ValidationError as exc:
        raise ManifestError(str(exc)) from exc

    # cross-field check
    if item.expected_subreddit:
        actual = _extract_subreddit(item.thread_url)
        if actual and actual.lower() != item.expected_subreddit.lower():
            raise ManifestError(
                f"thread_url points to r/{actual} but expected_subreddit=r/{item.expected_subreddit}"
            )
    return item


def _extract_subreddit(url: str) -> str | None:
    m = re.search(r"/r/([^/]+)", url)
    return m.group(1) if m else None
