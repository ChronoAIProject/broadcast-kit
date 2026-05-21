"""N-dimension severity-weighted reviewer.

Modeled on lexa-story's ``tools/local_reviewer/cli.py`` 10-dimension audit.
A YAML rubric defines the dimensions, weights, and severity hints for a
platform. An LLM scores the draft against each dimension and emits a list
of `ReviewerFinding`. The composite score is the weighted sum (from
`base.compute_composite`); `recommend_publish` is True iff
``composite_score >= publish_threshold``.

Optional multi-round mode (``max_rounds > 1``): if the first round falls
below threshold, ask the LLM to produce a revised draft using its own
revision suggestions, then rescore. Stop on the first passing round, or
when ``max_rounds`` is exhausted. Returns the final report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .base import (
    Draft,
    OptimizerError,
    Platform,
    ReviewerFinding,
    ReviewerReport,
    Severity,
    compute_composite,
)
from .llm import LLMConfig, call_llm_json


# --------------------------------------------------------------------- types


@dataclass
class RubricDimension:
    name: str
    description: str
    weight: float = 1.0
    severity_hint: dict[str, str] | None = None


@dataclass
class Rubric:
    name: str
    platform: Platform | None
    publish_threshold: float
    dimensions: list[RubricDimension] = field(default_factory=list)

    def dimension_weight(self, name: str) -> float:
        for dim in self.dimensions:
            if dim.name == name:
                return dim.weight
        return 1.0


# --------------------------------------------------------------------- loading


_VALID_SEVERITIES: tuple[Severity, ...] = ("OK", "WARN", "BLOCK")
_RUBRICS_DIR = Path(__file__).parent / "rubrics"


def _bundled_rubric_path(platform: Platform) -> Path:
    return _RUBRICS_DIR / f"{platform}.yaml"


def load_rubric(path: Path | None = None, *, platform: Platform | None = None) -> Rubric:
    """Load a YAML rubric.

    If ``path`` is None, falls back to the bundled rubric for ``platform``.
    Raises OptimizerError on missing file / malformed shape.
    """
    if path is None:
        if platform is None:
            raise OptimizerError("load_rubric requires either path= or platform=")
        path = _bundled_rubric_path(platform)
    rubric_path = Path(path)
    if not rubric_path.exists():
        raise OptimizerError(f"rubric not found: {rubric_path}")
    try:
        raw = yaml.safe_load(rubric_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise OptimizerError(f"rubric YAML parse failed: {exc}") from exc
    if not isinstance(raw, dict):
        raise OptimizerError(f"rubric root must be a mapping; got {type(raw).__name__}")

    name = str(raw.get("name") or rubric_path.stem)
    plat = raw.get("platform")
    if plat is not None and plat not in ("x", "xhs", "douyin"):
        raise OptimizerError(f"rubric platform must be x/xhs/douyin or null; got {plat!r}")
    threshold = float(raw.get("publish_threshold", -5))

    dims_raw = raw.get("dimensions") or []
    if not isinstance(dims_raw, list) or not dims_raw:
        raise OptimizerError("rubric must define a non-empty 'dimensions' list")

    dimensions: list[RubricDimension] = []
    for entry in dims_raw:
        if not isinstance(entry, dict):
            raise OptimizerError(f"each dimension must be a mapping; got {entry!r}")
        dim_name = entry.get("name")
        if not dim_name or not isinstance(dim_name, str):
            raise OptimizerError(f"dimension missing 'name': {entry!r}")
        dimensions.append(
            RubricDimension(
                name=dim_name,
                description=str(entry.get("description", "")),
                weight=float(entry.get("weight", 1.0)),
                severity_hint=entry.get("severity_hint") or None,
            )
        )
    return Rubric(name=name, platform=plat, publish_threshold=threshold, dimensions=dimensions)


# --------------------------------------------------------------------- prompts


_SYSTEM_PROMPT = (
    "You are a severity-weighted publish reviewer. You audit a draft "
    "against a fixed rubric of named dimensions and return one finding per "
    "dimension. Severity is one of OK, WARN, BLOCK. Use BLOCK only for "
    "concrete rule violations (banned phrases, safety issues, hard format "
    "breaks). Use WARN for taste / quality concerns. Use OK when the "
    "dimension is satisfied. Return ONLY a JSON object."
)


def _format_dimensions(rubric: Rubric) -> str:
    lines: list[str] = []
    for dim in rubric.dimensions:
        line = f"- {dim.name} (weight={dim.weight}): {dim.description}"
        if dim.severity_hint:
            hints = "; ".join(f"{lvl}={txt}" for lvl, txt in dim.severity_hint.items())
            line += f"  [{hints}]"
        lines.append(line)
    return "\n".join(lines)


def _build_user_prompt(draft: Draft, rubric: Rubric, round_idx: int, prior: dict[str, Any] | None) -> str:
    parts: list[str] = [
        f"PLATFORM: {draft.platform}",
        f"RUBRIC: {rubric.name}",
        "DIMENSIONS:",
        _format_dimensions(rubric),
        "",
        "DRAFT:",
        draft.as_text(),
    ]
    if draft.context:
        parts.append("")
        parts.append("DRAFT_CONTEXT_JSON:")
        parts.append(json.dumps(draft.context, ensure_ascii=False))
    if round_idx > 0 and prior is not None:
        parts.append("")
        parts.append(f"REVISION_ROUND: {round_idx}")
        parts.append("PRIOR_FINDINGS_JSON:")
        parts.append(json.dumps(prior, ensure_ascii=False))
    parts.extend(
        [
            "",
            "Return JSON with this shape:",
            "{",
            '  "findings": [',
            '    {"dimension": "<one of the dimension names>", "severity": "OK|WARN|BLOCK", "note": "<short reason>"}',
            "  ],",
            '  "revisions": ["<concrete edit suggestion>", "..."]',
            "}",
            "Emit one finding per dimension, in the order listed. revisions may be empty when nothing needs fixing.",
        ]
    )
    return "\n".join(parts)


# --------------------------------------------------------------------- parsing


def _coerce_severity(value: Any) -> Severity:
    if not isinstance(value, str):
        raise OptimizerError(f"severity must be a string; got {value!r}")
    norm = value.strip().upper()
    if norm not in _VALID_SEVERITIES:
        raise OptimizerError(f"severity must be one of {_VALID_SEVERITIES}; got {value!r}")
    return norm  # type: ignore[return-value]


def _parse_findings(payload: dict[str, Any], rubric: Rubric) -> tuple[list[ReviewerFinding], list[str]]:
    raw_findings = payload.get("findings")
    if not isinstance(raw_findings, list) or not raw_findings:
        raise OptimizerError(f"LLM response missing 'findings' list: {payload}")

    findings: list[ReviewerFinding] = []
    for entry in raw_findings:
        if not isinstance(entry, dict):
            raise OptimizerError(f"finding must be a mapping; got {entry!r}")
        dim_name = entry.get("dimension")
        if not isinstance(dim_name, str) or not dim_name:
            raise OptimizerError(f"finding missing 'dimension': {entry!r}")
        severity = _coerce_severity(entry.get("severity"))
        note = str(entry.get("note") or "")
        weight = rubric.dimension_weight(dim_name)
        findings.append(
            ReviewerFinding(dimension=dim_name, severity=severity, note=note, weight=weight)
        )

    raw_revisions = payload.get("revisions") or []
    if not isinstance(raw_revisions, list):
        raise OptimizerError(f"'revisions' must be a list; got {raw_revisions!r}")
    revisions = [str(item) for item in raw_revisions if item]

    return findings, revisions


# --------------------------------------------------------------------- revision loop


_REVISE_SYSTEM = (
    "You revise a draft using the reviewer's suggestions. Return ONLY JSON "
    'with shape {"title": "...", "body": "...", "hashtags": ["..."]}. '
    "Preserve the platform conventions. Omit fields that should not change "
    "by leaving them as their prior value. Do not add commentary."
)


def _revise_draft(draft: Draft, revisions: list[str], config: LLMConfig | None) -> Draft:
    user = "\n".join(
        [
            f"PLATFORM: {draft.platform}",
            "CURRENT_DRAFT:",
            draft.as_text(),
            "",
            "REVISIONS_TO_APPLY:",
            *(f"- {r}" for r in revisions),
        ]
    )
    payload = call_llm_json(_REVISE_SYSTEM, user, config)
    body = payload.get("body")
    if not isinstance(body, str) or not body.strip():
        # LLM declined to revise — keep prior draft so the loop terminates cleanly.
        return draft
    title = payload.get("title")
    if not isinstance(title, str):
        title = draft.title
    raw_tags = payload.get("hashtags")
    if isinstance(raw_tags, list):
        hashtags = [str(t) for t in raw_tags if t]
    else:
        hashtags = list(draft.hashtags)
    return Draft(
        platform=draft.platform,
        body=body,
        title=title or None,
        hashtags=hashtags,
        context=dict(draft.context),
    )


# --------------------------------------------------------------------- public


def review(
    draft: Draft,
    *,
    rubric: Rubric | None = None,
    config: LLMConfig | None = None,
    max_rounds: int = 1,
) -> ReviewerReport:
    """Run a rubric audit against the draft via LLM."""
    if max_rounds < 1:
        raise OptimizerError(f"max_rounds must be >= 1; got {max_rounds}")
    if rubric is None:
        rubric = load_rubric(platform=draft.platform)

    current = draft
    last_report: ReviewerReport | None = None
    prior_payload: dict[str, Any] | None = None

    for round_idx in range(max_rounds):
        user_prompt = _build_user_prompt(current, rubric, round_idx, prior_payload)
        payload = call_llm_json(_SYSTEM_PROMPT, user_prompt, config)
        findings, revisions = _parse_findings(payload, rubric)
        composite = compute_composite(findings)
        recommend = composite >= rubric.publish_threshold
        last_report = ReviewerReport(
            findings=findings,
            composite_score=composite,
            publish_threshold=rubric.publish_threshold,
            recommend_publish=recommend,
            revisions=revisions,
        )
        if recommend or round_idx == max_rounds - 1 or not revisions:
            break
        prior_payload = last_report.to_dict()
        current = _revise_draft(current, revisions, config)

    assert last_report is not None  # loop runs at least once
    return last_report


__all__ = [
    "Rubric",
    "RubricDimension",
    "load_rubric",
    "review",
]
