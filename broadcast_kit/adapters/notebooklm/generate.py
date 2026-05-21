"""High-level NotebookLM generate / status / download flows.

The adapter accepts a PDF, a markdown file, a single text file, or a directory
of markdown/text files. Non-PDF inputs are pre-converted to a single PDF using
the first available converter on the system (pandoc -> weasyprint -> markdown_pdf).

Output defaults to ``$BROADCAST_KIT_STATE_DIR/notebooklm/<slug>/`` (or
``./state/notebooklm/<slug>/`` if the env var is unset).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from broadcast_kit.adapters.base import command_plan
from broadcast_kit.optimizers.base import OptimizerError

from . import client


ArtifactKind = Literal["slides", "audio"]

_PDF_INSTALL_HINT = (
    "Cannot convert non-PDF input to PDF: install one of `pandoc`, "
    "`weasyprint` (pip install weasyprint), or `markdown-pdf` (pip install markdown-pdf)."
)


@dataclass
class NotebookLMArtifacts:
    notebook_id: str
    slide_deck_path: Path | None
    audio_path: Path | None
    transcript_path: Path | None
    status: str  # "complete" | "partial" | "error" | "dry_run"
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        out = asdict(self)
        for key in ("slide_deck_path", "audio_path", "transcript_path"):
            value = out.get(key)
            out[key] = str(value) if value is not None else None
        return out


# ---------------------------------------------------------------------------
# Path + slug helpers
# ---------------------------------------------------------------------------


def _state_root() -> Path:
    raw = os.getenv("BROADCAST_KIT_STATE_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.cwd().resolve() / "state"


def _slugify(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"^submitted_\d{4}_", "", stem)
    stem = re.sub(r"^\d{4}_", "", stem)
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_")
    return (stem or "notebooklm")[:60]


def _default_output_dir(input_path: Path) -> Path:
    return _state_root() / "notebooklm" / _slugify(input_path.name)


# ---------------------------------------------------------------------------
# Input normalization: any supported input -> a single PDF on disk
# ---------------------------------------------------------------------------


def _gather_markdown(directory: Path) -> list[Path]:
    files = sorted(
        [
            p
            for p in directory.rglob("*")
            if p.is_file() and p.suffix.lower() in {".md", ".markdown", ".txt"}
        ]
    )
    if not files:
        raise OptimizerError(f"no .md/.markdown/.txt files found under {directory}")
    return files


def _concat_text(files: list[Path]) -> str:
    parts: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="latin-1")
        parts.append(f"# {path.name}\n\n{text}\n")
    return "\n\n".join(parts)


def _convert_markdown_to_pdf(markdown_text: str, dest_pdf: Path) -> None:
    dest_pdf.parent.mkdir(parents=True, exist_ok=True)

    if shutil.which("pandoc"):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
            fh.write(markdown_text)
            tmp_md = Path(fh.name)
        try:
            result = subprocess.run(
                ["pandoc", str(tmp_md), "-o", str(dest_pdf)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=120,
            )
            if result.returncode == 0 and dest_pdf.exists():
                return
            # fall through to next converter
        finally:
            tmp_md.unlink(missing_ok=True)

    try:
        from weasyprint import HTML  # type: ignore

        # Minimal markdown -> HTML by escaping; relies on weasyprint for layout.
        html = "<html><body><pre style='white-space: pre-wrap; font-family: serif;'>" + (
            markdown_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        ) + "</pre></body></html>"
        HTML(string=html).write_pdf(str(dest_pdf))
        if dest_pdf.exists():
            return
    except ModuleNotFoundError:
        pass

    try:
        from markdown_pdf import MarkdownPdf, Section  # type: ignore

        pdf = MarkdownPdf()
        pdf.add_section(Section(markdown_text))
        pdf.save(str(dest_pdf))
        if dest_pdf.exists():
            return
    except ModuleNotFoundError:
        pass

    raise OptimizerError(_PDF_INSTALL_HINT)


def _normalize_input(input_path: Path, work_dir: Path) -> Path:
    """Return a PDF path to upload. Converts markdown/text/dir to PDF in work_dir if needed."""
    if not input_path.exists():
        raise OptimizerError(f"input path does not exist: {input_path}")

    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        return input_path

    if input_path.is_dir():
        files = _gather_markdown(input_path)
        text = _concat_text(files)
        dest = work_dir / f"{_slugify(input_path.name)}.pdf"
        _convert_markdown_to_pdf(text, dest)
        return dest

    if input_path.is_file() and input_path.suffix.lower() in {".md", ".markdown", ".txt"}:
        text = _concat_text([input_path])
        dest = work_dir / f"{_slugify(input_path.name)}.pdf"
        _convert_markdown_to_pdf(text, dest)
        return dest

    raise OptimizerError(
        f"unsupported input type: {input_path} (need .pdf, .md, .markdown, .txt, or a directory)"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate(
    input_path: Path,
    output_dir: Path | None = None,
    kinds: list[ArtifactKind] | None = None,
    *,
    poll_interval_seconds: int = 15,
    max_wait_seconds: int = 600,
    dry_run: bool = False,
) -> NotebookLMArtifacts:
    """Upload ``input_path`` to NotebookLM, generate requested artifacts, download them.

    ``kinds`` defaults to ``["slides", "audio"]``. Set ``dry_run=True`` to emit a
    plan without invoking the CLI. Returns a :class:`NotebookLMArtifacts`.
    """
    kinds = list(kinds) if kinds else ["slides", "audio"]
    invalid = [k for k in kinds if k not in ("slides", "audio")]
    if invalid:
        raise OptimizerError(f"unknown artifact kind(s): {invalid}; expected slides/audio")

    input_path = Path(input_path).expanduser().resolve()
    out_dir = (output_dir or _default_output_dir(input_path)).expanduser().resolve()
    slug = _slugify(input_path.name)

    if dry_run:
        plan = command_plan(
            "notebooklm",
            ["notebooklm", "create", slug, "&&", "notebooklm", "source", "add", str(input_path),
             "&&", "notebooklm", "generate", *kinds,
             "&&", "notebooklm", "download", "audio|slide-deck", str(out_dir)],
            cwd=out_dir,
        )
        return NotebookLMArtifacts(
            notebook_id="dry_run",
            slide_deck_path=(out_dir / f"{slug}_slides.pdf") if "slides" in kinds else None,
            audio_path=(out_dir / f"{slug}_podcast.wav") if "audio" in kinds else None,
            transcript_path=None,
            status="dry_run",
            detail=json.dumps(plan),
        )

    client.ensure_available()

    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = _normalize_input(input_path, out_dir)

    title = slug.replace("_", " ").title()[:60]
    notebook_id = client.create_notebook(title)
    client.add_source(pdf_path)

    if "slides" in kinds:
        client.request_slides()
    if "audio" in kinds:
        client.request_audio()

    poll = client.poll_until_settled(poll_interval_seconds, max_wait_seconds)

    artifacts = _download_into(out_dir, slug, kinds)
    artifacts.notebook_id = notebook_id

    if poll.get("timed_out"):
        artifacts.status = "partial"
        artifacts.detail = f"poll timed out after {max_wait_seconds}s"
    elif int(poll.get("failed", 0)) > 0:
        artifacts.status = "partial"
        artifacts.detail = f"notebooklm reported {poll['failed']} failed artifact(s)"

    _write_manifest(out_dir, slug, input_path, artifacts)
    return artifacts


def list_notebooks() -> list[dict]:
    """Return notebooks as parsed dicts from `notebooklm list` (best-effort)."""
    client.ensure_available()
    raw = client.list_notebooks_raw()
    notebooks: list[dict] = []
    for line in raw.splitlines():
        uuid = client.extract_uuid(line)
        if uuid:
            notebooks.append({"notebook_id": uuid, "raw": line.strip()})
    return notebooks


def status(notebook_id: str) -> dict:
    """Return artifact status for a notebook id (raw CLI output included)."""
    client.ensure_available()
    client.use_notebook(notebook_id)
    raw = client.artifact_list()
    return {
        "notebook_id": notebook_id,
        "completed": raw.count("completed"),
        "in_progress": raw.count("in_progress") + raw.count("pending"),
        "failed": raw.count("failed"),
        "raw": raw,
    }


def download(notebook_id: str, output_dir: Path) -> NotebookLMArtifacts:
    """Download completed artifacts for an existing notebook into ``output_dir``."""
    client.ensure_available()
    client.use_notebook(notebook_id)
    out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = out_dir.name or "notebooklm"
    artifacts = _download_into(out_dir, slug, ["slides", "audio"])
    artifacts.notebook_id = notebook_id
    return artifacts


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _download_into(out_dir: Path, slug: str, kinds: list[ArtifactKind]) -> NotebookLMArtifacts:
    slides_path: Path | None = None
    audio_path: Path | None = None

    if "audio" in kinds:
        target = out_dir / f"{slug}_podcast.wav"
        try:
            if client.download_audio(target):
                audio_path = target
        except OptimizerError:
            pass

    if "slides" in kinds:
        target = out_dir / f"{slug}_slides.pdf"
        try:
            if client.download_slides(target):
                slides_path = target
        except OptimizerError:
            pass

    requested = set(kinds)
    obtained = {k for k, v in {"slides": slides_path, "audio": audio_path}.items() if v}
    if obtained == requested:
        status_ = "complete"
        detail = ""
    elif obtained:
        status_ = "partial"
        detail = f"missing: {sorted(requested - obtained)}"
    else:
        status_ = "error"
        detail = "no artifacts downloaded"

    return NotebookLMArtifacts(
        notebook_id="",
        slide_deck_path=slides_path,
        audio_path=audio_path,
        transcript_path=None,
        status=status_,
        detail=detail,
    )


def _write_manifest(out_dir: Path, slug: str, input_path: Path, artifacts: NotebookLMArtifacts) -> None:
    manifest = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "slug": slug,
        "input_path": str(input_path),
        "notebook_id": artifacts.notebook_id,
        "status": artifacts.status,
        "detail": artifacts.detail,
        "artifacts": {
            "slide_deck_path": str(artifacts.slide_deck_path) if artifacts.slide_deck_path else None,
            "audio_path": str(artifacts.audio_path) if artifacts.audio_path else None,
            "transcript_path": str(artifacts.transcript_path) if artifacts.transcript_path else None,
        },
    }
    (out_dir / f"{slug}_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
