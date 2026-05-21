from __future__ import annotations

import json
import os
from typing import Any
from urllib import request

from broadcast_kit.contracts import ContractError
from broadcast_kit.transports import nyxid


def _thread_parts(job: dict[str, Any]) -> list[str]:
    body = str(job.get("body") or job.get("caption") or "").strip()
    title = str(job.get("title") or "").strip()
    if not body and title:
        body = title
    parts = [part.strip() for part in body.split("---") if part.strip()]
    if title and parts and not parts[0].startswith(title):
        parts[0] = f"{title}\n\n{parts[0]}"
    return parts or ([title] if title else [])


def _direct_post(text: str, *, reply_to: str | None = None) -> dict[str, Any]:
    token = os.getenv("X_BEARER_TOKEN")
    if not token:
        raise ContractError("X_BEARER_TOKEN is required for direct X API fallback")
    payload: dict[str, Any] = {"text": text}
    if reply_to:
        payload["reply"] = {"in_reply_to_tweet_id": reply_to}
    http_request = request.Request(
        "https://api.x.com/2/tweets",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
    )
    with request.urlopen(http_request, timeout=30) as response:
        return json.load(response)


def publish(job: dict[str, Any], *, dry_run: bool, config: dict[str, Any]) -> dict[str, Any]:
    parts = _thread_parts(job)
    if not parts:
        raise ContractError("X publish requires title or body")
    payload = {
        "title": job.get("title"),
        "body": job.get("body") or job.get("caption"),
        "thread": parts,
        "account_label": job.get("account_label"),
        "content_id": job.get("content_id"),
    }
    if dry_run:
        return {"platform": "x", "status": "dry_run", "payload": payload, "thread": parts}

    route_errors: list[str] = []
    try:
        response = nyxid.call("x", "post-thread", payload, dry_run=False, config=config.get("nyxid", config))
        response.setdefault("platform", "x")
        response.setdefault("status", "success")
        response.setdefault("thread", parts)
        return response
    except Exception as exc:  # noqa: BLE001
        route_errors.append(f"nyxid: {exc}")

    posted: list[dict[str, Any]] = []
    reply_to: str | None = None
    for part in parts:
        response = _direct_post(part, reply_to=reply_to)
        tweet = response.get("data", response)
        tweet_id = str(tweet.get("id", ""))
        if not tweet_id:
            raise ContractError("X API response did not include a tweet id")
        reply_to = tweet_id
        posted.append({"id": tweet_id, "text": part, "url": f"https://x.com/i/web/status/{tweet_id}"})
    return {
        "platform": "x",
        "status": "success",
        "post_id": posted[-1]["id"] if posted else None,
        "post_url": posted[-1]["url"] if posted else None,
        "thread": posted,
        "route": "direct",
        "route_errors": route_errors,
    }

