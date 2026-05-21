"""Platform publisher modules."""

from __future__ import annotations

from importlib import import_module
from typing import Any


def publish(platform: str, job: dict[str, Any], *, dry_run: bool, config: dict[str, Any] | None = None) -> dict[str, Any]:
    module = import_module(f"broadcast_kit.publishers.{platform}")
    return module.publish(job, dry_run=dry_run, config=config or {})

