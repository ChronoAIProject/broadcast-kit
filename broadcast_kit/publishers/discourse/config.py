"""Discourse publisher · per-(account · instance) storage_state."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


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


def _instance_slug(instance_url: str) -> str:
    """Get a filesystem-safe slug for an instance URL · e.g. community.n8n.io → community_n8n_io."""
    host = urlparse(instance_url).netloc or instance_url
    return re.sub(r"[^a-zA-Z0-9]+", "_", host).strip("_").lower()


@dataclass(frozen=True)
class Settings:
    state_root: Path
    discourse_auth_state: Path
    instance_url: str
    instance_login_url: str
    account: str = "default"

    def ensure_runtime_dirs(self) -> None:
        self.discourse_auth_state.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def for_discourse(
        cls,
        *,
        state_root: Path | None = None,
        account: str = "default",
        instance_url: str,
    ) -> "Settings":
        """Build Discourse Settings.

        storage_state path: state/discourse/<account>__<instance_slug>/auth.json

        Same account name can have multiple profiles · one per instance(e.g.
        nysoa72 @ community.n8n.io vs nysoa72 @ discuss.huggingface.co · they
        get separate auth.json files because login cookies are per-domain).
        """
        resolved_state_root = (
            state_root.expanduser().resolve() if state_root is not None else _state_root()
        )
        slug = _instance_slug(instance_url)
        profile_dir = resolved_state_root / "discourse" / f"{account}__{slug}"
        auth_state = profile_dir / "auth.json"
        # Default login URL: <instance>/login
        instance_url = instance_url.rstrip("/")
        login_url = os.getenv("DISCOURSE_LOGIN_URL", f"{instance_url}/login")
        settings = cls(
            state_root=resolved_state_root,
            discourse_auth_state=auth_state,
            instance_url=instance_url,
            instance_login_url=login_url,
            account=account,
        )
        settings.ensure_runtime_dirs()
        return settings


def load_settings(*, account: str = "default", instance_url: str) -> Settings:
    return Settings.for_discourse(account=account, instance_url=instance_url)


def is_auth_state_present(*, account: str = "default", instance_url: str) -> bool:
    return Settings.for_discourse(account=account, instance_url=instance_url).discourse_auth_state.exists()


def list_accounts(*, state_root: Path | None = None) -> list[str]:
    """Enumerate all (account · instance) tuples that have completed login.

    Returns list of profile dir names like "nysoa72__community_n8n_io".
    """
    root = state_root or _state_root()
    discourse_root = root / "discourse"
    if not discourse_root.is_dir():
        return []
    return sorted(
        [d.name for d in discourse_root.iterdir() if d.is_dir() and (d / "auth.json").exists()]
    )


def file_url(path: Path) -> str:
    return path.as_uri() if path.is_absolute() else Path(path).resolve().as_uri()
