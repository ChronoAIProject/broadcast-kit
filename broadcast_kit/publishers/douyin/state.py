from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


logger = logging.getLogger(__name__)


class StateError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_state(path: str | Path) -> dict[str, Any]:
    state_path = Path(path).expanduser().resolve()
    if not state_path.exists():
        return {"items": {}, "last_run": None}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StateError(f"state json parse failed: {state_path}") from exc
    if not isinstance(data, dict):
        raise StateError(f"state root must be object: {state_path}")
    data.setdefault("items", {})
    data.setdefault("last_run", None)
    return data


def write_state(path: str | Path, data: dict[str, Any]) -> Path:
    state_path = Path(path).expanduser().resolve()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temp = state_path.with_suffix(state_path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(state_path)
    logger.info("state written: %s", state_path)
    return state_path


@contextmanager
def file_lock(lock_path: str | Path) -> Iterator[bool]:
    path = Path(lock_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    acquired = False
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        acquired = True
        os.write(fd, f"{os.getpid()}\n{utc_now_iso()}\n".encode("utf-8"))
        os.close(fd)
        fd = None
        yield True
    except FileExistsError:
        yield False
    finally:
        if fd is not None:
            os.close(fd)
        try:
            if acquired and path.exists():
                path.unlink()
        except OSError:
            logger.error("failed to remove lock file: %s", path)
