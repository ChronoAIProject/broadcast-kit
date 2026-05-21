from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from broadcast_kit.contracts import ContractError
from broadcast_kit.metrics.base import MetricsSnapshot, empty_metrics


def _request_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = Request(url, headers=headers or {})
    with urlopen(req, timeout=30) as response:
        return json.load(response)


class XCollector:
    platform = "x"

    def __init__(self, handle: str, bearer_token: str) -> None:
        self.handle = handle.removeprefix("@")
        self.bearer_token = bearer_token
        self.base_url = "https://api.x.com/2"

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.bearer_token}"}

    def _user(self) -> dict[str, Any]:
        params = urlencode({"user.fields": "public_metrics,username,name"})
        return _request_json(f"{self.base_url}/users/by/username/{self.handle}?{params}", self.headers)["data"]

    def account_metrics(self) -> dict[str, Any]:
        user = self._user()
        public = user.get("public_metrics", {})
        return {
            "handle": f"@{user['username']}",
            "display_name": user.get("name"),
            "followers": public.get("followers_count", 0),
            "following": public.get("following_count", 0),
            "post_count": public.get("tweet_count", 0),
            "listed_count": public.get("listed_count", 0),
            "user_id": user["id"],
        }

    def recent_posts(self, limit: int = 5) -> list[dict[str, Any]]:
        user_id = self._user()["id"]
        params = urlencode({"max_results": str(limit), "exclude": "replies,retweets", "tweet.fields": "created_at,public_metrics,text"})
        tweets = _request_json(f"{self.base_url}/users/{user_id}/tweets?{params}", self.headers).get("data", [])
        return [{"id": tweet["id"], "created_at": tweet.get("created_at"), "text": tweet.get("text", "")[:120], **tweet.get("public_metrics", {})} for tweet in tweets]


def fetch(*, account: str | None, since: str | None, days: int | None, dry_run: bool, config: dict[str, Any]) -> dict[str, Any]:
    _ = since, days
    handle = account or os.getenv("X_HANDLE") or ""
    token = str(config.get("bearer_token") or os.getenv("X_BEARER_TOKEN") or "")
    if dry_run:
        return {"platform": "x", "status": "dry_run", "account": handle, "requires": ["X_BEARER_TOKEN"]}
    if not handle:
        raise ContractError("X metrics require --account or X_HANDLE")
    if not token:
        raise ContractError("X_BEARER_TOKEN is required for X metrics")
    collector = XCollector(handle, token)
    account_data = collector.account_metrics()
    metrics = empty_metrics()
    metrics["follower_growth"] = account_data["followers"]
    snapshot = MetricsSnapshot(
        platform="x",
        account_label=account or "",
        account_handle=account_data["handle"],
        metrics=metrics,
        source={"adapter": "broadcast-kit", "raw_path": "", "collector": "x-api-v2"},
    ).to_dict()
    snapshot["account"] = account_data
    snapshot["recent_posts_metrics"] = collector.recent_posts()
    return snapshot
