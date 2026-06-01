"""Discourse publisher CLI · typer."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .config import file_url, list_accounts, load_settings, setup_logging
from .manifest import read_manifest
from .manifest_schema import ManifestError
from .publish import (
    DiscourseError,
    DiscourseLoginExpiredError,
    check_login_valid,
    interactive_login,
    shadowban_check,
    submit_reply,
)


app = typer.Typer(add_completion=False, help="Discourse publisher CLI · generic for any instance (n8n forum / huggingface / etc).")


@app.command("publish")
def publish_command(
    manifest: Path = typer.Option(..., "--manifest", exists=True, file_okay=True, dir_okay=False),
    submit_publish: bool = typer.Option(True, "--submit-publish/--dry-run"),
    account: str = typer.Option("default", "--account", help="Account label"),
) -> None:
    setup_logging()
    manifest_path = manifest.expanduser().resolve()
    try:
        item = read_manifest(manifest_path)
    except ManifestError as exc:
        typer.echo(f"MANIFEST_INVALID: {exc}")
        raise typer.Exit(code=2) from exc

    settings = load_settings(account=account, instance_url=item.instance_url)
    try:
        result = submit_reply(
            settings=settings,
            topic_url=item.topic_url,
            body=item.body,
            dry_run=not submit_publish,
        )
    except DiscourseLoginExpiredError as exc:
        typer.echo("JUDGEMENT: session-expired")
        typer.echo(f"DETAIL: {exc}")
        typer.echo(
            f"REMEDY: python -m broadcast_kit.publishers.discourse.cli login --fresh "
            f"--account {account} --instance {item.instance_url}"
        )
        raise typer.Exit(code=3) from exc
    except DiscourseError as exc:
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
    instance: str = typer.Option(..., "--instance", help="Discourse instance URL · e.g. https://community.n8n.io"),
    fresh: bool = typer.Option(False, "--fresh", help="Force re-login and overwrite storage state"),
    account: str = typer.Option("default", "--account"),
) -> None:
    setup_logging()
    settings = load_settings(account=account, instance_url=instance)
    if fresh:
        path = interactive_login(settings, fresh=True)
        typer.echo(f"saved: {file_url(path)}")
        return
    valid = check_login_valid(settings)
    typer.echo("valid" if valid else "expired")


@app.command("accounts")
def accounts_command() -> None:
    setup_logging()
    accounts = list_accounts()
    if not accounts:
        typer.echo("(no profiles · run `login --fresh --account <handle> --instance <url>` first)")
        return
    for a in accounts:
        typer.echo(a)


@app.command("doctor")
def doctor_command(
    instance: str = typer.Option(..., "--instance"),
    account: str = typer.Option("default", "--account"),
) -> None:
    """Health check · runs check_login_valid."""
    setup_logging()
    settings = load_settings(account=account, instance_url=instance)
    typer.echo(f"account: {account}")
    typer.echo(f"instance: {instance}")
    typer.echo(f"auth_state path: {settings.discourse_auth_state}")
    typer.echo(f"auth_state exists: {settings.discourse_auth_state.exists()}")
    if settings.discourse_auth_state.exists():
        valid = check_login_valid(settings)
        typer.echo(f"live session: {'valid' if valid else 'expired'}")
    typer.echo("✓ doctor done")


@app.command("shadowban-check")
def shadowban_check_command(
    posted_url: str = typer.Argument(...),
    account: str = typer.Option(None, "--account", help="Username to look for in topic post-list"),
) -> None:
    """Check if posted reply is staged-for-review / hidden via anon Topic JSON API."""
    setup_logging()
    result = shadowban_check(posted_url, account)
    typer.echo(json.dumps(result, indent=2))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
