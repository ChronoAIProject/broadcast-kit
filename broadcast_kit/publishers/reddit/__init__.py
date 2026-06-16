"""Reddit publisher: Playwright-stealth based comment reply (old.reddit.com).

Self-contained inside broadcast-kit. First-time login:
``python -m broadcast_kit.publishers.reddit.cli login --fresh --account <handle>``.

Scope: peer-help comment-reply only(not OP-post)· per-account persistent
storage_state · stealth bypass for Cloudflare browser-integrity check ·
anonymous fetch shadowban detection. Callers wanting daily-cap / rate-limit
/ multi-account orchestration should build those on top.

Why stealth: Reddit gates new sessions through Cloudflare. Default Playwright
chromium gets blocked at /login with "You've been blocked by network
security". playwright-stealth patches navigator.webdriver + CDP signals +
WebGL fingerprint + others. Verified bypass 2026-05-29.
"""

from __future__ import annotations

from typing import Any

from .config import Settings, is_auth_state_present, list_accounts, load_settings
from .manifest_schema import ManifestError, RedditManifestItem, parse_manifest
from .publish import (
    RedditError,
    RedditLoginExpiredError,
    RedditPublishResult,
    check_login_valid,
    interactive_login,
    shadowban_check,
    submit_comment,
)


def publish(job: dict[str, Any], *, dry_run: bool, config: dict[str, Any]) -> dict[str, Any]:
    """Publisher Protocol entry. Submit a comment reply to a Reddit thread.

    Job / config shape:
        thread_url: full Reddit thread URL
        body: comment text (markdown OK)
        account: account label for storage_state (e.g. "my_dev_account")
    """
    account = config.get("account") or job.get("account") or "default"
    settings = load_settings(account=account)
    try:
        item = parse_manifest(job)
    except ManifestError as exc:
        return {"platform": "reddit", "status": "manifest_invalid", "reason": str(exc)}

    try:
        result = submit_comment(
            settings=settings,
            thread_url=item.thread_url,
            body=item.body,
            dry_run=dry_run,
        )
    except RedditLoginExpiredError as exc:
        return {"platform": "reddit", "status": "login_expired", "detail": str(exc), "remedy": "python -m broadcast_kit.publishers.reddit.cli login --fresh --account " + account}
    except RedditError as exc:
        return {"platform": "reddit", "status": "failed", "detail": str(exc)}

    return {
        "platform": "reddit",
        "status": result.status,
        "post_url": result.posted_url,
        "account": account,
        "dry_run": dry_run,
        "judgement": result.status,
    }


def fetch(*, account: str | None, since: str | None, days: int | None, dry_run: bool, config: dict[str, Any]) -> dict[str, Any]:
    """Reddit metrics fetch · not implemented in this kit. Returns stub.

    Use the Reddit JSON API directly (`https://www.reddit.com/comments/<id>.json`)
    or PRAW for metrics. This kit covers publishing only.
    """
    resolved_account = account or config.get("account", "default")
    load_settings(account=resolved_account)
    return {
        "platform": "reddit",
        "status": "stub",
        "account_label": resolved_account,
        "reason": "Reddit metrics fetch not implemented in this kit · use Reddit JSON API directly",
        "dry_run": dry_run,
    }


__all__ = [
    "publish",
    "fetch",
    "list_accounts",
    "is_auth_state_present",
    "Settings",
    "RedditError",
    "RedditLoginExpiredError",
    "RedditPublishResult",
    "RedditManifestItem",
    "shadowban_check",
]
