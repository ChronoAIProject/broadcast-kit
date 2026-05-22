"""Shared types and helpers for the optimizers layer.

The optimizers polish a draft (a Douyin caption, an XHS note, an X thread)
into a publishable version using either LLM-driven structured diagnostics
(`content_brain`, `reviewer`) or pure math (`engagement_score`). All
optimizers are optional; the publishers do not require them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


Platform = Literal["x", "xhs", "douyin"]
PublishDecision = Literal["publish", "weak_test", "hold"]
Severity = Literal["OK", "WARN", "BLOCK"]


@dataclass
class Draft:
    """A pre-publish draft that optimizers operate on."""

    platform: Platform
    body: str
    title: str | None = None
    hashtags: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    def as_text(self) -> str:
        parts: list[str] = []
        if self.title:
            parts.append(f"TITLE: {self.title}")
        parts.append(f"BODY: {self.body}")
        if self.hashtags:
            parts.append("HASHTAGS: " + " ".join(self.hashtags))
        return "\n".join(parts)


@dataclass
class ContentBrainReport:
    """Structured diagnostic output, dbskill-style.

    Field shapes match `ops/xiaohongshu/queue-item.schema.json` from the
    dayou-content reference, generalized away from the 八字/紫微 specifics.
    """

    audience: str
    core_conflict: str
    why_people_will_care: str
    why_people_may_ignore: str
    hook_options: list[str]
    title_options: list[str]
    recommended_title: str
    ai_taste_issues: list[str]
    risk_notes: list[str]
    publish_decision: PublishDecision

    def to_dict(self) -> dict[str, Any]:
        return {
            "audience": self.audience,
            "core_conflict": self.core_conflict,
            "why_people_will_care": self.why_people_will_care,
            "why_people_may_ignore": self.why_people_may_ignore,
            "hook_options": self.hook_options,
            "title_options": self.title_options,
            "recommended_title": self.recommended_title,
            "ai_taste_issues": self.ai_taste_issues,
            "risk_notes": self.risk_notes,
            "publish_decision": self.publish_decision,
        }


@dataclass
class ReviewerFinding:
    dimension: str
    severity: Severity
    note: str
    weight: float = 1.0


@dataclass
class ReviewerReport:
    """N-dimension reviewer output. Composite score = sum(severity_weight * dim_weight)."""

    findings: list[ReviewerFinding]
    composite_score: float
    publish_threshold: float
    recommend_publish: bool
    revisions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "composite_score": self.composite_score,
            "publish_threshold": self.publish_threshold,
            "recommend_publish": self.recommend_publish,
            "findings": [
                {
                    "dimension": finding.dimension,
                    "severity": finding.severity,
                    "note": finding.note,
                    "weight": finding.weight,
                }
                for finding in self.findings
            ],
            "revisions": self.revisions,
        }


# Severity to numeric score table used by the bundled reviewer rubrics.
SEVERITY_SCORE: dict[Severity, int] = {
    "OK": 0,
    "WARN": -3,
    "BLOCK": -10,
}


def severity_score(severity: Severity) -> int:
    return SEVERITY_SCORE[severity]


def compute_composite(findings: list[ReviewerFinding]) -> float:
    return float(sum(severity_score(f.severity) * f.weight for f in findings))


class OptimizerError(RuntimeError):
    """Raised when an optimizer can't produce a usable result."""
