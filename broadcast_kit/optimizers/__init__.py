"""Optional polish + scoring layer for broadcast-kit drafts.

Modules:

- `base`           — `Draft`, `ContentBrainReport`, `ReviewerReport`, severity scoring helpers.
- `llm`            — env-driven LLM provider (openai / anthropic / ollama).
- `content_brain`  — single structured LLM call: audience / conflict / hooks / titles / ai_taste / decision.
- `reviewer`       — N-dimension severity-weighted audit with bundled YAML rubrics per platform.
- `variants`       — generate N variants of a draft and rank them by reviewer score.
- `market_role`    — apply a vendored marketing-strategist persona prompt (Douyin / XHS / X / Growth).
- `virality_check` — pre-publish virality scoring via bitgrit (text) and Higgsfield CLI (video).
- `miss_analysis`  — rank corpus by composite score, LLM-explain why winners beat the draft.
- `engagement_score` — pure-math scoring of post-publish metrics (HeavyRanker + weighted composite).
- `playbook`       — Pydantic schema for `state/playbook/<platform>.yaml`.

Optimizers are optional. Publishers do not require them. Use them when you want
to (a) polish a draft before publish, (b) score one draft against many variants,
(c) feed post-publish metrics back into the loop, or (d) drive a sprint goal
from a playbook file.
"""

from __future__ import annotations

from .base import (
    ContentBrainReport,
    Draft,
    OptimizerError,
    Platform,
    ReviewerFinding,
    ReviewerReport,
    Severity,
    compute_composite,
    severity_score,
)
from .content_brain import adopted_summary, analyze
from .engagement_score import (
    COMPOSITE_DEFAULT_WEIGHTS,
    HEAVY_RANKER_DEFAULT_WEIGHTS,
    composite_score,
    heavy_ranker_score,
    rank_records,
    score_record,
)
from .llm import LLMConfig, call_llm_json, load_llm_config
from .market_role import (
    MarketRoleReport,
    chain_polish,
    list_available_roles,
    load_role_prompt,
    polish,
)
from .miss_analysis import MissAnalysisReport, load_corpus, top_performers
from .miss_analysis import analyze as analyze_misses
from .playbook import (
    CurrentState,
    MissAnalysisConfig,
    PerTaskTargets,
    Playbook,
    Sprint,
    SprintPace,
    Strategy,
    Target,
    evolve_playbook,
    list_playbooks,
    load_playbook,
    write_playbook,
)
from .reviewer import Rubric, RubricDimension, load_rubric, review
from .variants import VariantResult, best_variant, generate_variants, score_variants
from .virality_check import (
    BITGRIT_ENDPOINT,
    HIGGSFIELD_CLI,
    HIGGSFIELD_INSTALL_HINT,
    ViralityScore,
    bitgrit,
    higgsfield,
    rank_drafts,
)
from .virality_check import score as virality_score


__all__ = [
    "BITGRIT_ENDPOINT",
    "COMPOSITE_DEFAULT_WEIGHTS",
    "ContentBrainReport",
    "CurrentState",
    "Draft",
    "HEAVY_RANKER_DEFAULT_WEIGHTS",
    "HIGGSFIELD_CLI",
    "HIGGSFIELD_INSTALL_HINT",
    "LLMConfig",
    "MarketRoleReport",
    "MissAnalysisConfig",
    "MissAnalysisReport",
    "OptimizerError",
    "PerTaskTargets",
    "Platform",
    "Playbook",
    "ReviewerFinding",
    "ReviewerReport",
    "Rubric",
    "RubricDimension",
    "Severity",
    "Sprint",
    "SprintPace",
    "Strategy",
    "Target",
    "VariantResult",
    "ViralityScore",
    "adopted_summary",
    "analyze",
    "analyze_misses",
    "best_variant",
    "bitgrit",
    "call_llm_json",
    "chain_polish",
    "composite_score",
    "compute_composite",
    "evolve_playbook",
    "generate_variants",
    "heavy_ranker_score",
    "higgsfield",
    "list_available_roles",
    "list_playbooks",
    "load_corpus",
    "load_llm_config",
    "load_playbook",
    "load_role_prompt",
    "load_rubric",
    "polish",
    "rank_drafts",
    "rank_records",
    "review",
    "score_record",
    "score_variants",
    "severity_score",
    "top_performers",
    "virality_score",
    "write_playbook",
]
