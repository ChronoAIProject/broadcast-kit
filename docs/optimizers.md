# Optimizers

Optional polish + scoring layer. Live in `broadcast_kit/optimizers/`. Publishers do not require any of these. Use them when you want to:

- polish a draft before publish (`content_brain`, `reviewer`)
- pick the best of N variants (`variants`)
- score post-publish metrics with public industry weights (`engagement_score`)

## Configure the LLM provider

content_brain, reviewer, and variants need an LLM. Configure via env:

```bash
export BROADCAST_KIT_LLM_PROVIDER=openai     # or: anthropic, ollama
export BROADCAST_KIT_LLM_MODEL=gpt-4o-mini   # optional override; sensible defaults per provider
export OPENAI_API_KEY=sk-...
# anthropic: ANTHROPIC_API_KEY
# ollama:    OLLAMA_BASE_URL (defaults to http://localhost:11434)

export BROADCAST_KIT_LLM_TEMPERATURE=0.4     # optional
export BROADCAST_KIT_LLM_MAX_TOKENS=2000     # optional
```

`engagement_score` is pure math — no LLM, no env config needed.

## Draft shape

A `Draft` is a YAML/JSON file passed via `--draft`:

```yaml
platform: x        # or xhs / douyin
title: "..."       # optional for X (uses first thread tweet)
body: |
  Multi-line body. For X, separate thread tweets with `---`.
hashtags:
  - "#example"
context:           # optional; arbitrary platform extras
  thread_target_length: 5
```

## content_brain — structured diagnostic

Single structured LLM call. Returns the dbskill-style report:

```bash
broadcast-kit optimize content-brain --draft draft.yaml
```

Output (truncated):

```json
{
  "status": "ok",
  "platform": "xhs",
  "report": {
    "audience": "...",
    "core_conflict": "...",
    "why_people_will_care": "...",
    "why_people_may_ignore": "...",
    "hook_options": ["...", "...", "..."],
    "title_options": ["...", "...", "..."],
    "recommended_title": "...",
    "ai_taste_issues": ["delve into", "let's explore"],
    "risk_notes": ["..."],
    "publish_decision": "publish"
  }
}
```

`publish_decision` is one of `publish`, `weak_test`, `hold`. Treat `hold` as "do not publish".

In Python:

```python
from broadcast_kit.optimizers import Draft, analyze

draft = Draft(platform="xhs", title="...", body="...", hashtags=[])
report = analyze(draft)
print(report.recommended_title, report.publish_decision)
```

## reviewer — N-dimension severity-weighted audit

Severity table: `BLOCK = -10`, `WARN = -3`, `OK = 0`. Composite = sum(severity_score × dimension_weight). Default safety dimension weight is 2.0.

Bundled rubrics at `broadcast_kit/optimizers/rubrics/{x,xhs,douyin}.yaml`. Each has 10 dimensions and a `publish_threshold` of `-5`. Override with your own rubric YAML.

```bash
broadcast-kit optimize reviewer --draft draft.yaml --max-rounds 3
```

When `--max-rounds > 1` and the composite score is below threshold, the reviewer asks the LLM to revise and rescores. Stops on first pass-through, when revisions list is empty, or when rounds are exhausted.

In Python:

```python
from broadcast_kit.optimizers import Draft, load_rubric, review

draft = Draft(platform="x", body="...")
rubric = load_rubric(platform="x")
report = review(draft, rubric=rubric, max_rounds=3)
print(report.composite_score, report.recommend_publish)
for f in report.findings:
    print(f.dimension, f.severity, f.note)
```

### Writing a custom rubric

```yaml
name: my-rubric
platform: x
publish_threshold: -5
dimensions:
  - name: hook_strength
    description: "First tweet must have a concrete artifact, claim, or named target."
    weight: 1.0
    severity_hint:
      BLOCK: "first tweet is a meta-summary"
      WARN: "abstract claim with no artifact"
  - name: safety_proxy
    description: "Block adult, hate, violence, public-figure attack."
    weight: 2.0
```

Pass with `--rubric my-rubric.yaml`.

## variants — generate N + rank

```bash
broadcast-kit optimize variants --draft draft.yaml --n 3
```

Generates 3 hook-styled variants, scores each with the platform's default rubric, returns the best.

In Python:

```python
from broadcast_kit.optimizers import Draft, best_variant

result = best_variant(Draft(platform="x", body="..."), n=3)
print(result.draft.body, result.composite_score)
```

## engagement_score — pure math, no LLM

Two scorers:

**HeavyRanker** (`twitter/the-algorithm` public weights — facts, not AGPL code):

```python
HEAVY_RANKER_DEFAULT_WEIGHTS = {
    "favorite": 0.5,
    "retweet": 1.0,
    "reply": 13.5,
    "reply_engaged_by_author": 75.0,
    "good_click": 11.0,
    "good_profile_click": 12.0,
    "negative_feedback_v2": -74.0,
    "report": -369.0,
}
```

**Phoenix composite** (from lexa-story engagement loop):

```python
PHOENIX_DEFAULT_WEIGHTS = {
    "replies": 3.0,
    "quotes": 2.5,
    "reposts": 2.0,
    "bookmarks": 1.5,
    "favorites": 1.0,
    "dwell_proxy": 1.0,
}
# composite_score = sum(metric * weight) / log10(impressions + 10)
```

CLI ranks the records in a metrics jsonl and shows the top 5:

```bash
broadcast-kit optimize engagement --metrics state/douyin/work/metrics/default/2026-05-19.jsonl --scorer phoenix
broadcast-kit optimize engagement --metrics x_posts.jsonl --scorer heavy_ranker
```

In Python:

```python
from broadcast_kit.optimizers import heavy_ranker_score, phoenix_composite, rank_records

heavy_ranker_score({"reply": 5, "favorite": 100, "retweet": 10})   # 127.5
phoenix_composite({"replies": 5, "favorites": 100, "impressions": 10000})  # ~28.75

ranked = rank_records(records, scorer="phoenix")
```

## When to use what

| Goal | Use |
|---|---|
| "Is this draft worth publishing as-is?" | `content_brain` then read `publish_decision` |
| "What concretely should I fix?" | `reviewer` then read `findings` + `revisions` |
| "Pick the best of N hook variants" | `variants` |
| "After publish, which posts are high-resonance?" | `engagement_score` on the metrics jsonl |
| All four | chain them in a small Python script |

## Why these weights

- **HeavyRanker weights** are documented in `twitter/the-algorithm`'s public release. They are facts about Twitter's 2023 scoring; not AGPL-restricted.
- **Phoenix composite weights** come from lexa-story's engagement reinforcement loop, which uses Twitter's published action taxonomy as a feedback label.
- **Severity table** (-10 / -3 / 0) and the 10-dimension rubric structure come from lexa-story's `tools/local_reviewer/cli.py`.
- **Structured diagnostic shape** (audience / core_conflict / hook_options / title_options / ai_taste_issues / publish_decision) comes from the dayou-content dbskill output schema, generalized away from the 八字/紫微 specifics.

You can replace any of these with your own values — every weight, threshold, rubric, and prompt is overridable through env, function arg, or `--rubric`.
