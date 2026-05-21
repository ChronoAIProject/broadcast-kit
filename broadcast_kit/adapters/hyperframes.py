from __future__ import annotations

from pathlib import Path
from typing import Any

from broadcast_kit.adapters.base import command_plan, run_json_command


def validate(html_file: Path, dry_run: bool, repo: Path | None = None) -> dict[str, Any]:
    command = ["hyperframes", "validate", str(html_file), "--json"]
    if dry_run:
        return {"status": "dry_run", "plan": command_plan("hyperframes", command, repo)}
    return run_json_command(command, cwd=repo)
