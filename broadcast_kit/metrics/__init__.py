"""Platform metrics collectors."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_PUBLISHER_PACKAGE_PLATFORMS = {"douyin", "xhs"}


def fetch(platform: str, *, account: str | None, since: str | None, days: int | None, dry_run: bool, config: dict[str, Any] | None = None) -> dict[str, Any]:
    if platform in _PUBLISHER_PACKAGE_PLATFORMS:
        module = import_module(f"broadcast_kit.publishers.{platform}")
    else:
        module = import_module(f"broadcast_kit.metrics.{platform}")
    return module.fetch(account=account, since=since, days=days, dry_run=dry_run, config=config or {})
