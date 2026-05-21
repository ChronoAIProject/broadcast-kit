"""Playbook schema. Pure data model — broadcast-kit does NOT run a daemon.

A `Playbook` is what a consuming agent fills out by interviewing the user
("how many followers now? what's the 4-week target? wide-net or narrow-vertical
strategy?"). Once filled, the agent's own scheduler (launchd / cron / its own
loop) decides when to wake, what to draft, which optimizers to chain.

This module exists so the YAML is validated against one shared shape across
agents — Claude Code, Codex, Cursor all read/write the same file.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from .base import OptimizerError, Platform

logger = logging.getLogger(__name__)


Strategy = Literal["wide_net", "narrow_vertical", "experiment", "consolidate"]


class CurrentState(BaseModel):
    model_config = {"extra": "allow"}
    followers: int = 0
    posts_total: int = 0
    avg_engagement_rate: float = 0.0
    top_content_type: str | None = None


class Target(BaseModel):
    model_config = {"extra": "allow"}
    followers_4w: int | None = None
    engagement_rate: float | None = None
    posts_per_week: int | None = None


class SprintPace(BaseModel):
    daily: int = 1
    weekly: int = 7


class Sprint(BaseModel):
    start: date
    end: date
    pace: SprintPace = Field(default_factory=SprintPace)


class PerTaskTargets(BaseModel):
    model_config = {"extra": "allow"}
    impressions_p50: int | None = None
    saves_p50: int | None = None
    replies_p50: int | None = None
    likes_p50: int | None = None


class MissAnalysisConfig(BaseModel):
    retrieve_top_k: int = 5
    corpus_window_days: int = 30
    vertical_tag: str | None = None


class Playbook(BaseModel):
    """One platform-scoped sprint contract.

    Consuming agents call `load_playbook(platform)` once per wake to read goals,
    pace, wake times, quiet hours, miss-analysis config, etc. They are NOT
    required to honor every field — the schema is a shared dictionary, not a
    runtime spec. Extra keys are preserved.
    """

    model_config = {"extra": "allow"}

    platform: Platform
    account: str = Field(default="default", description="Per-account scope; defaults to 'default'.")
    current_state: CurrentState = Field(default_factory=CurrentState)
    target: Target = Field(default_factory=Target)
    strategy: Strategy = "wide_net"
    sprint: Sprint | None = None
    wake_times: list[str] = Field(default_factory=list, description='e.g. ["09:30", "20:00"], local timezone')
    quiet_hours: list[str] = Field(default_factory=list, description='e.g. ["01:00", "07:00"]')
    per_task_targets: PerTaskTargets = Field(default_factory=PerTaskTargets)
    miss_analysis: MissAnalysisConfig = Field(default_factory=MissAnalysisConfig)


def _state_root() -> Path:
    raw = os.getenv("BROADCAST_KIT_STATE_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.cwd().resolve() / "state"


def _playbook_path(platform: Platform, account: str = "default", *, root: Path | None = None) -> Path:
    """Account-aware playbook path: <root>/<platform>/<account>.yaml."""
    base = root or (_state_root() / "playbook")
    return base / f"{platform}" / f"{account}.yaml"


def _legacy_playbook_path(platform: Platform, *, root: Path | None = None) -> Path:
    """Legacy single-file path: <root>/<platform>.yaml."""
    base = root or (_state_root() / "playbook")
    return base / f"{platform}.yaml"


def load_playbook(platform: Platform, account: str = "default", *, root: Path | None = None) -> Playbook:
    """Read state/playbook/<platform>/<account>.yaml.

    For account="default", falls back to the legacy state/playbook/<platform>.yaml if the
    new-layout file is absent (and logs a warning that the next write_playbook will migrate).
    Raises OptimizerError if neither exists.
    """
    import yaml

    new_path = _playbook_path(platform, account, root=root)
    path = new_path
    if not path.exists():
        if account == "default":
            legacy = _legacy_playbook_path(platform, root=root)
            if legacy.exists():
                logger.warning(
                    "legacy playbook path detected; will migrate on next write_playbook: %s",
                    legacy,
                )
                path = legacy
            else:
                raise OptimizerError(
                    f"playbook not found: {new_path}; "
                    f"run `broadcast-kit playbook init --platform {platform} --account {account}` first"
                )
        else:
            raise OptimizerError(
                f"playbook not found: {new_path}; "
                f"run `broadcast-kit playbook init --platform {platform} --account {account}` first"
            )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise OptimizerError(f"playbook YAML parse failed: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise OptimizerError(f"playbook root must be a mapping: {path}")
    try:
        return Playbook.model_validate(data)
    except ValidationError as exc:
        raise OptimizerError(f"playbook schema validation failed: {path}: {exc}") from exc


def write_playbook(playbook: Playbook, *, root: Path | None = None) -> Path:
    """Write the playbook to state/playbook/<platform>/<account>.yaml.

    If a legacy single-file <root>/<platform>.yaml exists for this platform, migrate it:
    write the new path first, then unlink the legacy file. Returns the path written.
    """
    import yaml

    path = _playbook_path(playbook.platform, playbook.account, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = playbook.model_dump(mode="json", exclude_none=False)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    legacy = _legacy_playbook_path(playbook.platform, root=root)
    if legacy.exists() and legacy.is_file():
        logger.info("migrating %s → %s", legacy, path)
        try:
            legacy.unlink()
        except OSError as exc:
            logger.warning("legacy playbook unlink failed: %s: %s", legacy, exc)
    return path


def evolve_playbook(playbook: Playbook, metrics: dict[str, Any]) -> Playbook:
    """Apply a measured-metrics dict to current_state in-place (returns updated copy).

    `metrics` shape (best-effort, all optional):
      followers, posts_total, avg_engagement_rate, top_content_type

    The playbook's `account` field is preserved through the round-trip.
    """
    updated = playbook.model_dump()
    cs = updated["current_state"]
    for key in ("followers", "posts_total", "avg_engagement_rate", "top_content_type"):
        if key in metrics and metrics[key] is not None:
            cs[key] = metrics[key]
    return Playbook.model_validate(updated)


def list_playbooks(*, root: Path | None = None) -> list[Path]:
    """Enumerate playbook files across new layout AND legacy single-file layout.

    Returns both:
      - <root>/<platform>/<account>.yaml (new account-aware)
      - <root>/<platform>.yaml           (legacy single-file)

    Deduplicates: if a platform has both a legacy file and a new-layout default.yaml,
    only the new-layout file is returned (the new layout wins).
    """
    base = root or (_state_root() / "playbook")
    if not base.exists():
        return []

    new_files: list[Path] = []
    platforms_with_default = set()
    for sub in base.iterdir():
        if sub.is_dir():
            for f in sub.glob("*.yaml"):
                if f.is_file():
                    new_files.append(f)
                    if f.stem == "default":
                        platforms_with_default.add(sub.name)

    legacy_files = [
        p
        for p in base.glob("*.yaml")
        if p.is_file() and p.stem not in platforms_with_default
    ]
    return sorted(new_files + legacy_files)


__all__ = [
    "CurrentState",
    "MissAnalysisConfig",
    "PerTaskTargets",
    "Playbook",
    "Sprint",
    "SprintPace",
    "Strategy",
    "Target",
    "evolve_playbook",
    "list_playbooks",
    "load_playbook",
    "write_playbook",
]
