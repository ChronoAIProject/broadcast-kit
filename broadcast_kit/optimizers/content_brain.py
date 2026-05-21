"""Single-call LLM content brain.

Folds the dayou-content dbskill suite — `/dbs-content`, `/dbs-hook`,
`/dbs-xhs-title`, `/dbs-ai-check` — into one structured call that returns
a :class:`ContentBrainReport`. Platform-aware system prompt, draft as user
prompt, JSON-only response.

Usage::

    from broadcast_kit.optimizers.content_brain import analyze
    report = analyze(Draft(platform="xhs", body="..."))
"""

from __future__ import annotations

from typing import Any, get_args

from .base import (
    ContentBrainReport,
    Draft,
    OptimizerError,
    Platform,
    PublishDecision,
)
from .llm import LLMConfig, call_llm_json


_PUBLISH_DECISIONS: tuple[PublishDecision, ...] = get_args(PublishDecision)
_DEFAULT_DECISION: PublishDecision = "weak_test"


# Per-platform tone notes injected into the system prompt.
_PLATFORM_NOTES: dict[Platform, str] = {
    "xhs": (
        "Platform: Xiaohongshu (小红书).\n"
        "- Chinese, conversational, first-person.\n"
        "- Short, punchy hooks. Each hook ≤ 24 characters when possible.\n"
        "- Titles ≤ 20 characters, no clickbait punctuation spam.\n"
        "- Zero AI taste: avoid 『家人们』『姐妹们』『干货分享』『让我们一起』overused emoji walls.\n"
        "- recommended_title MUST be one of the title_options."
    ),
    "douyin": (
        "Platform: Douyin (抖音) video caption.\n"
        "- Single paragraph caption, Chinese, no hashtag spam (≤ 3 hashtags).\n"
        "- BRIEF v2 forbidden terms — never output: 来源, *, notebooklm, slidesync, #notebooklm.\n"
        "- Titles are video titles: ≤ 30 characters, hook-forward.\n"
        "- recommended_title MUST be one of the title_options."
    ),
    "x": (
        "Platform: X (Twitter) thread.\n"
        "- Thread format: tweets separated by a line containing only '---'.\n"
        "- English or Chinese — match the draft's language.\n"
        "- No thread-summarizer voice: avoid 'In this thread…', 'A thread 🧵', 'Let me explain…'.\n"
        "- title_options here are first-tweet candidates (the hook tweet).\n"
        "- recommended_title is optional; if absent, the caller will fall back to hook_options[0]."
    ),
}


_BASE_ROLE = (
    "You are a senior social-media editor and a brutal AI-taste critic. "
    "You combine four jobs into one pass: content audit (audience + conflict + why-care/why-ignore), "
    "hook generation, title generation, and AI-taste scrubbing. "
    "Be specific. No platitudes. No hedge words."
)


_SCHEMA_BLOCK = """\
Return a single JSON object with EXACTLY these keys (no extras, no nulls):

{
  "audience": string  // who this is for, one sentence, concrete
  "core_conflict": string  // the tension/promise driving the piece, one sentence
  "why_people_will_care": string  // the strongest pull, one sentence
  "why_people_may_ignore": string  // the strongest skip-reason, one sentence
  "hook_options": [string, string, string]  // 3 distinct opening lines, ordered best-first
  "title_options": [string, string, string]  // 3 distinct titles, ordered best-first
  "recommended_title": string  // the single best title (must equal one of title_options on xhs/douyin)
  "ai_taste_issues": [string, ...]  // concrete phrases or patterns from the draft that read as AI
                                     // (em-dash overuse, 'delve into', 'let's explore', 'in conclusion',
                                     //  emoji walls, listicle scaffolding, hedge stacking, etc.)
                                     // empty list if clean
  "risk_notes": [string, ...]  // compliance / safety / factual / platform-policy concerns
                               // empty list if none
  "publish_decision": "publish" | "weak_test" | "hold"
    // publish    = ship as-is, strong piece
    // weak_test  = ship with caveats, monitor signal
    // hold       = needs rework before publishing
}
"""


def _build_system_prompt(platform: Platform) -> str:
    notes = _PLATFORM_NOTES.get(platform, "")
    return f"{_BASE_ROLE}\n\n{notes}\n\n{_SCHEMA_BLOCK}"


