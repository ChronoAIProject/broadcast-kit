from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
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


@dataclass(frozen=True)
class Settings:
    state_root: Path
    xhs_auth_state: Path
    work_root: Path
    screenshot_dir: Path
    creator_publish_url: str
    xhs_skip_submit: bool
    xhs_keep_open: bool
    account: str = "default"

    def ensure_runtime_dirs(self) -> None:
        for path in (
            self.work_root,
            self.screenshot_dir,
            self.xhs_auth_state.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)


def _auto_migrate_legacy_layout(state_root: Path) -> None:
    """Move state/xhs/auth.json → state/xhs/default/auth.json once.

    Idempotent: skips if target already exists, or if source doesn't exist.
    """
    legacy = state_root / "xhs" / "auth.json"
    target = state_root / "xhs" / "default" / "auth.json"
    if not legacy.exists() or not legacy.is_file():
        return
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    legacy.rename(target)
    logger.info("migrated state/xhs/auth.json → state/xhs/default/auth.json")


def load_settings(account: str = "default") -> Settings:
    state_root = _state_root()
    account_root = state_root / "xhs" / account

    # Only auto-migrate when caller is not pinning XHS_AUTH_STATE explicitly.
    auth_env_set = os.getenv("XHS_AUTH_STATE") is not None
    if not auth_env_set:
        _auto_migrate_legacy_layout(state_root)

    work_root_default = account_root / "work"

    auth_state = _path_env(
        "XHS_AUTH_STATE", str(account_root / "auth.json"), state_root
    )
    work_root = _path_env("XHS_WORK_ROOT", str(work_root_default), state_root)
    screenshot_dir = _path_env(
        "XHS_SCREENSHOT_DIR", str(work_root / "screenshots"), state_root
    )

    settings = Settings(
        state_root=state_root,
        xhs_auth_state=auth_state,
        work_root=work_root,
        screenshot_dir=screenshot_dir,
        creator_publish_url=os.getenv(
            "XHS_CREATOR_PUBLISH_URL",
            "https://creator.xiaohongshu.com/publish/publish?source=official",
        ),
        xhs_skip_submit=_bool_env("XHS_SKIP_SUBMIT"),
        xhs_keep_open=_bool_env("XHS_KEEP_OPEN"),
        account=account,
    )
    settings.ensure_runtime_dirs()
    return settings


def list_accounts() -> list[dict]:
    """Scan state/xhs/*/auth.json and return one entry per account directory.

    Returns a list of dicts with keys: account, auth_path, auth_exists, auth_mtime.
    The auth_mtime is an ISO-ish "YYYY-MM-DD HH:MM" string (empty if missing).
    """
    state_root = _state_root()
    xhs_root = state_root / "xhs"
    out: list[dict] = []
    if not xhs_root.exists():
        return out
    for child in sorted(xhs_root.iterdir()):
        if not child.is_dir():
            continue
        auth_path = child / "auth.json"
        exists = auth_path.exists() and auth_path.is_file()
        mtime = ""
        if exists:
            mtime = datetime.fromtimestamp(auth_path.stat().st_mtime).strftime(
                "%Y-%m-%d %H:%M"
            )
        out.append(
            {
                "account": child.name,
                "auth_path": str(auth_path),
                "auth_exists": exists,
                "auth_mtime": mtime,
            }
        )
    return out


def file_url(path: Path) -> str:
    return path.resolve().as_uri()
