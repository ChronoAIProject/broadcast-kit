"""Discourse publisher: generic Playwright-stealth reply submit.

Works for any Discourse instance(community.n8n.io / discuss.huggingface.co
/ meta.discourse.org / self-hosted Discourse · etc.). Caller provides
instance_url in the manifest.

Scope: peer-help reply to existing topics(not OP new topic). Persistent
storage_state per (instance · account) tuple. Anonymous shadowban check
uses Discourse's built-in Topic JSON API for accurate post-list comparison.

Why generic Discourse:
- Same UI selectors across instances (.btn.create / .d-editor-input / .save-or-cancel)
- Same Topic JSON API (`/t/<topic_id>.json` returns post_stream.posts)
- Same anti-spam patterns (new accounts often staged for staff review)

Manifest specifies instance via `instance_url` field; state path is
`state/discourse/<account>__<instance_host>/auth.json` to keep multi-instance
profiles isolated.
"""

from __future__ import annotations

from typing import Any

from .config import Settings, is_auth_state_present, list_accounts, load_settings
from .manifest_schema import DiscourseManifestItem, ManifestError, parse_manifest
from .publish import (
    DiscourseError,
    DiscourseLoginExpiredError,
    DiscoursePublishResult,
    check_login_valid,
    interactive_login,
    shadowban_check,
    submit_reply,
)


def publish(job: dict[str, Any], *, dry_run: bool, config: dict[str, Any]) -> dict[str, Any]:
    """Publisher Protocol entry. Submit a reply to a Discourse topic."""
    account = config.get("account") or job.get("account") or "default"
    try:
        item = parse_manifest(job)
    except ManifestError as exc:
        return {"platform": "discourse", "status": "manifest_invalid", "reason": str(exc)}

    settings = load_settings(account=account, instance_url=item.instance_url)
    try:
        result = submit_reply(
            settings=settings,
            topic_url=item.topic_url,
            body=item.body,
            dry_run=dry_run,
        )
    except DiscourseLoginExpiredError as exc:
        return {
            "platform": "discourse",
            "status": "login_expired",
            "detail": str(exc),
            "remedy": f"python -m broadcast_kit.publishers.discourse.cli login --fresh --account {account} --instance {item.instance_url}",
        }
    except DiscourseError as exc:
        return {"platform": "discourse", "status": "failed", "detail": str(exc)}

    return {
        "platform": "discourse",
        "status": result.status,
        "post_url": result.posted_url,
        "account": account,
        "instance_url": item.instance_url,
        "dry_run": dry_run,
        "judgement": result.status,
    }


def fetch(*, account: str | None, since: str | None, days: int | None, dry_run: bool, config: dict[str, Any]) -> dict[str, Any]:
    """Discourse metrics fetch · use Topic JSON API directly. Returns stub."""
    return {
        "platform": "discourse",
        "status": "stub",
        "reason": "Discourse metrics: use the public Topic JSON API directly (`<instance>/t/<topic_id>.json`)",
        "dry_run": dry_run,
    }


__all__ = [
    "publish",
    "fetch",
    "list_accounts",
    "is_auth_state_present",
    "Settings",
    "DiscourseError",
    "DiscourseLoginExpiredError",
    "DiscoursePublishResult",
    "DiscourseManifestItem",
    "shadowban_check",
]
