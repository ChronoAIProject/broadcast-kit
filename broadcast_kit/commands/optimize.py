"""CLI implementations for `broadcast-kit optimize ...` subcommands.

Each function returns a dict; the cli layer prints it as JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from broadcast_kit.contracts import ContractError
from broadcast_kit.optimizers import (
    Draft,
    Rubric,
    analyze,
    best_variant,
    heavy_ranker_score,
    load_rubric,
    phoenix_composite,
    rank_records,
    review,
)


_PLATFORMS = {"x", "xhs", "douyin"}


def _load_draft(draft_path: Path) -> Draft:
    if not draft_path.exists():
        raise ContractError(f"draft file does not exist: {draft_path}")
    text = draft_path.read_text(encoding="utf-8")
    suffix = draft_path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        import yaml
        data = yaml.safe_load(text) or {}
    elif suffix == ".json":
        data = json.loads(text)
    else:
        raise ContractError(f"unsupported draft file type: {draft_path.suffix}")
    if not isinstance(data, dict):
        raise ContractError("draft root must be an object")
    platform = str(data.get("platform", "")).lower()
    if platform not in _PLATFORMS:
        raise ContractError(f"draft platform must be one of {sorted(_PLATFORMS)}, got {platform!r}")
    return Draft(
        platform=platform,  # type: ignore[arg-type]
        body=str(data.get("body", "")),
        title=data.get("title"),
        hashtags=list(data.get("hashtags") or []),
        context=dict(data.get("context") or {}),
    )


def content_brain(draft_path: Path) -> dict[str, Any]:
    draft = _load_draft(draft_path)
    report = analyze(draft)
    return {"status": "ok", "platform": draft.platform, "report": report.to_dict()}


def reviewer(draft_path: Path, rubric_path: Path | None, max_rounds: int) -> dict[str, Any]:
    draft = _load_draft(draft_path)
    rubric: Rubric = load_rubric(rubric_path) if rubric_path else load_rubric(platform=draft.platform)
    report = review(draft, rubric=rubric, max_rounds=max_rounds)
    return {"status": "ok", "platform": draft.platform, "rubric": rubric.name, "report": report.to_dict()}


def variants(draft_path: Path, n: int) -> dict[str, Any]:
    draft = _load_draft(draft_path)
    result = best_variant(draft, n=n)
    return {
        "status": "ok",
        "platform": draft.platform,
        "best": {
            "title": result.draft.title,
            "body": result.draft.body,
            "composite_score": result.composite_score,
        },
        "review": result.review.to_dict(),
    }


def engagement(metrics_path: Path, scorer: str) -> dict[str, Any]:
    if scorer not in {"phoenix", "heavy_ranker"}:
        raise ContractError("scorer must be phoenix or heavy_ranker")
    if not metrics_path.exists():
        raise ContractError(f"metrics file does not exist: {metrics_path}")
    records: list[dict[str, Any]] = []
    for line in metrics_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    ranked = rank_records(records, scorer=scorer)
    top = ranked[:5]
    return {
        "status": "ok",
        "scorer": scorer,
        "records": len(ranked),
        "top": [{"_score": r["_score"], "_rank": r["_rank"], "title": r.get("title") or r.get("content_id")} for r in top],
    }


__all__ = ["content_brain", "reviewer", "variants", "engagement"]
