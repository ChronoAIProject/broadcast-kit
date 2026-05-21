from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

from pathlib import Path

from broadcast_kit.adapters.base import command_plan
from broadcast_kit.contracts import ContractError


def _binary(config: dict[str, Any] | None = None) -> str:
    configured = (config or {}).get("binary")
    if configured:
        return str(configured)
    return os.getenv("NYXID_BIN") or shutil.which("nyxid") or "nyxid"


def call(service: str, action: str, payload: dict[str, Any], *, dry_run: bool, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Invoke `nyxid <service> <action>` with a JSON payload."""
    config = config or {}
    command = [_binary(config), service, action, "--input", "-"]
    if config.get("output_json", True):
        command.extend(["--output", "json"])
    cwd = Path(config["cwd"]) if config.get("cwd") else None
    if dry_run:
        return {"status": "dry_run", "plan": command_plan("nyxid", command, cwd), "payload": payload}
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ContractError(
            "nyxid command failed: "
            + " ".join(command)
            + f"\nstdout: {completed.stdout.strip()}\nstderr: {completed.stderr.strip()}"
        )
    output = completed.stdout.strip()
    if not output:
        return {"status": "ok"}
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ContractError(f"nyxid command did not emit JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ContractError("nyxid command JSON output must be an object")
    return parsed
