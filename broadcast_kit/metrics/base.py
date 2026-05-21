from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def empty_metrics() -> dict[str, Any]:
    return {
        "views": None,
        "likes": None,
        "comments": None,
        "shares": None,
        "favorites": None,
        "saves": None,
        "completion_rate": None,
        "profile_visits": None,
        "follower_growth": None,
        "follow_conversion": None,
    }


@dataclass
class MetricsSnapshot:
    platform: str
    account_label: str = ""
    account_handle: str = ""
    record_type: str = "account_snapshot"
    status: str = "ok"
    metrics: dict[str, Any] = field(default_factory=empty_metrics)
    post_id: str | None = None
    post_url: str | None = None
    title: str = ""
    published_at: str | None = None
    content_id: str = ""
    script_id: str = ""
    source_path: str = ""
    top_comments: list[str] = field(default_factory=list)
    partial: bool = False
    source: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "schema_version": "broadcast.metrics.v0",
            "snapshot_at": now.isoformat().replace("+00:00", "Z"),
            "date": now.date().isoformat(),
            **asdict(self),
        }

