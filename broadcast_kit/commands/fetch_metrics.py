from __future__ import annotations

from broadcast_kit import metrics
from broadcast_kit.contracts import METRIC_PLATFORMS, ContractError


def run(platform: str, account: str | None, since: str | None, days: int | None, dry_run: bool) -> dict:
    if platform not in METRIC_PLATFORMS:
        raise ContractError(f"platform must be one of {sorted(METRIC_PLATFORMS)}")
    if since and days:
        raise ContractError("use either since or days, not both")

    effective_days = days
    if effective_days is None and since and since.isdigit():
        effective_days = int(since)

    if platform == "all":
        platforms = sorted(METRIC_PLATFORMS - {"all"})
        return {
            "platform": "all",
            "status": "ok",
            "records": [
                metrics.fetch(name, account=account, since=since, days=effective_days, dry_run=dry_run, config={})
                for name in platforms
            ],
        }
    return metrics.fetch(platform, account=account, since=since, days=effective_days, dry_run=dry_run, config={})
