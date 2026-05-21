"""Top-K miss analysis: why did the winners win, and what should this draft change?

Pipeline (v1, no embeddings):

1. Load the per-platform jsonl corpus at ``state/corpus/<platform>.jsonl``.
2. Filter to records snapshotted within ``window_days`` of now.
3. Rank by the Phoenix composite (via ``rank_records``) and take top K.
4. Ask an LLM, given the top K and the new draft, to diff-explain the gap and
   emit concrete revisions plus hook/title examples. Strict JSON in/out.

Empty / under-populated corpora short-circuit before any LLM call.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .base import Draft, OptimizerError, Platform
from .engagement_score import rank_records
from .llm import LLMConfig, call_llm_json


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class MissAnalysisReport:
    """Result of comparing a draft against the platform's recent winners."""

    platform: Platform
    top_performers: list[dict[str, Any]]
    diff_insights: str
    concrete_revisions: list[str] = field(default_factory=list)
    recommended_hook_examples: list[str] = field(default_factory=list)
    recommended_title_examples: list[str] = field(default_factory=list)
    raw_llm: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "top_performers": self.top_performers,
            "diff_insights": self.diff_insights,
            "concrete_revisions": self.concrete_revisions,
            "recommended_hook_examples": self.recommended_hook_examples,
            "recommended_title_examples": self.recommended_title_examples,
            "raw_llm": self.raw_llm,
        }


# ---------------------------------------------------------------------------
# Corpus IO
# ---------------------------------------------------------------------------


def _default_corpus_root() -> Path:
    return Path(os.getenv("BROADCAST_KIT_STATE_DIR", "./state")) / "corpus"


def _parse_snapshot_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    # ``datetime.fromisoformat`` handles ``2026-05-19T12:34:56+00:00``. Also
    # accept the trailing-Z form that some collectors emit.
    text = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_corpus(
    platform: Platform,
    *,
    root: Path | None = None,
    window_days: int = 30,
) -> list[dict[str, Any]]:
    """Read ``state/corpus/<platform>.jsonl`` and keep recent records.

    - Missing directory or file: returns ``[]`` (no auto-create).
    - Records with no parseable ``snapshot_at`` are kept (treated as recent).
    - Malformed json lines are skipped silently.
    """
    corpus_root = root if root is not None else _default_corpus_root()
    path = corpus_root / f"{platform}.jsonl"
    if not path.exists():
        return []

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=window_days)
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            snap = _parse_snapshot_at(rec.get("snapshot_at"))
            if snap is not None and snap < cutoff:
                continue
            records.append(rec)
    return records


def top_performers(
    platform: Platform,
    *,
    k: int = 5,
    window_days: int = 30,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Load the corpus, Phoenix-rank, return the top ``k`` annotated records."""
    records = load_corpus(platform, root=root, window_days=window_days)
    if not records:
        return []
    ranked = rank_records(records, scorer="phoenix")
    return ranked[: max(0, k)]


# ---------------------------------------------------------------------------
# LLM diff-explain
# ---------------------------------------------------------------------------


def _compact_performer(record: dict[str, Any]) -> dict[str, Any]:
    """Trim a record down to the fields the LLM actually needs."""
    metrics = record.get("metrics")
    if not isinstance(metrics, dict):
        # Flat record — keep only numeric-looking keys to avoid blowing the prompt.
        metrics = {
            key: value
            for key, value in record.items()
            if isinstance(value, (int, float)) and not key.startswith("_")
        }
    body = record.get("body") or record.get("caption") or record.get("content") or ""
    return {
        "rank": record.get("_rank"),
        "score": round(float(record.get("_score", 0.0)), 4),
        "content_id": record.get("content_id"),
        "title": record.get("title"),
        "body": (body[:400] + "…") if isinstance(body, str) and len(body) > 400 else body,
        "metrics": metrics,
        "snapshot_at": record.get("snapshot_at"),
        "top_comments": record.get("top_comments", [])[:5] if isinstance(record.get("top_comments"), list) else [],
    }


_SYSTEM_PROMPT_TEMPLATE = (
    "You are a content growth analyst. Given top-performing posts on {platform} "
    "and a new draft, explain concretely why the winners outperformed and what the "
    "draft should change to close the gap. Be specific — cite hooks, titles, "
    "structural moves, and audience cues from the winners. Avoid platitudes. "
    "Return STRICT JSON matching the schema described in the user message. "
    "No prose outside the JSON object."
)


def _build_user_prompt(draft: Draft, performers: list[dict[str, Any]]) -> str:
    compact = [_compact_performer(rec) for rec in performers]
    schema_hint = {
        "diff_insights": "string — 1-2 paragraphs explaining why winners outperformed and what the draft is missing",
        "concrete_revisions": ["string — actionable rewrite suggestion", "…"],
        "recommended_hook_examples": ["string — 2-3 hook patterns extracted from winners"],
        "recommended_title_examples": ["string — 2-3 title patterns extracted from winners"],
    }
    return (
        "PLATFORM: " + draft.platform + "\n\n"
        "TOP PERFORMERS (most recent window, ranked by Phoenix composite):\n"
        + json.dumps(compact, ensure_ascii=False, indent=2)
        + "\n\nNEW DRAFT (under review):\n"
        + json.dumps(
            {
                "title": draft.title,
                "body": draft.body,
                "hashtags": draft.hashtags,
                "context": draft.context,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n\nReturn JSON with this exact shape:\n"
        + json.dumps(schema_hint, ensure_ascii=False, indent=2)
    )


def _coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)]


def analyze(
    draft: Draft,
    *,
    k: int = 5,
    window_days: int = 30,
    corpus_root: Path | None = None,
    config: LLMConfig | None = None,
) -> MissAnalysisReport:
    """End-to-end: load top-K winners for the draft's platform, ask the LLM why
    they beat the draft, and return a structured ``MissAnalysisReport``.

    If the corpus is empty or too small, skip the LLM call and return an empty
    report with ``diff_insights="insufficient corpus"``.
    """
    performers = top_performers(
        draft.platform,
        k=k,
        window_days=window_days,
        root=corpus_root,
    )
    if not performers:
        return MissAnalysisReport(
            platform=draft.platform,
            top_performers=[],
            diff_insights="insufficient corpus",
        )

    system = _SYSTEM_PROMPT_TEMPLATE.format(platform=draft.platform)
    user = _build_user_prompt(draft, performers)
    raw = call_llm_json(system, user, config=config)

    diff_insights = raw.get("diff_insights")
    if not isinstance(diff_insights, str) or not diff_insights.strip():
        raise OptimizerError(
            "miss_analysis: LLM response missing 'diff_insights' string; "
            f"keys={sorted(raw.keys())!r}"
        )

    return MissAnalysisReport(
        platform=draft.platform,
        top_performers=performers,
        diff_insights=diff_insights.strip(),
        concrete_revisions=_coerce_str_list(raw.get("concrete_revisions")),
        recommended_hook_examples=_coerce_str_list(raw.get("recommended_hook_examples")),
        recommended_title_examples=_coerce_str_list(raw.get("recommended_title_examples")),
        raw_llm=raw,
    )
