from __future__ import annotations

from pathlib import Path

from broadcast_kit.adapters import slidesync
from broadcast_kit.contracts import ContractError, validate_slidesync_job


def run(input_dir: Path, project_dir: Path, llm_provider: str, dry_run: bool) -> dict:
    if llm_provider not in {"none", "openai_compatible", "codex_cli"}:
        raise ContractError("llm_provider must be none, openai_compatible, or codex_cli")
    if not input_dir.exists() or not input_dir.is_dir():
        raise ContractError(f"input_dir must be an existing directory: {input_dir}")
    project_dir.mkdir(parents=True, exist_ok=True)

    result = slidesync.preflight(input_dir, project_dir, llm_provider, dry_run=True)
    job = {
        "job_id": "slidesync_" + input_dir.name,
        "status": "dry_run" if dry_run else "draft",
        "work_dir": str(project_dir / "work"),
        "output_dir": str(project_dir / "output"),
        "artifacts": {
            "transcript_raw": "work/transcript.raw.json",
            "transcript": "work/transcript.json",
            "diarization": "work/diarization.json",
            "slide_index": "work/slide_index.json",
            "timeline_draft": "work/timeline.draft.json",
            "timeline_reviewed": "work/timeline.reviewed.json",
            "draft_video": "output/draft.mp4",
            "final_video": "output/final.mp4",
            "subtitles": "output/subtitles.srt",
            "qa_report": "output/qa-report.json",
        },
    }
    validate_slidesync_job(job)
    if not dry_run:
        result = slidesync.generate(input_dir, project_dir, llm_provider)
    return {"status": job["status"], "slidesync": result, "slidesync_job": job}
