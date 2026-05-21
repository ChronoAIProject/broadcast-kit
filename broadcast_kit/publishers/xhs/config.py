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

    def ensure_runtime_dirs(self) -> None:
        for path in (
            self.work_root,
            self.screenshot_dir,
            self.xhs_auth_state.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    state_root = _state_root()
    work_root_default = state_root / "xhs" / "work"

    auth_state = _path_env("XHS_AUTH_STATE", str(state_root / "xhs" / "auth.json"), state_root)
    work_root = _path_env("XHS_WORK_ROOT", str(work_root_default), state_root)
    screenshot_dir = _path_env("XHS_SCREENSHOT_DIR", str(work_root / "screenshots"), state_root)

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
    )
    settings.ensure_runtime_dirs()
    return settings


def file_url(path: Path) -> str:
    return path.resolve().as_uri()
