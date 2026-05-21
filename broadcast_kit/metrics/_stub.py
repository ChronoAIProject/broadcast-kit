from __future__ import annotations

from typing import Any

from broadcast_kit.metrics.base import MetricsSnapshot


def fetch_stub(platform: str, *, account: str | None, dry_run: bool, reason: str) -> dict[str, Any]:
    snapshot = MetricsSnapshot(
        platform=platform,
        account_label=account or "",
        account_handle=account or "",
        record_type="collector_stub",
        status="stub",
        partial=True,
        source={"adapter": "broadcast-kit", "raw_path": "", "collector": f"{platform}-stub"},
    ).to_dict()
    snapshot["reason"] = reason
    snapshot["dry_run"] = dry_run
    return snapshot

