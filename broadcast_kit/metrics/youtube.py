from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from broadcast_kit.contracts import ContractError
from broadcast_kit.metrics.base import MetricsSnapshot, empty_metrics


def _request_json(url: str) -> dict[str, Any]:
    with urlopen(Request(url), timeout=30) as response:
        return json.load(response)


class YouTubeCollector:
    platform = "youtube"

    def __init__(self, handle: str, api_key: str) -> None:
        self.handle = handle
        self.api_key = api_key
        self.base_url = "https://www.googleapis.com/youtube/v3"

    def _api_get(self, endpoint: str, **params: str) -> dict[str, Any]:
        params["key"] = self.api_key
        return _request_json(f"{self.base_url}/{endpoint}?{urlencode(params)}")

    def channel(self) -> dict[str, Any]:
        payload = self._api_get("channels", part="snippet,statistics", forHandle=self.handle.removeprefix("@"))
        items = payload.get("items", [])
        if not items:
            raise ContractError(f"No YouTube channel found for handle: {self.handle}")
        return items[0]

    def recent_posts(self, limit: int = 5) -> list[dict[str, Any]]:
        channel_id = self.channel()["id"]
        search = self._api_get("search", part="id", channelId=channel_id, maxResults=str(limit), order="date", type="video")
        ids = [item["id"]["videoId"] for item in search.get("items", []) if item.get("id", {}).get("videoId")]
        if not ids:
            return []
        videos = self._api_get("videos", part="snippet,statistics", id=",".join(ids)).get("items", [])
        return [
            {
                "id": video["id"],
                "published_at": video.get("snippet", {}).get("publishedAt"),
                "title": video.get("snippet", {}).get("title"),
                "views": int(video.get("statistics", {}).get("viewCount", 0)),
                "likes": int(video.get("statistics", {}).get("likeCount", 0)),
                "comments": int(video.get("statistics", {}).get("commentCount", 0)),
            }
            for video in videos
        ]


def fetch(*, account: str | None, since: str | None, days: int | None, dry_run: bool, config: dict[str, Any]) -> dict[str, Any]:
    _ = since, days
    handle = account or os.getenv("YOUTUBE_CHANNEL_HANDLE") or ""
    api_key = str(config.get("api_key") or os.getenv("YOUTUBE_API_KEY") or "")
    if dry_run:
        return {"platform": "youtube", "status": "dry_run", "account": handle, "requires": ["YOUTUBE_API_KEY"]}
    if not handle:
        raise ContractError("YouTube metrics require --account or YOUTUBE_CHANNEL_HANDLE")
    if not api_key:
        raise ContractError("YOUTUBE_API_KEY is required for YouTube metrics")
    collector = YouTubeCollector(handle, api_key)
    channel = collector.channel()
    stats = channel.get("statistics", {})
    metrics = empty_metrics()
    metrics["views"] = int(stats.get("viewCount", 0))
    metrics["follower_growth"] = int(stats.get("subscriberCount", 0))
    snapshot = MetricsSnapshot(
        platform="youtube",
        account_label=account or "",
        account_handle=handle,
        metrics=metrics,
        source={"adapter": "broadcast-kit", "raw_path": "", "collector": "youtube-data-api-v3"},
    ).to_dict()
    snapshot["channel"] = {"id": channel["id"], "title": channel.get("snippet", {}).get("title"), "video_count": int(stats.get("videoCount", 0))}
    snapshot["recent_posts_metrics"] = collector.recent_posts()
    return snapshot
