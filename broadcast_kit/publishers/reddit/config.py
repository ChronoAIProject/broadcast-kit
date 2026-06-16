"""Reddit publisher · Settings + per-account storage_state path."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path


logger = logging.getLogger(__name__)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _state_root() -> Path:
    raw = os.getenv("BROADCAST_KIT_STATE_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.cwd().resolve() / "state"


def _login_url() -> str:
    return os.getenv("REDDIT_LOGIN_URL", "https://old.reddit.com/login")


def _logged_in_check_url() -> str:
    # /me redirects to user page when logged in · anon redirects to /
    return os.getenv("REDDIT_LOGGED_IN_CHECK_URL", "https://old.reddit.com/me/")


@dataclass(frozen=True)
class Settings:
    state_root: Path
    reddit_auth_state: Path
    login_url: str
    logged_in_check_url: str
    account: str = "default"

    def ensure_runtime_dirs(self) -> None:
        self.reddit_auth_state.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def for_reddit(
        cls,
        *,
        state_root: Path | None = None,
        account: str = "default",
    ) -> "Settings":
        """Build Reddit Settings.

        Env vars take precedence: BROADCAST_KIT_STATE_DIR, REDDIT_LOGIN_URL,
        REDDIT_LOGGED_IN_CHECK_URL.

        storage_state path: state/reddit/<account>/auth.json
        """
        resolved_state_root = (
            state_root.expanduser().resolve() if state_root is not None else _state_root()
        )
        account_root = resolved_state_root / "reddit" / account
        auth_state = account_root / "auth.json"
        settings = cls(
            state_root=resolved_state_root,
            reddit_auth_state=auth_state,
            login_url=_login_url(),
            logged_in_check_url=_logged_in_check_url(),
            account=account,
        )
        settings.ensure_runtime_dirs()
        return settings


def load_settings(*, account: str = "default") -> Settings:
    return Settings.for_reddit(account=account)


def is_auth_state_present(*, account: str = "default") -> bool:
    """File-stat only · cheap presence check(does not verify session validity)."""
    return Settings.for_reddit(account=account).reddit_auth_state.exists()


def list_accounts(*, state_root: Path | None = None) -> list[str]:
    """Enumerate accounts that have completed at least first-time login.

    Looks at state/reddit/*/auth.json and returns the parent dir names.
    """
    root = state_root or _state_root()
    reddit_root = root / "reddit"
    if not reddit_root.is_dir():
        return []
    return sorted(
        [d.name for d in reddit_root.iterdir() if d.is_dir() and (d / "auth.json").exists()]
    )


def file_url(path: Path) -> str:
    """For typer.echo · gives clickable file:// URL in modern terminals."""
    return path.as_uri() if path.is_absolute() else Path(path).resolve().as_uri()
