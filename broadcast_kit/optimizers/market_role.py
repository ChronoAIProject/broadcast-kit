"""Marketing role-agent polish pass.

Loads a platform-specific marketing strategist persona (vendored under
`role_agents/` as Markdown files with YAML frontmatter) and applies it to
a `Draft` via a single LLM call. The role's prompt body becomes the LLM
system prompt; the draft + a strict JSON contract becomes the user message.

Two entry points:

- `polish(draft, role=...)` — single pass with one role
- `chain_polish(draft, roles=[...])` — sequential passes, each role polishing
  the previous role's output. Typical chain: `<platform>` → `growth`.

Discovery helpers `list_available_roles()` and `load_role_prompt()` let
external agents introspect which personas are vendored.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from .base import Draft, OptimizerError
from .llm import LLMConfig, call_llm_json


ROLE_AGENTS_DIR = Path(__file__).parent / "role_agents"

PublishConfidence = Literal["high", "medium", "low"]
_VALID_CONFIDENCE: tuple[str, ...] = ("high", "medium", "low")


@dataclass
class MarketRoleReport:
    role: str
    polished_title: str | None
    polished_body: str
    polished_hashtags: list[str] = field(default_factory=list)
    adopted_techniques: list[str] = field(default_factory=list)
    change_notes: str = ""
    risk_flags: list[str] = field(default_factory=list)
    publish_confidence: PublishConfidence = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "polished_title": self.polished_title,
            "polished_body": self.polished_body,
            "polished_hashtags": list(self.polished_hashtags),
            "adopted_techniques": list(self.adopted_techniques),
            "change_notes": self.change_notes,
            "risk_flags": list(self.risk_flags),
            "publish_confidence": self.publish_confidence,
        }

    def as_draft(self, platform: str, context: dict[str, Any] | None = None) -> Draft:
        """Materialize this report back into a Draft for chained polishing."""
        return Draft(
            platform=platform,  # type: ignore[arg-type]
            body=self.polished_body,
            title=self.polished_title,
            hashtags=list(self.polished_hashtags),
            context=dict(context or {}),
        )


def _resolve_role_path(role: str) -> Path:
    """Resolve a role identifier to an on-disk Markdown file.

    Accepts a stem ('douyin', 'xhs', 'x', 'growth'), a filename
    ('douyin.md'), or a full path. Raises OptimizerError if missing.
    """
    candidate = Path(role)
    if candidate.is_absolute() and candidate.is_file():
        return candidate
    # Try as stem inside role_agents/
    stem_path = ROLE_AGENTS_DIR / f"{Path(role).stem}.md"
    if stem_path.is_file():
        return stem_path
    # Try literal name inside role_agents/
    literal = ROLE_AGENTS_DIR / role
    if literal.is_file():
        return literal
    raise OptimizerError(
        f"role prompt not found for '{role}'; expected file in {ROLE_AGENTS_DIR}"
    )


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter delimited by two `---` lines at the top."""
    stripped = text.lstrip("﻿")
    if not stripped.startswith("---"):
        return {}, stripped
    # Find the closing fence on its own line.
    lines = stripped.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, stripped
    close_idx: int | None = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            close_idx = idx
            break
    if close_idx is None:
        return {}, stripped
    fm_block = "\n".join(lines[1:close_idx])
    body = "\n".join(lines[close_idx + 1 :]).lstrip("\n")
    try:
        fm = yaml.safe_load(fm_block) or {}
    except yaml.YAMLError as exc:
        raise OptimizerError(f"invalid YAML frontmatter: {exc}") from exc
    if not isinstance(fm, dict):
        raise OptimizerError(
            f"role frontmatter must be a mapping; got {type(fm).__name__}"
        )
    return fm, body


