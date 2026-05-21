from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

try:
    import typer
except ModuleNotFoundError:  # Keep `import broadcast_kit; broadcast_kit.cli.main` usable pre-install.
    typer = None  # type: ignore[assignment]

from broadcast_kit.commands import doc_to_batch, doctor as doctor_cmd, enrich_metrics, fetch_metrics as fetch_metrics_cmd, optimize as optimize_cmd, produce_publish, publish as publish_cmd, registry_to_manifest, render_narration, render_video, setup as setup_cmd
from broadcast_kit.contracts import ContractError


if typer is not None:
    app = typer.Typer(help="Broadcast Kit agent-facing CLI.")

    def _print(data: dict) -> None:
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2))

    def _handle(fn, *args, **kwargs) -> None:
        try:
            _print(fn(*args, **kwargs))
        except ContractError as exc:
            raise typer.BadParameter(str(exc)) from exc

    @app.command("doc-to-batch")
    def doc_to_batch_command(
        input: Path = typer.Option(..., "--input", exists=True, help="Markdown file, directory, or repo path."),
        output_dir: Path = typer.Option(..., "--output-dir", help="Run output folder."),
        platform: str = typer.Option(..., "--platform", help="douyin, xhs, x, or all."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Validate and print plan without writing output."),
    ) -> None:
        _handle(doc_to_batch.run, input, output_dir, platform, dry_run)

    @app.command("render-narration")
    def render_narration_command(
        batch: Path = typer.Option(..., "--batch", exists=True, help="content-batch.json path."),
        item_id: str = typer.Option(..., "--item-id", help="Batch item content_id."),
        variant: str = typer.Option(..., "--variant", help="hook-a, hook-b, brand, or opening."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Validate storyboard contract only."),
    ) -> None:
        _handle(render_narration.run, batch, item_id, variant, dry_run)

    @app.command("render-video")
    def render_video_command(
        input_dir: Path = typer.Option(..., "--input-dir", exists=True, file_okay=False, help="SlideSync inputCase directory."),
        project_dir: Path = typer.Option(..., "--project-dir", help="SlideSync project directory."),
        llm_provider: str = typer.Option("none", "--llm-provider", help="none, openai_compatible, or codex_cli."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Run preflight/plan only."),
    ) -> None:
        _handle(render_video.run, input_dir, project_dir, llm_provider, dry_run)

    @app.command("publish")
    def publish_command(
        platform: str = typer.Option(..., "--platform", help="douyin, xhs, or x."),
        manifest: Path = typer.Option(..., "--manifest", exists=True, help="Publish job or platform manifest."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Validate and plan without live publish."),
        account: str = typer.Option("default", "--account", help="State scope (auth, screenshots, metrics, inventory). Default 'default'."),
    ) -> None:
        _handle(publish_cmd.run, platform, manifest, dry_run, account)

    @app.command("produce-publish")
    def produce_publish_command(
        input: Path = typer.Option(..., "--input", exists=True, help="PDF, markdown file, or directory."),
        platforms: str = typer.Option(..., "--platforms", help="Comma-separated: douyin,xhs[,x]"),
        output_dir: Path = typer.Option(Path("state/produce_publish"), "--output-dir", help="Working directory for artifacts."),
        schedule: Optional[str] = typer.Option(None, "--schedule", help="ISO 8601 with timezone (Douyin requires this)."),
        video_file: Optional[Path] = typer.Option(None, "--video-file", exists=True, dir_okay=False, help="Known-good final video to publish instead of generating one."),
        skip: list[str] = typer.Option([], "--skip", help="Skip a stage: notebooklm, slidesync, content_brain, market_role, reviewer, publish. Repeatable."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Validate every stage without irreversible actions."),
        account: str = typer.Option("default", "--account", help="State scope (auth, screenshots, metrics, inventory). Default 'default'."),
    ) -> None:
        _handle(
            produce_publish.run,
            input,
            platforms,
            output_dir,
            schedule,
            skip,
            dry_run,
            account,
            video_file=video_file,
        )

    @app.command("doctor")
    def doctor_command(
        live_login_check: bool = typer.Option(False, "--live-login-check", help="Open platform pages and verify saved login cookies."),
        account: str = typer.Option("default", "--account", help="State scope (auth, screenshots, metrics, inventory). Default 'default'."),
        all_accounts: bool = typer.Option(False, "--all-accounts", help="Run doctor checks against every discovered account and surface a multi-row table."),
    ) -> None:
        _handle(doctor_cmd.run, live_login_check, account, all_accounts)

    @app.command("registry-to-manifest")
    def registry_to_manifest_command(
        registry: Path = typer.Option(..., "--registry", exists=True, help="publish-registry JSON path."),
        content_id: str = typer.Option(..., "--content-id", help="Registry item content_id."),
        platform: str = typer.Option(..., "--platform", help="douyin, xhs, or x."),
        output: Path = typer.Option(..., "--output", help="Manifest/job output path."),
        schedule_at: Optional[str] = typer.Option(None, "--schedule-at", help="Internal schedule time, ISO 8601."),
        douyin_schedule_publish_at: Optional[str] = typer.Option(None, "--douyin-schedule-publish-at", help="Douyin-side scheduled publish time, ISO 8601."),
        account_label: Optional[str] = typer.Option(None, "--account", help="Account label for publish-job outputs."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Validate and print manifest without writing."),
    ) -> None:
        _handle(
            registry_to_manifest.run,
            registry,
            content_id,
            platform,
            output,
            schedule_at,
            douyin_schedule_publish_at,
            account_label,
            dry_run,
        )

    @app.command("fetch-metrics")
    def fetch_metrics_command(
        platform: str = typer.Option(..., "--platform", help="douyin, xhs, x, youtube, or all."),
        account: str = typer.Option("default", "--account", help="State scope (auth, screenshots, metrics, inventory). Default 'default'."),
        since: Optional[str] = typer.Option(None, "--since", help="Date/window selector."),
        days: Optional[int] = typer.Option(None, "--days", help="Douyin metrics day window."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Validate and plan without scraping."),
    ) -> None:
        _handle(fetch_metrics_cmd.run, platform, account, since, days, dry_run)

    @app.command("enrich-metrics")
    def enrich_metrics_command(
        metrics: Path = typer.Option(..., "--metrics", exists=True, help="Raw metrics JSONL path."),
        output: Path = typer.Option(..., "--output", help="Enriched feedback JSONL output path."),
        registry: Optional[Path] = typer.Option(None, "--registry", exists=True, help="Optional publish-registry JSON path."),
        manifest: list[Path] = typer.Option([], "--manifest", exists=True, help="Optional platform manifest path; repeatable."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Print enrichment preview without writing."),
    ) -> None:
        _handle(enrich_metrics.run, metrics, output, registry, manifest, dry_run)

    @app.command("setup")
    def setup_command(
        yes: bool = typer.Option(False, "--yes", "-y", help="Accept all defaults without asking."),
        skip: list[str] = typer.Option([], "--skip", help="Skip a step: env, llm, douyin, xhs, notebooklm. Repeatable."),
        reset: bool = typer.Option(False, "--reset", help="Re-ask every question even if state/.env exists."),
        tier: Optional[str] = typer.Option(None, "--for", help="Restrict setup to a capability tier: tier1, tier2, or tier3."),
    ) -> None:
        if tier is not None and tier not in {"tier1", "tier2", "tier3"}:
            raise typer.BadParameter("--for must be tier1, tier2, or tier3")
        _handle(setup_cmd.run, yes, skip, reset, tier)

    optimize_app = typer.Typer(help="Optional polish + scoring layer.")
    app.add_typer(optimize_app, name="optimize")

    @optimize_app.command("content-brain")
    def optimize_content_brain(
        draft: Path = typer.Option(..., "--draft", exists=True, help="Draft YAML/JSON: platform, title, body, hashtags."),
    ) -> None:
        _handle(optimize_cmd.content_brain, draft)

    @optimize_app.command("reviewer")
    def optimize_reviewer(
        draft: Path = typer.Option(..., "--draft", exists=True, help="Draft YAML/JSON path."),
        rubric: Optional[Path] = typer.Option(None, "--rubric", exists=True, help="Optional rubric YAML override."),
        max_rounds: int = typer.Option(1, "--max-rounds", min=1, max=4, help="Reviewer revision rounds."),
    ) -> None:
        _handle(optimize_cmd.reviewer, draft, rubric, max_rounds)

    @optimize_app.command("variants")
    def optimize_variants(
        draft: Path = typer.Option(..., "--draft", exists=True, help="Draft YAML/JSON path."),
        n: int = typer.Option(3, "--n", min=2, max=10, help="Number of variants to generate."),
    ) -> None:
        _handle(optimize_cmd.variants, draft, n)

    @optimize_app.command("engagement")
    def optimize_engagement(
        metrics: Path = typer.Option(..., "--metrics", exists=True, help="Metrics JSONL path."),
        scorer: str = typer.Option("phoenix", "--scorer", help="phoenix or heavy_ranker."),
    ) -> None:
        _handle(optimize_cmd.engagement, metrics, scorer)

    def main() -> None:
        from broadcast_kit._pyver import require_min_python

        require_min_python("broadcast_kit.cli")
        app()

else:
    app = None

    def main() -> None:
        from broadcast_kit._pyver import require_min_python

        require_min_python("broadcast_kit.cli")
        raise RuntimeError("Typer is required to run the broadcast-kit CLI. Install the package with pip first.")


__all__ = ["app", "main"]


if __name__ == "__main__":
    main()
