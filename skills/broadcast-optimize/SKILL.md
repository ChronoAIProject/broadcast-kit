---
name: broadcast-optimize
description: Optional polish + scoring of a draft before publish, and engagement scoring after.
---

# Broadcast Optimize

Use this skill when you want to polish a draft before calling `broadcast-publish-*`, or rank post-publish metrics.

## Agent Instructions

- Optimizers are optional. The publishers do not require them.
- Configure the LLM via env: `BROADCAST_KIT_LLM_PROVIDER` ∈ {openai, anthropic, ollama} + matching API key. See `docs/optimizers.md` for the full env set.
- Draft input is a YAML/JSON file with at minimum `platform` (x|xhs|douyin) and `body`.
- The reviewer's `publish_threshold` is -5 in the bundled rubrics; a composite score below threshold means do NOT publish without revising.
- Treat `content_brain.publish_decision == "hold"` as a hard stop.
- `engagement_score` is pure math; no LLM, no env. HeavyRanker weights apply to X-style records; weighted composite scoring applies to any platform with engagement metrics.

## Command Template

Structured diagnostic (dbskill-style):

```bash
broadcast-kit optimize content-brain --draft draft.yaml
```

Severity-weighted reviewer (10 dimensions per bundled rubric):

```bash
broadcast-kit optimize reviewer --draft draft.yaml --max-rounds 3
```

Generate N variants and pick the best:

```bash
broadcast-kit optimize variants --draft draft.yaml --n 3
```

Rank post-publish metrics:

```bash
broadcast-kit optimize engagement --metrics state/douyin/work/metrics/default/<date>.jsonl --scorer composite
broadcast-kit optimize engagement --metrics x_posts.jsonl --scorer heavy
```

See `docs/optimizers.md` for return shapes, Python-level usage, custom rubric format, and the source of every weight.
