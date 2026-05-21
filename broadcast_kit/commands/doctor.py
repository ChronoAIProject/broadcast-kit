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


def _auth_file(platform: str, state_root: Path, account: str = "default") -> dict[str, Any]:
    # Prefer per-account auth path when present, otherwise fall back to the
    # legacy single-account location so this check works during the rollout.
    scoped = state_root / platform / account / "auth.json"
    legacy = state_root / platform / "auth.json"
    path = scoped if scoped.exists() else legacy
    return {
        "ok": path.exists() and path.stat().st_size > 100,
        "path": str(path),
        "account": account,
    }


def _login_check(platform: str, account: str = "default") -> dict[str, Any]:
    try:
        if platform == "douyin":
            from broadcast_kit.publishers.douyin.config import load_settings
            from broadcast_kit.publishers.douyin.publish import check_login_valid
        elif platform == "xhs":
            from broadcast_kit.publishers.xhs.config import load_settings
            from broadcast_kit.publishers.xhs.publish import check_login_valid
        else:
            return {"ok": False, "reason": f"unsupported platform: {platform}"}
        try:
            settings = load_settings(account=account)
        except TypeError:
            # Parallel refactor may not yet have landed; fall back to the
            # legacy no-arg signature so doctor still runs.
            settings = load_settings()
        return {"ok": bool(check_login_valid(settings)), "account": account}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": str(exc), "account": account}


def _discover_accounts(platform: str) -> list[str]:
    """Lazily import the platform's list_accounts() helper, returning ["default"] on failure."""
    try:
        if platform == "douyin":
            from broadcast_kit.publishers.douyin.config import list_accounts  # type: ignore
        elif platform == "xhs":
            from broadcast_kit.publishers.xhs.config import list_accounts  # type: ignore
        else:
            return ["default"]
        accounts = list(list_accounts() or [])
        return accounts or ["default"]
    except Exception:  # noqa: BLE001
        return ["default"]


def _per_account_state(state_root: Path, account: str, live_login_check: bool) -> dict[str, Any]:
    block: dict[str, Any] = {
        "account": account,
        "douyin_auth": _auth_file("douyin", state_root, account=account),
        "xhs_auth": _auth_file("xhs", state_root, account=account),
    }
    if live_login_check:
        block["douyin_login"] = _login_check("douyin", account=account)
        block["xhs_login"] = _login_check("xhs", account=account)
    return block


def run(live_login_check: bool = False, account: str = "default", all_accounts: bool = False) -> dict[str, Any]:
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
            "account": account,
            "douyin_auth": _auth_file("douyin", state_root, account=account),
            "xhs_auth": _auth_file("xhs", state_root, account=account),
        },
        "live_login_check": live_login_check,
        "account": account,
        "all_accounts": all_accounts,
    }
    if live_login_check:
        checks["state"]["douyin_login"] = _login_check("douyin", account=account)
        checks["state"]["xhs_login"] = _login_check("xhs", account=account)

    if all_accounts:
        discovered: list[str] = []
        for plat in ("douyin", "xhs"):
            for acct in _discover_accounts(plat):
                if acct not in discovered:
                    discovered.append(acct)
        if not discovered:
            discovered = ["default"]
        checks["accounts"] = {
            "discovered": discovered,
            "rows": [
                _per_account_state(state_root, acct, live_login_check)
                for acct in discovered
            ],
        }

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
