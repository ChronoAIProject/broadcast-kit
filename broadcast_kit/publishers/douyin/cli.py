from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

import typer

from .config import Settings, file_url, load_settings, setup_logging
from .cover_gen import MediaError, generate_covers_from_video
from .manifest import read_manifest, resolve_manifest_path
from .manifest_schema import ManifestError
from .publish import DouyinError, upload_video
from .metrics import fetch_metrics as fetch_metrics_impl


app = typer.Typer(add_completion=False, help="Douyin publisher CLI (publish, fetch-metrics, login).")


FORBIDDEN_PATTERNS = [
    (re.compile(r"来源"), "来源"),
    (re.compile(r"\*"), "*"),
    (re.compile(r"notebooklm", re.IGNORECASE), "notebooklm"),
    (re.compile(r"slidesync", re.IGNORECASE), "slidesync"),
    (re.compile(r"#notebooklm", re.IGNORECASE), "#notebooklm"),
]

DEFAULT_INVENTORY_ID_PATTERN = r"^\|\s*([A-Za-z][A-Za-z0-9_-]+)\b"


def _scan_caption(caption: str) -> list[str]:
    return [label for pattern, label in FORBIDDEN_PATTERNS if pattern.search(caption)]


def _parse_tz(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(f"--schedule-publish-at must include timezone: {value}")
    return parsed


def _inventory_ids(settings: Settings) -> set[str]:
    if not settings.inventory_file or not settings.inventory_file.exists():
        return set()
    pattern = re.compile(os.getenv("DOUYIN_INVENTORY_ID_PATTERN", DEFAULT_INVENTORY_ID_PATTERN))
    text = settings.inventory_file.read_text(encoding="utf-8")
    ids: set[str] = set()
    for line in text.splitlines():
        match = pattern.search(line)
        if match:
            ids.add(match.group(1))
    return ids


def _print_report(
    manifest_path: Path,
    video_path: Path,
    schedule_at: str | None,
    douyin_schedule_at: datetime,
    judgement: str,
    cover_verified: bool,
    queue_verified: str,
    queue_txt: Path | None,
    queue_png: Path | None,
    screenshots: list[Path],
    forbidden_hits: list[str],
) -> None:
    cover_str = "True" if cover_verified else "False"
    queue_str = {"true": "True", "false": "False", "partial": "partial", "not_checked": "not_checked"}.get(
        queue_verified, queue_verified
    )
    success = judgement == "success" and cover_verified and queue_verified == "true"
    conclusion = "成功" if success else ("部分成功" if judgement == "success" else "失败")
    typer.echo("")
    typer.echo(f"最终结论:{conclusion}")
    typer.echo("")
    typer.echo("本次任务:")
    typer.echo(f"- manifest: {manifest_path}")
    typer.echo(f"- 视频: {video_path}")
    typer.echo(f"- 内部触发: {schedule_at or '-'}")
    typer.echo(f"- 抖音定时: {douyin_schedule_at.isoformat()}")
    typer.echo("")
    typer.echo("判定三元组:")
    typer.echo(f"- JUDGEMENT: {judgement}")
    typer.echo(f"- COVER_VERIFY: {cover_str}")
    typer.echo(f"- QUEUE_VERIFY: {queue_str}")
    typer.echo("")
    typer.echo("证据:")
    if screenshots:
        typer.echo(f"- publish-after 截图: {file_url(screenshots[-1])}")
    if queue_txt:
        typer.echo(f"- queue 文本: {file_url(queue_txt)}")
    if queue_png:
        typer.echo(f"- queue 截图: {file_url(queue_png)}")
    typer.echo("")
    typer.echo("文案检查:")
    typer.echo(f"- 出现 \"来源\": {'yes' if '来源' in forbidden_hits else 'no'}")
    typer.echo(f"- 出现 \"*\": {'yes' if '*' in forbidden_hits else 'no'}")
    typer.echo(
        "- 出现 notebooklm/SlideSync: "
        + ("yes" if any(item in forbidden_hits for item in ("notebooklm", "slidesync", "#notebooklm")) else "no")
    )
    if not success:
        typer.echo("")
        typer.echo("如果失败:")
        stage = (
            "judgement"
            if judgement != "success"
            else ("cover" if not cover_verified else "queue")
        )
        typer.echo(f"- 失败阶段: {stage}")
        typer.echo(f"- 失败原因: judgement={judgement}, cover_verify={cover_str}, queue_verify={queue_str}")
        typer.echo("- 下一步: 不要继续发布下一条;查看证据后人工恢复")


@app.command("publish")
def publish_command(
    manifest: Path = typer.Option(..., "--manifest", exists=True, file_okay=True, dir_okay=False),
    schedule_publish_at: str = typer.Option(..., "--schedule-publish-at", help="ISO 8601 with timezone"),
    autogen_cover: bool = typer.Option(True, "--autogen-cover/--no-autogen-cover"),
    cover_at_seconds: float = typer.Option(6.0, "--cover-at-seconds"),
    force_republish: bool = typer.Option(False, "--force-republish"),
    submit_publish: bool = typer.Option(True, "--submit-publish/--dry-run"),
) -> None:
    setup_logging()
    settings = load_settings()
    manifest_path = manifest.expanduser().resolve()

    try:
        item = read_manifest(manifest_path)
    except ManifestError as exc:
        typer.echo(f"MANIFEST_INVALID: {exc}")
        raise typer.Exit(code=2) from exc

    inventory_ids = _inventory_ids(settings)
    if str(item.id) in inventory_ids and not force_republish:
        typer.echo(f"REFUSE_REPUBLISH: id={item.id} already in {settings.inventory_file} (pass --force-republish to override)")
        raise typer.Exit(code=2)

    hits = _scan_caption(item.caption)
    if hits:
        typer.echo(f"FORBIDDEN_HIT: {','.join(hits)}")
        raise typer.Exit(code=2)

    try:
        douyin_at = _parse_tz(schedule_publish_at)
    except ValueError as exc:
        typer.echo(f"SCHEDULE_INVALID: {exc}")
        raise typer.Exit(code=2) from exc

    video_path = resolve_manifest_path(manifest_path, item.video_file)
    if not (video_path and video_path.exists()):
        typer.echo(f"VIDEO_MISSING: {item.video_file}")
        raise typer.Exit(code=2)

    cover_h = resolve_manifest_path(manifest_path, item.cover_horizontal_file)
    cover_v = resolve_manifest_path(manifest_path, item.cover_vertical_file)
    need_gen = (cover_h is None or not cover_h.exists()) or (cover_v is None or not cover_v.exists())
    if need_gen and autogen_cover:
        try:
            cover_h, cover_v = generate_covers_from_video(video_path, manifest_path.parent, at_seconds=cover_at_seconds)
            typer.echo("cover: auto-generated from video frame")
        except MediaError as exc:
            typer.echo(f"COVER_AUTOGEN_FAILED: {exc}")
            raise typer.Exit(code=2) from exc
    elif need_gen:
        typer.echo("COVER_MISSING and --no-autogen-cover")
        raise typer.Exit(code=2)

    slug = str(item.id)
    try:
        result = upload_video(
            settings=settings,
            video_path=video_path,
            title=item.title,
            description=item.caption,
            cover_horizontal=cover_h,
            cover_vertical=cover_v,
            submit_publish=submit_publish,
            scheduled_publish_at=douyin_at,
            queue_verify_title=item.title,
            queue_verify_slug=slug,
        )
    except DouyinError as exc:
        typer.echo("JUDGEMENT: failed")
        typer.echo(f"DETAIL: {exc}")
        raise typer.Exit(code=1) from exc

    _print_report(
        manifest_path=manifest_path,
        video_path=video_path,
        schedule_at=item.schedule_at,
        douyin_schedule_at=douyin_at,
        judgement=result.verdict,
        cover_verified=result.cover_verified,
        queue_verified=result.queue_verified,
        queue_txt=result.queue_evidence_txt,
        queue_png=result.queue_evidence_png,
        screenshots=result.screenshots,
        forbidden_hits=hits,
    )

    triple_ok = (
        result.verdict == "success"
        and result.cover_verified
        and result.queue_verified == "true"
    )
    if not triple_ok:
        raise typer.Exit(code=1)


@app.command("fetch-metrics")
def fetch_metrics_command(
    days: int = typer.Option(7, "--days", min=1),
    account: str = typer.Option("default", "--account"),
) -> None:
    setup_logging()
    settings = load_settings()
    path = fetch_metrics_impl(settings, days=days, account=account)
    typer.echo(f"metrics: {file_url(path)}")


@app.command("login")
def login_command(
    fresh: bool = typer.Option(False, "--fresh", help="Force re-login and overwrite storage state"),
) -> None:
    setup_logging()
    settings = load_settings()
    from .publish import check_login_valid, interactive_login

    if fresh:
        path = interactive_login(settings, fresh=True)
        typer.echo(f"saved: {file_url(path)}")
        return
    valid = check_login_valid(settings)
    typer.echo("valid" if valid else "expired")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
