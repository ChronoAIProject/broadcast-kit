from __future__ import annotations

from pathlib import Path

import typer

from .config import file_url, list_accounts, load_settings, setup_logging
from .manifest import read_manifest, resolve_asset_paths
from .manifest_schema import ManifestError
from .publish import XhsError, check_login_valid, interactive_login, upload_note


app = typer.Typer(add_completion=False, help="Xiaohongshu (XHS) publisher CLI.")


@app.command("publish")
def publish_command(
    manifest: Path = typer.Option(..., "--manifest", exists=True, file_okay=True, dir_okay=False),
    submit_publish: bool = typer.Option(True, "--submit-publish/--dry-run"),
    account: str = typer.Option("default", "--account", help="Account label under state/xhs/<account>/"),
) -> None:
    setup_logging()
    settings = load_settings(account=account)
    manifest_path = manifest.expanduser().resolve()
    try:
        item = read_manifest(manifest_path)
    except ManifestError as exc:
        typer.echo(f"MANIFEST_INVALID: {exc}")
        raise typer.Exit(code=2) from exc

    asset_paths = resolve_asset_paths(manifest_path, item.asset_paths)
    missing = [p for p in asset_paths if not p.exists()]
    if missing:
        typer.echo(f"ASSET_MISSING: {missing}")
        raise typer.Exit(code=2)

    try:
        result = upload_note(
            settings=settings,
            asset_paths=asset_paths,
            title=item.title,
            body=item.body,
            topics=item.topics,
            asset_kind=item.asset_kind,
            submit_publish=submit_publish,
        )
    except XhsError as exc:
        typer.echo("JUDGEMENT: failed")
        typer.echo(f"DETAIL: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo("")
    typer.echo(f"verdict: {result.verdict}")
    typer.echo(f"detail: {result.detail}")
    typer.echo(f"note_url: {result.note_url or '-'}")
    if result.screenshots:
        typer.echo(f"last screenshot: {file_url(result.screenshots[-1])}")
    if result.verdict != "success" and submit_publish:
        raise typer.Exit(code=1)


@app.command("login")
def login_command(
    fresh: bool = typer.Option(False, "--fresh", help="Force re-login and overwrite storage state"),
    account: str = typer.Option("default", "--account", help="Account label under state/xhs/<account>/"),
) -> None:
    setup_logging()
    settings = load_settings(account=account)
    if fresh:
        path = interactive_login(settings, fresh=True)
        typer.echo(f"saved: {file_url(path)}")
        return
    valid = check_login_valid(settings)
    typer.echo("valid" if valid else "expired")


@app.command("accounts")
def accounts_command(
    live_check: bool = typer.Option(
        False,
        "--live-check",
        help="Run check_login_valid for each account (launches headless browser).",
    ),
) -> None:
    """List XHS accounts discovered under state/xhs/*/auth.json."""
    setup_logging()
    entries = list_accounts()
    header = f"{'account':<14} {'auth_exists':<12} {'auth_mtime':<20} {'login_valid'}"
    typer.echo(header)
    if not entries:
        typer.echo("(no accounts found — run `xhs login --fresh --account <label>`)")
        return
    for entry in entries:
        exists_label = "yes" if entry["auth_exists"] else "no"
        mtime_label = entry["auth_mtime"] or "-"
        if live_check and entry["auth_exists"]:
            try:
                settings = load_settings(account=entry["account"])
                login_label = "valid" if check_login_valid(settings) else "expired"
            except Exception as exc:  # noqa: BLE001 — surface error in row, keep listing.
                login_label = f"error: {exc}"
        else:
            login_label = "(run --live-check)"
        typer.echo(
            f"{entry['account']:<14} {exists_label:<12} {mtime_label:<20} {login_label}"
        )


def main() -> None:
    from broadcast_kit._pyver import require_min_python

    require_min_python("broadcast_kit.publishers.xhs.cli")
    app()


if __name__ == "__main__":
    main()
