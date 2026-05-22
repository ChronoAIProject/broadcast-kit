"""Pure-math engagement scoring for post-publish metrics.

No LLM. Two scoring families:

- HeavyRanker: public weights from `twitter/the-algorithm`. The code there
  is AGPL but the numeric weights themselves are facts and reproduced here.
- Composite: platform-neutral engagement weights, normalized by
  log10(impressions + 10).

`score_record` consumes a single jsonl record matching
`contracts/metrics-snapshot.schema.json` and emits both scores plus a
high-resonance flag. `rank_records` sorts a list by either scorer.
"""

from __future__ import annotations

import math
from typing import Any


HEAVY_RANKER_DEFAULT_WEIGHTS: dict[str, float] = {
    "favorite": 0.5,
    "retweet": 1.0,
    "reply": 13.5,
    "reply_engaged_by_author": 75.0,
    "good_click": 11.0,
    "good_profile_click": 12.0,
    "negative_feedback_v2": -74.0,
    "report": -369.0,
}


COMPOSITE_DEFAULT_WEIGHTS: dict[str, float] = {
    "replies": 3.0,
    "quotes": 2.5,
    "reposts": 2.0,
    "bookmarks": 1.5,
    "favorites": 1.0,
    "dwell_proxy": 1.0,
}

HIGH_RESONANCE_THRESHOLD = 8.0


def _num(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def heavy_ranker_score(metrics: dict[str, Any], weights: dict[str, float] | None = None) -> float:
    """HeavyRanker weighted sum. Missing keys treated as 0."""
    w = weights if weights is not None else HEAVY_RANKER_DEFAULT_WEIGHTS
    return float(sum(_num(metrics.get(k, 0)) * w.get(k, 0.0) for k in w))


def composite_score(metrics: dict[str, Any], weights: dict[str, float] | None = None) -> float:
    """Weighted engagement composite, normalized by log10(impressions + 10)."""
    w = weights if weights is not None else COMPOSITE_DEFAULT_WEIGHTS
    raw = sum(_num(metrics.get(k, 0)) * w[k] for k in w)
    impressions = _num(metrics.get("impressions", 0))
    return float(raw / math.log10(impressions + 10))


# Mapping from broadcast-kit metrics-snapshot field names to scorer keys.
# The snapshot's `metrics` block uses generic names (likes/comments/...),
# which we project into both the HeavyRanker and composite scorer namespaces.
def _project_snapshot_metrics(snapshot_metrics: dict[str, Any]) -> dict[str, dict[str, float]]:
    likes = _num(snapshot_metrics.get("likes"))
    comments = _num(snapshot_metrics.get("comments"))
    shares = _num(snapshot_metrics.get("shares"))
    favorites = _num(snapshot_metrics.get("favorites")) or _num(snapshot_metrics.get("saves"))
    views = _num(snapshot_metrics.get("views"))
    profile_visits = _num(snapshot_metrics.get("profile_visits"))
    completion = _num(snapshot_metrics.get("completion_rate"))

    heavy = {
        "favorite": likes,
        "retweet": shares,
        "reply": comments,
        "good_profile_click": profile_visits,
        # `good_click` proxied by completion_rate * views (long-dwell views).
        "good_click": completion * views,
    }
    composite = {
        "replies": comments,
        "reposts": shares,
        "favorites": likes,
        "bookmarks": favorites,
        # No explicit quote counter in the snapshot schema.
        "quotes": 0.0,
        "dwell_proxy": completion * views,
        "impressions": views,
    }
    return {"heavy": heavy, "composite": composite}


def score_record(record: dict[str, Any], *, threshold: float = HIGH_RESONANCE_THRESHOLD) -> dict[str, Any]:
    """Score one metrics-snapshot jsonl record.

    Returns a dict with both scores and an `is_high_resonance` flag. The
    input may be either the full snapshot record (with a nested `metrics`
    block) or a flat dict already in scorer-key namespace.
    """
    if isinstance(record.get("metrics"), dict):
        projected = _project_snapshot_metrics(record["metrics"])
        heavy = heavy_ranker_score(projected["heavy"])
        composite = composite_score(projected["composite"])
    else:
        heavy = heavy_ranker_score(record)
        composite = composite_score(record)
    return {
        "heavy_ranker_score": heavy,
        "composite_score": composite,
        "is_high_resonance": composite >= threshold,
    }


def rank_records(records: list[dict[str, Any]], *, scorer: str = "composite") -> list[dict[str, Any]]:
    """Return records sorted by score desc, annotated with `_score` and `_rank`."""
    scorer_aliases = {"heavy_ranker": "heavy"}
    scorer = scorer_aliases.get(scorer, scorer)
    if scorer not in {"composite", "heavy"}:
        raise ValueError(f"scorer must be 'composite' or 'heavy'; got {scorer!r}")
    key = "composite_score" if scorer == "composite" else "heavy_ranker_score"
    annotated: list[dict[str, Any]] = []
    for rec in records:
        scored = score_record(rec)
        out = dict(rec)
        out["_score"] = scored[key]
        annotated.append(out)
    annotated.sort(key=lambda r: r["_score"], reverse=True)
    for i, rec in enumerate(annotated, start=1):
        rec["_rank"] = i
    return annotated
