"""CLI for the NotebookLM adapter.

Usage::

    python -m broadcast_kit.adapters.notebooklm.cli generate --input <path> --output-dir <dir> \
        [--kinds slides,audio] [--dry-run]
    python -m broadcast_kit.adapters.notebooklm.cli list
    python -m broadcast_kit.adapters.notebooklm.cli status --notebook-id <id>
    python -m broadcast_kit.adapters.notebooklm.cli download --notebook-id <id> --output-dir <dir>
    python -m broadcast_kit.adapters.notebooklm.cli login
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from broadcast_kit.optimizers.base import OptimizerError

from .generate import download, generate, list_notebooks, status


def _parse_kinds(raw: str | None) -> list[str]:
    if not raw:
        return ["slides", "audio"]
    items = [s.strip() for s in raw.split(",") if s.strip()]
    return items or ["slides", "audio"]


def _emit(obj: object) -> None:
    if hasattr(obj, "to_dict"):
        obj = obj.to_dict()
    sys.stdout.write(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def _cmd_generate(args: argparse.Namespace) -> int:
    artifacts = generate(
        input_path=Path(args.input),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        kinds=_parse_kinds(args.kinds),
        poll_interval_seconds=args.poll_interval,
        max_wait_seconds=args.max_wait,
        dry_run=args.dry_run,
    )
    _emit(artifacts)
    return 0 if artifacts.status in {"complete", "dry_run"} else 1


def _cmd_list(_args: argparse.Namespace) -> int:
    _emit(list_notebooks())
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    _emit(status(args.notebook_id))
    return 0


def _cmd_download(args: argparse.Namespace) -> int:
    artifacts = download(args.notebook_id, Path(args.output_dir))
    _emit(artifacts)
    return 0 if artifacts.status in {"complete", "partial"} else 1


def _cmd_login(_args: argparse.Namespace) -> int:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        return subprocess.call(["notebooklm", "login"], env=env)
    except FileNotFoundError as exc:
        raise OptimizerError(
            "notebooklm-py not installed; pip install notebooklm-py && notebooklm login"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="broadcast-kit-notebooklm",
        description="Generate NotebookLM slides + audio from a PDF / markdown / directory input.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_gen = sub.add_parser("generate", help="Upload input, generate artifacts, download them.")
    p_gen.add_argument("--input", required=True, help="Path to PDF, markdown file, text file, or directory.")
    p_gen.add_argument("--output-dir", default=None, help="Where to write artifacts (default: state/notebooklm/<slug>).")
    p_gen.add_argument("--kinds", default=None, help="Comma list: slides,audio (default: both).")
    p_gen.add_argument("--poll-interval", type=int, default=15, help="Seconds between status polls (default 15).")
    p_gen.add_argument("--max-wait", type=int, default=600, help="Max seconds to wait for artifacts (default 600).")
    p_gen.add_argument("--dry-run", action="store_true", help="Print plan and exit; do not invoke notebooklm.")
    p_gen.set_defaults(func=_cmd_generate)

    p_list = sub.add_parser("list", help="List notebooks visible to the logged-in account.")
    p_list.set_defaults(func=_cmd_list)

    p_status = sub.add_parser("status", help="Show artifact status for a notebook id.")
    p_status.add_argument("--notebook-id", required=True)
    p_status.set_defaults(func=_cmd_status)

    p_dl = sub.add_parser("download", help="Download artifacts for an existing notebook.")
    p_dl.add_argument("--notebook-id", required=True)
    p_dl.add_argument("--output-dir", required=True)
    p_dl.set_defaults(func=_cmd_download)

    p_login = sub.add_parser("login", help="Run `notebooklm login` (OAuth browser flow).")
    p_login.set_defaults(func=_cmd_login)

    return parser


def main(argv: list[str] | None = None) -> int:
    from broadcast_kit._pyver import require_min_python

    require_min_python("broadcast_kit.adapters.notebooklm.cli")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except OptimizerError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
