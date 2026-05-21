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
    project_root: Path
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


def load_settings() -> Settings:
    state_root = _state_root()
    work_root_default = state_root / "douyin" / "work"

    auth_state = _path_env("DOUYIN_AUTH_STATE", str(state_root / "douyin" / "auth.json"), state_root)
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
    inventory_file = Path(inventory_raw).expanduser().resolve() if inventory_raw else None
    metrics_title_suffix = os.getenv("DOUYIN_METRICS_TITLE_SUFFIX") or None

    settings = Settings(
        project_root=state_root,
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


def file_url(path: Path) -> str:
    return path.resolve().as_uri()
