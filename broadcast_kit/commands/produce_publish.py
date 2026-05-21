"""End-to-end orchestrator: existing media or NotebookLM -> SlideSync -> publish.

The primary known-good path is: provide a finished video with ``--video-file``,
polish/validate the draft, then publish. The source-to-video path is available
when NotebookLM and SlideSync are installed; if they are not, this command
reports the missing asset gate instead of attempting a broken publish.

This module imports the NotebookLM adapter lazily so that this module imports
cleanly even when the parallel notebooklm adapter has not yet shipped.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from broadcast_kit import publishers
from broadcast_kit.adapters import slidesync
from broadcast_kit.optimizers import (
    Draft,
    OptimizerError,
    analyze,
    polish,
    review,
)


SUPPORTED_PLATFORMS = {"douyin", "xhs", "x"}


@dataclass
class StageResult:
    name: str
    status: str  # "ok" | "skipped" | "error" | "hold" | "rejected"
    detail: str = ""
    artifacts: dict[str, Any] = field(default_factory=dict)


def _title_from_input(input_path: Path) -> str:
    stem = input_path.stem if input_path.is_file() else input_path.name
    return stem.replace("-", " ").replace("_", " ").strip() or input_path.name


def _build_publish_job(
    platform: str,
    draft: Draft,
    video_path: Optional[Path],
    schedule: Optional[str],
    content_id: str,
) -> dict[str, Any]:
    """Produce a per-platform publish-job dict matching each publisher's manifest schema."""
    title = (draft.title or "").strip() or "Untitled"
    body = (draft.body or "").strip() or title
    hashtags = list(draft.hashtags or [])

    if platform == "douyin":
        return {
            "id": content_id,
            "platform": "douyin",
            "title": title[:55],
            "caption": body,
            "publish_mode": "scheduled" if schedule else "manual",
            "video_file": str(video_path) if video_path else None,
            "topics": hashtags,
            "schedule_at": schedule,
            "douyin_schedule_publish_at": schedule,
        }
    if platform == "xhs":
        return {
            "id": content_id,
            "platform": "xhs",
            "title": title[:20],
            "body": body[:1000],
            "topics": hashtags,
            "asset_paths": [str(video_path)] if video_path else [],
            "asset_kind": "video" if video_path else "image",
        }
    if platform == "x":
        return {
            "platform": "x",
            "content_id": content_id,
            "title": title,
            "body": body,
        }
    return {"platform": platform, "title": title, "body": body}


def _platform_asset_block(platform: str, video_path: Optional[Path]) -> str | None:
    if platform == "douyin" and not video_path:
        return "no publishable video; provide --video-file or complete NotebookLM+SlideSync"
    if platform == "xhs" and not video_path:
        return "no publishable video/image asset; provide --video-file or publish a manifest with image asset_paths"
    return None


