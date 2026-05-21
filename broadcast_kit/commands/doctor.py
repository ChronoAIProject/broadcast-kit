from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any


def _import_check(module_name: str) -> dict[str, Any]:
    try:
        __import__(module_name)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": str(exc)}


def _which_check(binary: str) -> dict[str, Any]:
    path = shutil.which(binary)
    return {"ok": path is not None, "path": path}


def _chromium_installed() -> dict[str, Any]:
    candidates = [
        Path.home() / "Library/Caches/ms-playwright",
        Path.home() / ".cache/ms-playwright",
    ]
    for cache in candidates:
        if not cache.exists():
            continue
        matches = [str(path) for path in cache.iterdir() if path.name.startswith("chromium")]
        if matches:
            return {"ok": True, "cache": str(cache), "matches": matches[:5]}
    return {"ok": False, "reason": "run `python -m playwright install chromium`"}


def _auth_file(platform: str, state_root: Path) -> dict[str, Any]:
    path = state_root / platform / "auth.json"
    return {"ok": path.exists() and path.stat().st_size > 100, "path": str(path)}


def _login_check(platform: str) -> dict[str, Any]:
    try:
        if platform == "douyin":
            from broadcast_kit.publishers.douyin.config import load_settings
            from broadcast_kit.publishers.douyin.publish import check_login_valid
        elif platform == "xhs":
            from broadcast_kit.publishers.xhs.config import load_settings
            from broadcast_kit.publishers.xhs.publish import check_login_valid
        else:
            return {"ok": False, "reason": f"unsupported platform: {platform}"}
        settings = load_settings()
        return {"ok": bool(check_login_valid(settings))}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": str(exc)}


def run(live_login_check: bool = False) -> dict[str, Any]:
    """Read-only local capability check for agents after setup."""
    state_root = Path("state").resolve()
    checks: dict[str, Any] = {
        "python": {
            "ok": sys.version_info >= (3, 11),
            "version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        },
        "packages": {
            "typer": _import_check("typer"),
            "yaml": _import_check("yaml"),
            "pydantic": _import_check("pydantic"),
            "playwright": _import_check("playwright"),
            "PIL": _import_check("PIL"),
            "notebooklm": _import_check("notebooklm"),
        },
        "binaries": {
            "ffmpeg": _which_check("ffmpeg"),
            "slidesync": _which_check("slidesync"),
            "notebooklm": _which_check("notebooklm"),
            "nyxid": _which_check("nyxid"),
        },
        "playwright": {
            "chromium": _chromium_installed(),
        },
        "state": {
            "root": str(state_root),
            "env_file": {"ok": (state_root / ".env").exists(), "path": str(state_root / ".env")},
            "douyin_auth": _auth_file("douyin", state_root),
            "xhs_auth": _auth_file("xhs", state_root),
        },
        "live_login_check": live_login_check,
    }
    if live_login_check:
        checks["state"]["douyin_login"] = _login_check("douyin")
        checks["state"]["xhs_login"] = _login_check("xhs")

    core_blockers: list[str] = []
    if not checks["python"]["ok"]:
        core_blockers.append("python>=3.11")
    for name in ("typer", "yaml", "pydantic", "playwright", "PIL"):
        if not checks["packages"][name]["ok"]:
            core_blockers.append(f"python package: {name}")
    if not checks["playwright"]["chromium"]["ok"]:
        core_blockers.append("playwright chromium")

    douyin_blockers = list(core_blockers)
    if not checks["binaries"]["ffmpeg"]["ok"]:
        douyin_blockers.append("ffmpeg")
    xhs_blockers = list(core_blockers)

    optional_missing: list[str] = []
    for name in ("slidesync", "notebooklm", "nyxid"):
        if not checks["binaries"][name]["ok"]:
            optional_missing.append(name)
    if not checks["packages"]["notebooklm"]["ok"]:
        optional_missing.append("python package: notebooklm")

    checks["summary"] = {
        "ok_for_publish_existing_media": not douyin_blockers and not xhs_blockers,
        "ok_for_douyin_existing_media": not douyin_blockers,
        "ok_for_xhs_existing_media": not xhs_blockers,
        "ok_for_source_to_video": not douyin_blockers and checks["binaries"]["slidesync"]["ok"] and checks["binaries"]["notebooklm"]["ok"] and checks["packages"]["notebooklm"]["ok"],
        "blockers": sorted(set(douyin_blockers + xhs_blockers)),
        "douyin_blockers": douyin_blockers,
        "xhs_blockers": xhs_blockers,
        "optional_missing": sorted(set(optional_missing)),
    }
    return checks