def load_role_prompt(role: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, prompt_body_string) for the given role."""
    path = _resolve_role_path(role)
    raw = path.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(raw)
    if not body.strip():
        raise OptimizerError(f"role prompt body is empty: {path}")
    return fm, body


def list_available_roles() -> list[dict[str, str]]:
    """Scan role_agents/ and return summaries of every vendored persona."""
    if not ROLE_AGENTS_DIR.is_dir():
        return []
    out: list[dict[str, str]] = []
    for path in sorted(ROLE_AGENTS_DIR.glob("*.md")):
        # Skip docs like README.md that have no frontmatter.
        try:
            fm, body = _split_frontmatter(path.read_text(encoding="utf-8"))
        except OptimizerError:
            continue
        if not fm or not body.strip():
            continue
        out.append(
            {
                "file": path.stem,
                "name": str(fm.get("name", path.stem)),
                "description": str(fm.get("description", "")),
                "vibe": str(fm.get("vibe", "")),
            }
        )
    return out


def _coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        # Allow a single string or a JSON-ish array embedded as string.
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _coerce_confidence(value: Any) -> PublishConfidence:
    if isinstance(value, str) and value.strip().lower() in _VALID_CONFIDENCE:
        return value.strip().lower()  # type: ignore[return-value]
    return "medium"


def _build_user_message(draft: Draft) -> str:
    return (
        "Return ONLY a JSON object with these keys:\n"
        "- polished_title (string or null)\n"
        "- polished_body (string)\n"
        "- polished_hashtags (array of strings)\n"
        "- adopted_techniques (array of short strings naming the techniques you applied)\n"
        "- change_notes (one-paragraph summary)\n"
        "- risk_flags (array of strings; empty if none)\n"
        '- publish_confidence ("high" | "medium" | "low")\n'
        "\n"
        "DRAFT:\n"
        f"{draft.as_text()}\n"
        "\n"
        f"Apply your marketing expertise to polish this draft for {draft.platform}.\n"
        "Preserve the core message; improve hook, structure, virality, platform fit.\n"
    )


def _report_from_payload(payload: dict[str, Any], role_name: str) -> MarketRoleReport:
    body = payload.get("polished_body")
    if not isinstance(body, str) or not body.strip():
        raise OptimizerError(
            f"LLM response missing required 'polished_body'; got payload keys={list(payload)}"
        )
    title_raw = payload.get("polished_title")
    title: str | None
    if title_raw is None:
        title = None
    elif isinstance(title_raw, str):
        title = title_raw.strip() or None
    else:
        title = str(title_raw).strip() or None
    notes_raw = payload.get("change_notes", "")
    change_notes = notes_raw.strip() if isinstance(notes_raw, str) else str(notes_raw)
    return MarketRoleReport(
        role=role_name,
        polished_title=title,
        polished_body=body.strip(),
        polished_hashtags=_coerce_str_list(payload.get("polished_hashtags")),
        adopted_techniques=_coerce_str_list(payload.get("adopted_techniques")),
        change_notes=change_notes,
        risk_flags=_coerce_str_list(payload.get("risk_flags")),
        publish_confidence=_coerce_confidence(payload.get("publish_confidence")),
    )


def polish(
    draft: Draft,
    *,
    role: str | None = None,
    config: LLMConfig | None = None,
) -> MarketRoleReport:
    """Run a single marketing-strategist polish on the draft.

    If `role` is None, the role defaults to `<draft.platform>` (e.g. a Douyin
    draft uses `role_agents/douyin.md`).
    """
    role_id = role if role is not None else draft.platform
    frontmatter, system_prompt = load_role_prompt(role_id)
    role_name = str(frontmatter.get("name") or Path(role_id).stem)
    user_message = _build_user_message(draft)
    try:
        payload = call_llm_json(system_prompt, user_message, config=config)
    except OptimizerError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise OptimizerError(f"market_role polish failed: {exc}") from exc
    try:
        return _report_from_payload(payload, role_name)
    except OptimizerError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise OptimizerError(
            f"market_role payload validation failed: {exc}; payload={json.dumps(payload)[:400]}"
        ) from exc


def chain_polish(
    draft: Draft,
    *,
    roles: list[str],
    config: LLMConfig | None = None,
) -> list[MarketRoleReport]:
    """Run `polish` once per role in order, threading each output into the next."""
    if not roles:
        raise OptimizerError("chain_polish requires at least one role")
    reports: list[MarketRoleReport] = []
    current = draft
    for role in roles:
        report = polish(current, role=role, config=config)
        reports.append(report)
        current = report.as_draft(platform=current.platform, context=current.context)
    return reports