def _run_notebooklm(input_path: Path, output_dir: Path, dry_run: bool) -> tuple[StageResult, Any]:
    try:
        from broadcast_kit.adapters.notebooklm import generate as nb_generate  # type: ignore
    except ImportError as exc:
        return StageResult("notebooklm", "skipped", f"adapter unavailable: {exc}", {}), None
    try:
        artifacts = nb_generate(input_path, output_dir / "notebooklm", dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        return StageResult("notebooklm", "error", f"notebooklm failed: {exc}", {}), None
    art_dict = {
        "slides": str(getattr(artifacts, "slide_deck_path", "") or ""),
        "audio": str(getattr(artifacts, "audio_path", "") or ""),
        "transcript": str(getattr(artifacts, "transcript_path", "") or ""),
    }
    status = str(getattr(artifacts, "status", "ok") or "ok")
    detail = str(getattr(artifacts, "detail", "") or "")
    return StageResult("notebooklm", status, detail, art_dict), artifacts


def _run_slidesync(
    nb_artifacts: Any, output_dir: Path, dry_run: bool
) -> tuple[StageResult, Optional[Path]]:
    slide_path = getattr(nb_artifacts, "slide_deck_path", None) if nb_artifacts else None
    audio_path = getattr(nb_artifacts, "audio_path", None) if nb_artifacts else None
    if not (slide_path and audio_path):
        return StageResult("slidesync", "skipped", "missing notebooklm outputs", {}), None

    input_dir = Path(slide_path).parent
    project_dir = output_dir / "slidesync"
    project_dir.mkdir(parents=True, exist_ok=True)
    try:
        preflight = slidesync.preflight(input_dir, project_dir, "none", dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        return StageResult("slidesync", "error", f"preflight failed: {exc}", {}), None

    final_video = project_dir / "output" / "final.mp4"
    if dry_run:
        return (
            StageResult(
                "slidesync",
                "ok",
                "dry_run preflight only",
                {"preflight": preflight, "planned_video": str(final_video)},
            ),
            None,
        )

    try:
        generate = slidesync.generate(input_dir, project_dir, "none")
    except Exception as exc:  # noqa: BLE001
        return StageResult("slidesync", "error", f"generate failed: {exc}", {}), None

    video_path = final_video if final_video.exists() else None
    return (
        StageResult(
            "slidesync",
            "ok" if video_path else "error",
            "video generated" if video_path else "no video produced",
            {"result": generate, "video": str(video_path) if video_path else None},
        ),
        video_path,
    )


def run(
    input_path: Path,
    platforms_csv: str,
    output_dir: Path,
    schedule: Optional[str],
    skip: list[str],
    dry_run: bool,
    video_file: Optional[Path] = None,
) -> dict:
    platforms = [p.strip() for p in platforms_csv.split(",") if p.strip()]
    unknown = [p for p in platforms if p not in SUPPORTED_PLATFORMS]
    skip_set = set(skip or [])
    output_dir.mkdir(parents=True, exist_ok=True)

    stages: list[StageResult] = []
    publish_block: str | None = None

    if unknown:
        stages.append(
            StageResult(
                "setup",
                "error",
                f"unsupported platforms: {unknown}; allowed={sorted(SUPPORTED_PLATFORMS)}",
                {},
            )
        )
        platforms = [p for p in platforms if p in SUPPORTED_PLATFORMS]

    if not platforms:
        stages.append(StageResult("setup", "error", "no valid platforms supplied", {}))
        return {
            "status": "error",
            "stages": [asdict(s) for s in stages],
            "platforms": [],
            "dry_run": dry_run,
        }

    provided_video = video_file.resolve() if video_file else None
    if provided_video and not provided_video.exists():
        stages.append(
            StageResult("assets", "error", f"--video-file not found: {provided_video}", {})
        )
        provided_video = None
    elif provided_video:
        stages.append(
            StageResult(
                "assets",
                "ok",
                "using provided publishable video",
                {"video_file": str(provided_video)},
            )
        )

    # Stage 1: NotebookLM
    if provided_video:
        stages.append(
            StageResult(
                "notebooklm",
                "skipped",
                "not needed because --video-file was provided",
                {},
            )
        )
        nb_artifacts = None
    elif "notebooklm" in skip_set:
        stages.append(StageResult("notebooklm", "skipped", "skipped by flag", {}))
        nb_artifacts = None
    else:
        stage, nb_artifacts = _run_notebooklm(input_path, output_dir, dry_run)
        stages.append(stage)

    # Stage 2: SlideSync
    if provided_video:
        stages.append(
            StageResult(
                "slidesync",
                "skipped",
                "not needed because --video-file was provided",
                {"video": str(provided_video)},
            )
        )
        video_path = provided_video
    elif "slidesync" in skip_set:
        stages.append(StageResult("slidesync", "skipped", "skipped by flag", {}))
        video_path: Optional[Path] = None
    else:
        stage, video_path = _run_slidesync(nb_artifacts, output_dir, dry_run)
        stages.append(stage)

    # Stage 3: build seed draft
    seed_title = _title_from_input(input_path)
    seed_body = f"Generated from {input_path.name}"
    draft = Draft(
        platform=platforms[0],  # type: ignore[arg-type]
        title=seed_title,
        body=seed_body,
        hashtags=[],
        context={"video_path": str(video_path) if video_path else None, "source": str(input_path)},
    )

    # Stage 4: content_brain
    if "content_brain" in skip_set:
        stages.append(StageResult("content_brain", "skipped", "skipped by flag", {}))
    else:
        try:
            brain = analyze(draft)
            decision = brain.publish_decision
            artifacts = {"report": brain.to_dict()}
            if brain.recommended_title:
                draft.title = brain.recommended_title
            if decision == "hold":
                stages.append(
                    StageResult("content_brain", "hold", "content_brain decision=hold", artifacts)
                )
                publish_block = "content_brain hold"
            else:
                stages.append(StageResult("content_brain", decision, "", artifacts))
        except (OptimizerError, Exception) as exc:  # noqa: BLE001
            stages.append(StageResult("content_brain", "skipped", f"unavailable: {exc}", {}))

    # Stage 5: market_role polish (per first platform)
    if "market_role" in skip_set or publish_block:
        if publish_block:
            stages.append(StageResult("market_role", "skipped", "blocked upstream", {}))
        else:
            stages.append(StageResult("market_role", "skipped", "skipped by flag", {}))
    else:
        try:
            report = polish(draft, role=draft.platform)
            draft = report.as_draft(platform=draft.platform, context=draft.context)
            stages.append(
                StageResult("market_role", "ok", f"role={report.role}", {"report": report.to_dict()})
            )
        except (OptimizerError, Exception) as exc:  # noqa: BLE001
            stages.append(StageResult("market_role", "skipped", f"unavailable: {exc}", {}))

    # Stage 6: reviewer
    if "reviewer" in skip_set or publish_block:
        if publish_block:
            stages.append(StageResult("reviewer", "skipped", "blocked upstream", {}))
        else:
            stages.append(StageResult("reviewer", "skipped", "skipped by flag", {}))
    else:
        try:
            rev = review(draft, max_rounds=2)
            artifacts = {"report": rev.to_dict()}
            if not rev.recommend_publish:
                stages.append(
                    StageResult(
                        "reviewer",
                        "rejected",
                        f"composite={rev.composite_score} threshold={rev.publish_threshold}",
                        artifacts,
                    )
                )
                publish_block = "reviewer rejected"
            else:
                stages.append(StageResult("reviewer", "ok", "recommend_publish=true", artifacts))
        except (OptimizerError, Exception) as exc:  # noqa: BLE001
            stages.append(StageResult("reviewer", "skipped", f"unavailable: {exc}", {}))

    # Stage 7: publish per platform
    if "publish" in skip_set:
        stages.append(StageResult("publish", "skipped", "skipped by flag", {}))
    elif publish_block:
        stages.append(StageResult("publish", "skipped", f"blocked: {publish_block}", {}))
    else:
        content_id = input_path.stem or input_path.name
        for plat in platforms:
            asset_block = _platform_asset_block(plat, video_path)
            if asset_block:
                stages.append(StageResult(f"publish:{plat}", "error", f"blocked: {asset_block}", {}))
                continue
            per_draft = Draft(
                platform=plat,  # type: ignore[arg-type]
                title=draft.title,
                body=draft.body,
                hashtags=list(draft.hashtags),
                context=dict(draft.context),
            )
            job = _build_publish_job(plat, per_draft, video_path, schedule, content_id)
            try:
                result = publishers.publish(plat, job, dry_run=dry_run, config={})
                status = str(result.get("status", "ok"))
                detail = str(result.get("detail") or result.get("reason") or "")
                stages.append(StageResult(f"publish:{plat}", status, detail, result))
            except Exception as exc:  # noqa: BLE001
                stages.append(
                    StageResult(f"publish:{plat}", "error", f"publish failed: {exc}", {})
                )

    all_green = all(s.status in {"ok", "skipped", "publish", "weak_test", "success", "dry_run"} for s in stages)
    overall = "ok" if all_green else "partial"
    if publish_block and "publish" not in skip_set:
        overall = "blocked"

    return {
        "status": overall,
        "platforms": platforms,
        "dry_run": dry_run,
        "video_file": str(video_path) if video_path else None,
        "block_reason": publish_block,
        "stages": [asdict(s) for s in stages],
    }


__all__ = ["run", "StageResult", "SUPPORTED_PLATFORMS"]