def _build_user_prompt(draft: Draft) -> str:
    ctx_lines: list[str] = []
    if draft.context:
        for key, value in draft.context.items():
            ctx_lines.append(f"  {key}: {value}")
    parts = [
        f"PLATFORM: {draft.platform}",
        draft.as_text(),
    ]
    if ctx_lines:
        parts.append("CONTEXT:\n" + "\n".join(ctx_lines))
    parts.append("Analyze and return the JSON object now.")
    return "\n\n".join(parts)


def _coerce_str_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise OptimizerError(f"field '{field_name}' must be a list; got {type(value).__name__}")
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _coerce_str(value: Any, field_name: str, *, required: bool = True) -> str:
    if value is None:
        if required:
            raise OptimizerError(f"field '{field_name}' is required")
        return ""
    if not isinstance(value, str):
        raise OptimizerError(f"field '{field_name}' must be a string; got {type(value).__name__}")
    return value.strip()


def _normalize_decision(value: Any) -> PublishDecision:
    if isinstance(value, str) and value.strip() in _PUBLISH_DECISIONS:
        return value.strip()  # type: ignore[return-value]
    return _DEFAULT_DECISION


def analyze(draft: Draft, *, config: LLMConfig | None = None) -> ContentBrainReport:
    """Run a single structured LLM call combining the dbskill suite.

    Raises :class:`OptimizerError` if the LLM output is malformed.
    """
    if draft.platform not in _PLATFORM_NOTES:
        raise OptimizerError(f"unsupported platform: {draft.platform}")

    system = _build_system_prompt(draft.platform)
    user = _build_user_prompt(draft)
    payload = call_llm_json(system, user, config=config)

    audience = _coerce_str(payload.get("audience"), "audience")
    core_conflict = _coerce_str(payload.get("core_conflict"), "core_conflict")
    why_care = _coerce_str(payload.get("why_people_will_care"), "why_people_will_care")
    why_ignore = _coerce_str(payload.get("why_people_may_ignore"), "why_people_may_ignore")

    hook_options = _coerce_str_list(payload.get("hook_options"), "hook_options")
    if not hook_options:
        raise OptimizerError("hook_options must contain at least one non-empty string")

    title_options = _coerce_str_list(payload.get("title_options"), "title_options")
    if draft.platform in {"xhs", "douyin"} and not title_options:
        raise OptimizerError(
            f"title_options must contain at least one non-empty string for platform={draft.platform}"
        )

    recommended = _coerce_str(payload.get("recommended_title"), "recommended_title", required=False)
    if not recommended:
        if draft.platform == "x":
            recommended = hook_options[0]
        elif title_options:
            recommended = title_options[0]
        else:
            raise OptimizerError(
                f"recommended_title is required for platform={draft.platform}"
            )

    ai_taste_issues = _coerce_str_list(payload.get("ai_taste_issues") or [], "ai_taste_issues")
    risk_notes = _coerce_str_list(payload.get("risk_notes") or [], "risk_notes")
    decision = _normalize_decision(payload.get("publish_decision"))

    return ContentBrainReport(
        audience=audience,
        core_conflict=core_conflict,
        why_people_will_care=why_care,
        why_people_may_ignore=why_ignore,
        hook_options=hook_options,
        title_options=title_options or [recommended],
        recommended_title=recommended,
        ai_taste_issues=ai_taste_issues,
        risk_notes=risk_notes,
        publish_decision=decision,
    )


def adopted_summary(report: ContentBrainReport) -> list[str]:
    """Short bullets summarizing what the next-stage editor should incorporate."""
    bullets: list[str] = [
        f"Audience: {report.audience}",
        f"Core conflict: {report.core_conflict}",
        f"Why care: {report.why_people_will_care}",
        f"Recommended title: {report.recommended_title}",
        f"Top hook: {report.hook_options[0]}",
        f"Decision: {report.publish_decision}",
    ]
    if report.ai_taste_issues:
        preview = "; ".join(report.ai_taste_issues[:3])
        bullets.append(f"Scrub AI taste: {preview}")
    if report.risk_notes:
        preview = "; ".join(report.risk_notes[:3])
        bullets.append(f"Risks: {preview}")
    return bullets
