from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass
class PublisherResult:
    platform: str
    status: str
    post_id: str | None = None
    post_url: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        details = data.pop("details")
        data.update(details)
        return data


class Publisher(Protocol):
    def publish(self, job: dict[str, Any], *, dry_run: bool, config: dict[str, Any]) -> dict[str, Any]:
        """Publish a normalized job and return a publish-result object."""

