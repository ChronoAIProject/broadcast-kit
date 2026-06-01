"""Reddit publisher CLI · typer."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .config import file_url, list_accounts, load_settings, setup_logging
from .manifest import read_manifest
from .manifest_schema import ManifestError
from .publish import (
    RedditError,
    RedditLoginExpiredError,
    check_login_valid,
    interactive_login,
    shadowban_check,
    submit_comment,
)


app = typer.Typer(add_completion=False, help="Reddit publisher CLI · old.reddit + stealth.")


@app.command("publish")
def publish_command(
    manifest: Path = typer.Option(..., "--manifest", exists=True, file_okay=True, dir_okay=False),
    submit_publish: bool = typer.Option(True, "--submit-publish/--dry-run"),
    account: str = typer.Option("default", "--account", help="Account label under state/reddit/<account>/"),
) -> None:
    setup_logging()
    settings = load_settings(account=account)
    manifest_path = manifest.expanduser().resolve()
    try:
        item = read_manifest(manifest_path)
    except ManifestError as exc:
        typer.echo(f"MANIFEST_INVALID: {exc}")
        raise typer.Exit(code=2) from exc

    try:
        result = submit_comment(
            settings=settings,
            thread_url=item.thread_url,
            body=item.body,
            dry_run=not submit_publish,
        )
    except RedditLoginExpiredError as exc:
        typer.echo("JUDGEMENT: session-expired")
        typer.echo(f"DETAIL: {exc}")
        typer.echo(
            f"REMEDY: python -m broadcast_kit.publishers.reddit.cli login --fresh --account {account}"
        )
        raise typer.Exit(code=3) from exc
    except RedditError as exc:
        typer.echo("JUDGEMENT: failed")
        typer.echo(f"DETAIL: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo("")
    typer.echo(f"verdict: {result.status}")
    typer.echo(f"posted_url: {result.posted_url or '-'}")
    if result.detail:
        typer.echo(f"detail: {result.detail}")


@app.command("login")
def login_command(
    fresh: bool = typer.Option(False, "--fresh", help="Force re-login and overwrite storage state"),
    account: str = typer.Option("default", "--account", help="Account label under state/reddit/<account>/"),
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
    live_check: bool = typer.Option(False, "--live-check", help="Also verify cookie via live navigation"),
) -> None:
    setup_logging()
    accounts = list_accounts()
    if not accounts:
        typer.echo("(no accounts found · run `login --fresh --account <handle>` first)")
        return
    for acct in accounts:
        if live_check:
            settings = load_settings(account=acct)
            status = "valid" if check_login_valid(settings) else "expired"
            typer.echo(f"{acct}\t{status}")
        else:
            typer.echo(acct)


@app.command("doctor")
def doctor_command(
    account: str = typer.Option("default", "--account"),
) -> None:
    """Health check · runs check_login_valid + dry-run a public thread navigation."""
    setup_logging()
    settings = load_settings(account=account)
    typer.echo(f"account: {account}")
    typer.echo(f"auth_state path: {settings.reddit_auth_state}")
    typer.echo(f"auth_state exists: {settings.reddit_auth_state.exists()}")
    if settings.reddit_auth_state.exists():
        valid = check_login_valid(settings)
        typer.echo(f"live session: {'valid' if valid else 'expired'}")
    typer.echo("✓ doctor done")


@app.command("shadowban-check")
def shadowban_check_command(
    posted_url: str = typer.Argument(...),
) -> None:
    """Run anon-fetch shadowban detection on a comment URL."""
    setup_logging()
    result = shadowban_check(posted_url)
    typer.echo(json.dumps(result, indent=2))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
