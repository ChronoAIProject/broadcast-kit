from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from broadcast_kit.contracts import ContractError


def run_json_command(command: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=merged_env,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ContractError(
            "external command failed: "
            + " ".join(command)
            + f"\nstdout: {completed.stdout.strip()}\nstderr: {completed.stderr.strip()}"
        )
    output = completed.stdout.strip()
    if not output:
        return {"status": "ok", "stdout": ""}
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ContractError(f"external command did not emit JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ContractError("external command JSON output must be an object")
    return parsed


def command_plan(adapter: str, command: list[str], cwd: Path | None = None) -> dict[str, Any]:
    return {
        "adapter": adapter,
        "cwd": str(cwd) if cwd else None,
        "command": command,
    }
