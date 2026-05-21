from __future__ import annotations

import shutil
import argparse
import json
from pathlib import Path


AGENT_SKILL_DIRS = [
    Path.home() / ".claude" / "skills",
    Path.home() / ".codex" / "skills",
    Path.home() / ".cursor-extensions",
]


def source_skills_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "skills"


def detect_targets(create_missing: bool = False) -> list[Path]:
    targets: list[Path] = []
    for path in AGENT_SKILL_DIRS:
        if path.exists():
            targets.append(path)
        elif create_missing:
            path.mkdir(parents=True, exist_ok=True)
            targets.append(path)
    return targets


def install(create_missing: bool = False, overwrite: bool = True) -> dict:
    source = source_skills_dir()
    if not source.exists():
        raise FileNotFoundError(f"skills source directory not found: {source}")
    targets = detect_targets(create_missing=create_missing)
    installed: list[str] = []
    for target in targets:
        for skill_dir in sorted(source.iterdir()):
            if not skill_dir.is_dir():
                continue
            destination = target / skill_dir.name
            if destination.exists() and overwrite:
                shutil.rmtree(destination)
            if not destination.exists():
                shutil.copytree(skill_dir, destination)
            installed.append(str(destination))
    return {
        "source": str(source),
        "targets": [str(target) for target in targets],
        "installed": installed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy Broadcast Kit skills into detected agent directories.")
    parser.add_argument("--create-missing", action="store_true", help="Create known agent skill directories when absent.")
    parser.add_argument("--no-overwrite", action="store_true", help="Leave existing installed skill directories untouched.")
    args = parser.parse_args()
    result = install(create_missing=args.create_missing, overwrite=not args.no_overwrite)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
