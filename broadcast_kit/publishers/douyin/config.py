from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


logger = logging.getLogger(__name__)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _path_env(name: str, default: str, base_dir: Path) -> Path:
    raw = os.getenv(name, default)
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _state_root() -> Path:
    raw = os.getenv("BROADCAST_KIT_STATE_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.cwd().resolve() / "state"


def _auto_migrate_legacy_layout(state_root: Path) -> None:
    """One-shot migration: state/douyin/auth.json → state/douyin/default/auth.json.

    Idempotent — does nothing if the legacy file is absent or the target already exists.
    Only runs when the user hasn't overridden DOUYIN_AUTH_STATE explicitly.
    """
    legacy = state_root / "douyin" / "auth.json"
    if not legacy.exists() or not legacy.is_file():
        return
    target = state_root / "douyin" / "default" / "auth.json"
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    legacy.replace(target)
    logger.info("migrated state/douyin/auth.json → state/douyin/default/auth.json")


@dataclass(frozen=True)
class Settings:
    project_root: Path
    account: str
    douyin_auth_state: Path
    work_root: Path
    screenshot_dir: Path
    scheduled_state_dir: Path
    scheduled_results_dir: Path
    metrics_dir: Path
    douyin_publish_url: str
    douyin_skip_submit: bool
    douyin_keep_open: bool
    douyin_schedule_state_json: Path
    inventory_file: Path | None
    metrics_title_suffix: str | None

    def ensure_runtime_dirs(self) -> None:
        for path in (
            self.work_root,
            self.screenshot_dir,
            self.scheduled_state_dir,
            self.scheduled_results_dir,
            self.metrics_dir,
            self.douyin_auth_state.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)


def load_settings(account: str = "default") -> Settings:
    state_root = _state_root()

    # Only auto-migrate the legacy single-account layout when the user has NOT
    # overridden DOUYIN_AUTH_STATE explicitly (env-override preserves old behavior).
    auth_state_override = os.getenv("DOUYIN_AUTH_STATE")
    if not auth_state_override:
        _auto_migrate_legacy_layout(state_root)

    account_root = state_root / "douyin" / account
    work_root_default = account_root / "work"

    auth_state = _path_env(
        "DOUYIN_AUTH_STATE",
        str(account_root / "auth.json"),
        state_root,
    )
    work_root = _path_env("DOUYIN_WORK_ROOT", str(work_root_default), state_root)
    screenshot_dir = _path_env("DOUYIN_SCREENSHOT_DIR", str(work_root / "screenshots"), state_root)
    scheduled_state_dir = _path_env("DOUYIN_SCHEDULED_STATE_DIR", str(work_root / "scheduled_state"), state_root)
    scheduled_results_dir = _path_env("DOUYIN_SCHEDULED_RESULTS_DIR", str(work_root / "scheduled_results"), state_root)
    metrics_dir = _path_env("DOUYIN_METRICS_DIR", str(work_root / "metrics"), state_root)
    schedule_state_json = _path_env(
        "DOUYIN_SCHEDULE_STATE_JSON",
        str(scheduled_state_dir / "publish_state.json"),
        state_root,
    )

    inventory_raw = os.getenv("DOUYIN_INVENTORY_FILE")
    if inventory_raw:
        inventory_file: Path | None = Path(inventory_raw).expanduser().resolve()
    else:
        inventory_file = (account_root / "inventory.md").resolve()
    metrics_title_suffix = os.getenv("DOUYIN_METRICS_TITLE_SUFFIX") or None

    settings = Settings(
        project_root=state_root,
        account=account,
        douyin_auth_state=auth_state,
        work_root=work_root,
        screenshot_dir=screenshot_dir,
        scheduled_state_dir=scheduled_state_dir,
        scheduled_results_dir=scheduled_results_dir,
        metrics_dir=metrics_dir,
        douyin_publish_url=os.getenv(
            "DOUYIN_PUBLISH_URL",
            "https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page",
        ),
        douyin_skip_submit=_bool_env("DOUYIN_SKIP_SUBMIT"),
        douyin_keep_open=_bool_env("DOUYIN_KEEP_OPEN"),
        douyin_schedule_state_json=schedule_state_json,
        inventory_file=inventory_file,
        metrics_title_suffix=metrics_title_suffix,
    )
    settings.ensure_runtime_dirs()
    return settings


def list_accounts() -> list[dict]:
    """Scan state/douyin/*/auth.json and return a summary list.

    Each entry: {"account": str, "auth_path": str, "auth_exists": bool, "auth_mtime": str | None}.
    The list is sorted alphabetically by account label, with "default" first if present.
    """
    state_root = _state_root()
    douyin_root = state_root / "douyin"
    results: list[dict] = []
    if not douyin_root.exists():
        return results

    for entry in sorted(douyin_root.iterdir()):
        if not entry.is_dir():
            continue
        auth_path = entry / "auth.json"
        exists = auth_path.exists() and auth_path.is_file()
        mtime: str | None = None
        if exists:
            ts = datetime.fromtimestamp(auth_path.stat().st_mtime, tz=timezone.utc).astimezone()
            mtime = ts.strftime("%Y-%m-%d %H:%M")
        results.append(
            {
                "account": entry.name,
                "auth_path": str(auth_path),
                "auth_exists": exists,
                "auth_mtime": mtime,
            }
        )

    # Put "default" first if present, keep rest alphabetical.
    results.sort(key=lambda d: (d["account"] != "default", d["account"]))
    return results


def is_auth_state_present(settings: Settings) -> bool:
    """Fast file-stat: does the storage_state json exist on disk?

    Does NOT validate the cookie. Use when you only need to know whether
    the user has finished the first interactive login yet. Pair with
    `check_login_valid()` only when you need to confirm the cookie still
    works against the live platform (which costs a Chromium startup).
    """
    return settings.douyin_auth_state.exists() and settings.douyin_auth_state.is_file()


def file_url(path: Path) -> str:
    return path.resolve().as_uri()
