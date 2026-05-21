"""Thin subprocess wrapper around the `notebooklm` CLI shipped by notebooklm-py.

We deliberately do not import notebooklm-py as a library because its public API
is the CLI; importing the package only validates that the user has installed it.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

from broadcast_kit.optimizers.base import OptimizerError


_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_INSTALL_HINT = "notebooklm-py not installed; pip install notebooklm-py && notebooklm login"


def ensure_available() -> None:
    """Raise OptimizerError if notebooklm-py / the `notebooklm` CLI is not on PATH."""
    try:
        import notebooklm  # noqa: F401
    except ModuleNotFoundError as exc:
        raise OptimizerError(_INSTALL_HINT) from exc
    # The CLI must also be on PATH.
    try:
        subprocess.run(
            ["notebooklm", "--help"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise OptimizerError(_INSTALL_HINT) from exc


def run_nlm(*args: str, timeout: int = 120) -> str:
    """Run `notebooklm <args...>` returning stripped stdout; logs stderr on non-zero."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        result = subprocess.run(
            ["notebooklm", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            env=env,
            check=False,
        )
    except FileNotFoundError as exc:
        raise OptimizerError(_INSTALL_HINT) from exc
    except subprocess.TimeoutExpired as exc:
        raise OptimizerError(f"notebooklm {' '.join(args)}: timed out after {timeout}s") from exc
    stdout = result.stdout.decode("utf-8", errors="replace").strip()
    stderr = result.stderr.decode("utf-8", errors="replace").strip()
    if result.returncode != 0:
        detail = stderr or stdout or f"exit={result.returncode}"
        raise OptimizerError(f"notebooklm {' '.join(args)} failed: {detail[:400]}")
    return stdout


def extract_uuid(text: str) -> str | None:
    match = _UUID_RE.search(text)
    return match.group(0) if match else None


def create_notebook(title: str) -> str:
    """Create a new notebook, return its UUID."""
    out = run_nlm("create", title)
    nb_id = extract_uuid(out)
    if not nb_id:
        raise OptimizerError(f"notebooklm create: could not parse notebook id from {out!r}")
    run_nlm("use", nb_id[:8])
    return nb_id


def use_notebook(notebook_id: str) -> None:
    run_nlm("use", notebook_id[:8])


def add_source(path: Path, timeout: int = 180) -> None:
    out = run_nlm("source", "add", str(path), timeout=timeout)
    if "added" not in out.lower():
        raise OptimizerError(f"notebooklm source add {path.name} unexpected output: {out[:300]}")


def request_slides(prompt: str | None = None, timeout: int = 60) -> str:
    body = prompt or (
        "A clear presentation covering: motivation, main results, "
        "method, key takeaways, and open questions."
    )
    return run_nlm("generate", "slide-deck", body, timeout=timeout)


def request_audio(prompt: str | None = None, timeout: int = 60) -> str:
    body = prompt or (
        "A deep dive podcast discussing this material's key ideas, "
        "context, and significance."
    )
    return run_nlm("generate", "audio", body, timeout=timeout)


def artifact_list(timeout: int = 30) -> str:
    return run_nlm("artifact", "list", timeout=timeout)


def poll_until_settled(
    poll_interval: int,
    max_wait: int,
) -> dict[str, object]:
    """Poll `artifact list` until nothing is in_progress/pending or we time out.

    Returns ``{"completed": int, "failed": int, "output": str, "timed_out": bool}``.
    """
    start = time.time()
    output = ""
    while time.time() - start < max_wait:
        output = artifact_list()
        in_progress = output.count("in_progress") + output.count("pending")
        completed = output.count("completed")
        failed = output.count("failed")
        if in_progress == 0:
            return {"completed": completed, "failed": failed, "output": output, "timed_out": False}
        time.sleep(poll_interval)
    return {
        "completed": output.count("completed"),
        "failed": output.count("failed"),
        "output": output,
        "timed_out": True,
    }


def download_audio(dest: Path, timeout: int = 120) -> bool:
    run_nlm("download", "audio", str(dest), timeout=timeout)
    return dest.exists() and dest.stat().st_size > 1000


def download_slides(dest: Path, timeout: int = 120) -> bool:
    run_nlm("download", "slide-deck", str(dest), timeout=timeout)
    return dest.exists() and dest.stat().st_size > 1000


def list_notebooks_raw(timeout: int = 30) -> str:
    return run_nlm("list", timeout=timeout)
