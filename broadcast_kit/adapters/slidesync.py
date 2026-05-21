from __future__ import annotations

from pathlib import Path
from typing import Any

from broadcast_kit.adapters.base import command_plan, run_json_command


def preflight(input_dir: Path, project_dir: Path, llm_provider: str, dry_run: bool, repo: Path | None = None) -> dict[str, Any]:
    command = [
        "slidesync",
        "preflight",
        "--input-dir",
        str(input_dir),
        "--project-dir",
        str(project_dir),
        "--llm-provider",
        llm_provider,
        "--json",
    ]
    if dry_run:
        return {"status": "dry_run", "plan": command_plan("slidesync", command, repo)}
    return run_json_command(command, cwd=repo)


def generate(input_dir: Path, project_dir: Path, llm_provider: str, repo: Path | None = None) -> dict[str, Any]:
    command = [
        "slidesync",
        "generate",
        "--input-dir",
        str(input_dir),
        "--project-dir",
        str(project_dir),
        "--llm-provider",
        llm_provider,
        "--json",
    ]
    return run_json_command(command, cwd=repo)
