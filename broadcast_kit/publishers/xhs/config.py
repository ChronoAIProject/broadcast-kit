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

    @classmethod
    def for_xhs(
        cls,
        *,
        state_root: Path | None = None,
        account: str = "default",
        keep_open: bool = False,
        skip_submit: bool = False,
        creator_publish_url: str | None = None,
    ) -> "Settings":
        """Build XHS Settings programmatically, bypassing env-var pokes.

        Env vars still take precedence when set (preserves CLI/legacy behavior):
        BROADCAST_KIT_STATE_DIR, XHS_AUTH_STATE, XHS_WORK_ROOT,
        XHS_SCREENSHOT_DIR, XHS_CREATOR_PUBLISH_URL, XHS_KEEP_OPEN,
        XHS_SKIP_SUBMIT. Pass an explicit state_root to anchor paths anywhere
        on disk; if None, falls back to BROADCAST_KIT_STATE_DIR / cwd/state.

        Returns a fully-formed Settings with runtime dirs created
        (ensure_runtime_dirs() is called before return).
        """
        # state_root: explicit arg wins; otherwise honor env / cwd default.
        resolved_state_root = (
            state_root.expanduser().resolve() if state_root is not None else _state_root()
        )
        account_root = resolved_state_root / "xhs" / account

        # Only auto-migrate when caller is not pinning XHS_AUTH_STATE explicitly.
        auth_env_set = os.getenv("XHS_AUTH_STATE") is not None
        if not auth_env_set:
            _auto_migrate_legacy_layout(resolved_state_root)

        work_root_default = account_root / "work"

        auth_state = _path_env(
            "XHS_AUTH_STATE", str(account_root / "auth.json"), resolved_state_root
        )
        work_root = _path_env(
            "XHS_WORK_ROOT", str(work_root_default), resolved_state_root
        )
        screenshot_dir = _path_env(
            "XHS_SCREENSHOT_DIR", str(work_root / "screenshots"), resolved_state_root
        )

        default_publish_url = (
            creator_publish_url
            or "https://creator.xiaohongshu.com/publish/publish?source=official"
        )

        settings = cls(
            state_root=resolved_state_root,
            xhs_auth_state=auth_state,
            work_root=work_root,
            screenshot_dir=screenshot_dir,
            creator_publish_url=os.getenv(
                "XHS_CREATOR_PUBLISH_URL",
                default_publish_url,
            ),
            xhs_skip_submit=_bool_env("XHS_SKIP_SUBMIT", default=skip_submit),
            xhs_keep_open=_bool_env("XHS_KEEP_OPEN", default=keep_open),
            account=account,
        )
        settings.ensure_runtime_dirs()
        return settings


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
    """Load XHS Settings from environment variables (legacy CLI entrypoint).

    Delegates to `Settings.for_xhs(account=account)` so both code paths share
    the same env-var resolution logic.
    """
    return Settings.for_xhs(account=account)


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


def is_auth_state_present(settings: Settings) -> bool:
    """Fast file-stat: does the storage_state json exist on disk?

    Does NOT validate the cookie. Use when you only need to know whether
    the user has finished the first interactive login yet. Pair with
    `check_login_valid()` only when you need to confirm the cookie still
    works against the live platform (which costs a Chromium startup).
    """
    return settings.xhs_auth_state.exists() and settings.xhs_auth_state.is_file()


def file_url(path: Path) -> str:
    return path.resolve().as_uri()
