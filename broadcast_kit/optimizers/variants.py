"""Generate N variant drafts of a post and pick the best by reviewer score."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import Draft, OptimizerError, ReviewerReport
from .llm import LLMConfig, call_llm_json


_VARIANT_SYSTEM = (
    "You are a multi-platform content editor. Given a draft post, produce N "
    "rewritten variants that explore DIFFERENT hook styles (e.g. contrarian, "
    "question, list, story, stat-led, emotional). Keep the same platform, "
    "hashtags, and overall topic. Vary the title and body. Match the language "
    "of the original draft. Return ONLY a JSON object."
)


_VARIANT_USER_TEMPLATE = """Original draft (platform={platform}):

{draft_text}

Produce exactly {n} variants. Each must explore a DIFFERENT hook style.
Respond with JSON of the shape:

{{
  "variants": [
    {{"hook_style": "<short label>", "title": "<title>", "body": "<body>"}},
    ...
  ]
}}
"""


@dataclass
class VariantResult:
    draft: Draft
    review: ReviewerReport
    composite_score: float


def generate_variants(draft: Draft, *, n: int = 3, config: LLMConfig | None = None) -> list[Draft]:
    """Ask the LLM for N variants. Hashtags and platform are preserved."""
    if n <= 0:
        raise ValueError(f"n must be >= 1; got {n}")
    user = _VARIANT_USER_TEMPLATE.format(
        platform=draft.platform,
        draft_text=draft.as_text(),
        n=n,
    )
    payload = call_llm_json(_VARIANT_SYSTEM, user, config=config)
    raw_variants = payload.get("variants")
    if not isinstance(raw_variants, list) or not raw_variants:
        raise OptimizerError(f"variants payload missing 'variants' array; got {payload}")

    out: list[Draft] = []
    for i, item in enumerate(raw_variants[:n]):
        if not isinstance(item, dict):
            raise OptimizerError(f"variant {i} not an object: {item!r}")
        body = item.get("body")
        if not isinstance(body, str) or not body.strip():
            raise OptimizerError(f"variant {i} missing 'body' string")
        title = item.get("title")
        if title is not None and not isinstance(title, str):
            raise OptimizerError(f"variant {i} has non-string title: {title!r}")
        context: dict[str, Any] = dict(draft.context)
        hook_style = item.get("hook_style")
        if isinstance(hook_style, str):
            context["hook_style"] = hook_style
        context["variant_index"] = i
        out.append(
            Draft(
                platform=draft.platform,
                body=body.strip(),
                title=title.strip() if isinstance(title, str) else draft.title,
                hashtags=list(draft.hashtags),
                context=context,
            )
        )
    if not out:
        raise OptimizerError("generate_variants produced zero valid drafts")
    return out


def score_variants(variants: list[Draft]) -> list[VariantResult]:
    """Score each variant via reviewer.review(); return sorted desc by score."""
    from .reviewer import review  # lazy import — reviewer is a sibling module

    results: list[VariantResult] = []
    for variant in variants:
        report = review(variant)
        results.append(
            VariantResult(
                draft=variant,
                review=report,
                composite_score=report.composite_score,
            )
        )
    results.sort(key=lambda r: r.composite_score, reverse=True)
    return results


def best_variant(draft: Draft, *, n: int = 3, config: LLMConfig | None = None) -> VariantResult:
    """Generate N variants, score them, return the highest-scoring one."""
    variants = generate_variants(draft, n=n, config=config)
    ranked = score_variants(variants)
    if not ranked:
        raise OptimizerError("best_variant: no scored variants")
    return ranked[0]
