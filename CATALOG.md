# broadcast-kit Catalog (for the AI agent reading this)

You are an AI agent (Claude Code, Codex, Cursor, or similar) and a user has asked you to help them grow a social account or publish content. This kit ships callable parts. **Your job**: interview the user, pick the right parts, assemble a pipeline.

This file is the **menu**. Each entry: name, what it does, how to call it, when it's useful, and how it composes with neighbors.

If you only read one file in this kit, read this one.

---

## How to use this kit (3-sentence summary)

1. Ask the user **what platform, current state, target, and timeframe**. Optionally lay it down as `state/playbook/<platform>.yaml` using `broadcast_kit.optimizers.Playbook` (template at `playbook/templates/<platform>.yaml`).
2. For each new draft, run a **polish chain**: `content_brain → market_role → reviewer → virality_check`. Each step is optional; skip what doesn't apply.
3. After publish, run `engagement_score` + `miss_analysis` to feed insights back into the next draft.

You compose. The kit does not run a daemon. Use launchd / cron / your own loop if you want unattended runs.

## Capability tiers

Use these tiers when setting expectations with a new teammate or agent:

| Tier | Path | Reliability expectation |
|---|---|---|
| 1 | existing media → manifest / `produce-publish --video-file` → publish | Known-good path after login and `doctor` pass. |
| 2 | publish-registry → manifest → publish → fetch metrics → enrich feedback | Known-good path for teams that already have a content inventory. |
| 3 | source document → NotebookLM → SlideSync → publish | Setup-gated path. Requires external NotebookLM and SlideSync tools to be installed and logged in. |

Run `broadcast-kit doctor` after setup. `ok_for_douyin_existing_media=true` or `ok_for_xhs_existing_media=true` means that platform should be usable for Tier 1/2. `ok_for_source_to_video=true` means Tier 3 has the required local dependencies.

### Multi-account

Every Tier 1/2/3 path on `douyin` and `xhs` is now `--account`-scoped. Default account label is `"default"`; omitting `--account` resolves there. State lives at `state/<platform>/<account>/{auth.json, work/, ...}` and playbooks at `state/playbook/<platform>/<account>.yaml`. See [`docs/publishers/douyin.md`](docs/publishers/douyin.md) and [`docs/publishers/xhs.md`](docs/publishers/xhs.md) for the per-account login, listing, and migration details. X is single-account in this version — multi-account for X is a future task.

## Decision tree (start here)

The consuming agent should interview the user once, then jump to the matching tier + recipe. Don't run setup or the catalog tour before doing this step.

| User signal | Tier | Recipe | Setup command |
|---|---|---|---|
| "I have a finished video, just publish it to <platforms>" | 1 | E (with `--video-file`) | `broadcast-kit setup --for tier1` |
| "I have a draft caption; polish it before I publish" | 1 | A or C | `broadcast-kit setup --for tier1` |
| "I have a publish-registry / content inventory" | 2 | B via `registry-to-manifest` | `broadcast-kit setup --for tier2` |
| "I have a PDF / markdown source; make the video and publish" | 3 | E (full) | `broadcast-kit setup --for tier3` |
| "Grow my <platform> account over the next N weeks" | Sprint | B with playbook | `broadcast-kit setup --for tier1` + write playbook |
| "Why did my last posts underperform" | Analysis | `analyze_misses` + `engagement_score` | `broadcast-kit setup --for tier1` (LLM only) |
| "Find the best of N hook variants" | Polish | `variants.best_variant` | `broadcast-kit setup --for tier1` |

After the user signals the goal, recommend the matching `setup --for` command and the recipe section. Don't ask NotebookLM questions unless the goal needs Tier 3.

---

## Inventory by stage

### 0. State + playbook

| Part | Path | Purpose |
|---|---|---|
| Playbook schema | `broadcast_kit.optimizers.Playbook` | Pydantic model for `state/playbook/<platform>/<account>.yaml` (douyin/xhs; X stays at `state/playbook/x.yaml`). Fields: `account` (default `"default"`), `current_state`, `target`, `strategy`, `sprint`, `wake_times`, `quiet_hours`, `per_task_targets`, `miss_analysis`. |
| Playbook loader | `load_playbook(platform, account="default")` / `write_playbook(pb)` / `evolve_playbook(pb, metrics)` | Read, write, and update the playbook after a wake. Legacy `state/playbook/<platform>.yaml` is auto-migrated to `state/playbook/<platform>/default.yaml` on next write. |
| Templates | `playbook/templates/{xhs,douyin,x}.yaml` | Copy to `state/playbook/<platform>/<account>.yaml` (douyin/xhs) or `state/playbook/x.yaml` (X) and fill in numbers. |

**When to use**: at the start of any growth sprint, ask the user the 8 fields in the template, then write the YAML. After each wake, call `evolve_playbook(pb, measured)` and `write_playbook(pb)` to keep current_state current.

### 1. Publishing (the only required part)

| Platform | Module | Login | Scheduled publish | Metrics scraper |
|---|---|---|---|---|
| `douyin` | `broadcast_kit.publishers.douyin` | Playwright `state/douyin/auth.json` | Yes | content-manage page |
| `xhs` | `broadcast_kit.publishers.xhs` | Playwright `state/xhs/auth.json` | No | not implemented |
| `x` | `broadcast_kit.publishers.x` | NyxID or `X_BEARER_TOKEN` | n/a | X API v2 |
| `reddit` | `broadcast_kit.publishers.reddit` | Playwright `state/reddit/<acct>/auth.json` + stealth | n/a (peer-help comment-reply on demand) | use Reddit JSON API directly |
| `discourse` | `broadcast_kit.publishers.discourse` | Playwright `state/discourse/<acct>__<host>/auth.json` + stealth | n/a (peer-help reply on demand) | use Topic JSON API directly |

First-time login:

```bash
python -m broadcast_kit.publishers.<platform>.cli login --fresh
# Reddit (per-account):
broadcast-kit-reddit login --fresh --account <handle>
# Discourse (per-account · per-instance):
broadcast-kit-discourse login --fresh --account <handle> --instance https://community.n8n.io
```

Publish via CLI:

```bash
broadcast-kit publish --platform <p> --manifest <manifest.yaml>
# OR per-platform CLI:
broadcast-kit-reddit publish --manifest reddit-manifest.yaml --account <handle>
broadcast-kit-discourse publish --manifest discourse-manifest.yaml --account <handle>
```

Or Python:

```python
from broadcast_kit.publishers import publish
result = publish("xhs", job=manifest_dict, dry_run=False, config={"manifest": "/path/to/manifest.yaml"})
result = publish("reddit", job=reddit_manifest_dict, dry_run=False, config={"account": "my_handle"})
result = publish("discourse", job=discourse_manifest_dict, dry_run=False, config={"account": "my_handle"})
```

See `docs/publishers/{douyin,xhs,reddit,discourse}.md` for manifest shape, success contract, env vars.

**Reddit / Discourse vs Douyin / XHS:** the new English-community publishers target **peer-help comment-reply** (existing thread), not OP-post. Cloudflare bypass via `playwright-stealth` (verified · Reddit Cloudflare 1020 only blocks default Chromium). Both ship anon-fetch shadowban detection because AutoMod (Reddit) and staff-staging (Discourse) silently hide new-account posts without leaving "removed" text in HTML. Discourse uses Topic JSON API for accurate post-list comparison.

### 2. Optimizers (all optional, all compose)

Configure the LLM provider once via env: `BROADCAST_KIT_LLM_PROVIDER ∈ {openai, anthropic, ollama}` plus matching API key.

#### 2a. content_brain — structured diagnostic

```python
from broadcast_kit.optimizers import Draft, analyze
report = analyze(Draft(platform="xhs", body="..."))
# report.audience, .core_conflict, .hook_options, .title_options,
# .ai_taste_issues, .publish_decision ("publish" | "weak_test" | "hold")
```

CLI: `broadcast-kit optimize content-brain --draft draft.yaml`

**When**: first pass on any draft. If `publish_decision == "hold"`, do not publish.

#### 2b. market_role — vendored strategist persona

```python
from broadcast_kit.optimizers import Draft, polish, chain_polish, list_available_roles

# Single role (defaults to draft.platform)
report = polish(Draft(platform="xhs", body="..."))
# .polished_body, .polished_title, .polished_hashtags, .adopted_techniques

# Chain: platform-specific → growth hacker second-pass
reports = chain_polish(Draft(platform="x", body="..."), roles=["x", "growth"])
```

Available roles (auto-discovered from `broadcast_kit/optimizers/role_agents/*.md`):
- `douyin` — Douyin Strategist (3-second hook, completion rate)
- `xhs` — Xiaohongshu Specialist (aesthetic, micro-content)
- `x` — Twitter Engager (thread structure, reply bait)
- `growth` — Growth Hacker (cross-platform funnel)

CLI: not yet (call via Python).

**When**: after content_brain. Before reviewer.

#### 2c. reviewer — 10-dimension severity-weighted audit

```python
from broadcast_kit.optimizers import Draft, load_rubric, review
rubric = load_rubric(platform="x")            # bundled YAML, threshold -5
report = review(Draft(platform="x", body="..."), rubric=rubric, max_rounds=3)
# report.composite_score, .recommend_publish, .findings, .revisions
```

CLI: `broadcast-kit optimize reviewer --draft draft.yaml --max-rounds 3`

Custom rubric: pass `--rubric your.yaml`. See `broadcast_kit/optimizers/rubrics/x.yaml` for the shape.

**When**: after market_role. Last LLM-pass before publish.

#### 2d. variants — generate N + rank

```python
from broadcast_kit.optimizers import Draft, best_variant
result = best_variant(Draft(platform="xhs", body="..."), n=3)
```

CLI: `broadcast-kit optimize variants --draft draft.yaml --n 3`

**When**: when you want to A/B explore hook style.

#### 2e. virality_check — pre-publish virality score

```python
from broadcast_kit.optimizers import bitgrit, higgsfield, virality_score

# X (and XHS captions as a proxy): free REST, needs BITGRIT_API_KEY
r = bitgrit("draft tweet here", followers=312, following=180)

# Douyin video: subprocess to higgsfield CLI; skipped if not installed
r = higgsfield("/path/to/clip.mp4")

# Auto-dispatch by platform:
r = virality_score(Draft(platform="x", body="...", context={"followers": 312}))
# r.score (0-100), r.sub_scores ({hook_score, hold_rate, ...}), r.status
```

CLI: not yet (call via Python).

**When**: after reviewer, before publish. Graceful skip if backend not configured (no `BITGRIT_API_KEY`, no `higgsfield` CLI on PATH).

#### 2f. engagement_score — post-publish scoring (pure math)

```python
from broadcast_kit.optimizers import composite_score, heavy_ranker_score, rank_records

# HeavyRanker (public weights from twitter/the-algorithm; for X)
heavy_ranker_score({"reply": 5, "favorite": 100, "retweet": 10})  # → 127.5

# Weighted composite (works on any platform)
composite_score({"replies": 5, "favorites": 100, "impressions": 10000})  # → 28.75

# Rank a jsonl of records
ranked = rank_records(records, scorer="composite")
```

CLI: `broadcast-kit optimize engagement --metrics metrics.jsonl --scorer composite`

**When**: immediately after `fetch-metrics` to identify high-resonance posts.

#### 2g. miss_analysis — why winners beat the draft

```python
from broadcast_kit.optimizers import Draft, analyze_misses, top_performers

# Just retrieve top-K (no LLM)
winners = top_performers("xhs", k=5, window_days=30)

# Full diff-explain (one LLM call)
report = analyze_misses(Draft(platform="xhs", body="draft we're about to publish"))
# .top_performers, .diff_insights, .concrete_revisions,
# .recommended_hook_examples, .recommended_title_examples
```

CLI: not yet (call via Python).

**When**: before drafting the next batch. Feed `concrete_revisions` into the draft prompt context.

Reads `state/corpus/<platform>.jsonl`. The corpus is whatever you've collected via `fetch-metrics`; you decide what gets in.

### 3. Metrics collection

```bash
broadcast-kit fetch-metrics --platform <p> --account <label> --days 7
```

Writes a jsonl at `state/<platform>/work/metrics/<account>/<date>.jsonl`. Drop those records into `state/corpus/<platform>.jsonl` (or `cat >>`) to make them visible to `miss_analysis`.

### 4. Other commands

| Command | What it does |
|---|---|
| `broadcast-kit doctor` | Read-only capability check: Python deps, Playwright Chromium, ffmpeg, optional NotebookLM/SlideSync, saved auth files. |
| `broadcast-kit doc-to-batch` | Markdown / directory / repo → `content-batch.json` (cross-platform manifest) |
| `broadcast-kit render-narration` | Storyboard contract handoff to NotebookLM |
| `broadcast-kit render-video` | SlideSync preflight |
| `broadcast-kit registry-to-manifest` | `publish-registry.json` → platform-specific manifest |
| `broadcast-kit enrich-metrics` | Raw metrics + registry → scored `feedback-enriched.jsonl` |

See `--help` per command for details.

---

## Common recipes (copy-paste for the agent)

### Recipe A: one-shot polished publish (most common)

**Prerequisites**:

- Env: `BROADCAST_KIT_LLM_PROVIDER` + matching API key (`OPENAI_API_KEY` | `ANTHROPIC_API_KEY` | `OLLAMA_BASE_URL`).
- Services: none
- Platform logins: the one platform you're publishing to (douyin / xhs / x).
- Doctor flags: `ok_for_<platform>_existing_media=true` for the target platform.
- Account: `<label>`, default `"default"` (douyin/xhs only; X is single-account in this version).
- Setup command: `broadcast-kit setup --for tier1`.

```python
from broadcast_kit.optimizers import Draft, analyze, polish, review, virality_score
from broadcast_kit.publishers import publish

draft = Draft(platform="xhs", title="hook line", body="multi-line body...", hashtags=["#test"])

# Stage 1: structured diagnostic
brain = analyze(draft)
if brain.publish_decision == "hold":
    raise SystemExit(f"content_brain held: {brain.risk_notes}")

# Stage 2: marketing persona polish
market = polish(draft)
draft = Draft(platform=draft.platform, title=market.polished_title, body=market.polished_body,
              hashtags=market.polished_hashtags, context=draft.context)

# Stage 3: severity-weighted reviewer (with up to 3 revision rounds)
reviewed = review(draft, max_rounds=3)
if not reviewed.recommend_publish:
    raise SystemExit(f"reviewer rejected: score={reviewed.composite_score}")

# Stage 4: virality second-opinion
vscore = virality_score(draft)  # graceful-skip on missing backend

# Stage 5: ship
result = publish("xhs", job={"id": "demo", "title": draft.title, "body": draft.body,
                              "asset_kind": "image", "asset_paths": ["covers/01.png"]},
                 dry_run=False, config={})
```

### Recipe B: account-growth-sprint (twice-daily loop)

**Prerequisites**:

- Env: `BROADCAST_KIT_LLM_PROVIDER` + matching API key (`OPENAI_API_KEY` | `ANTHROPIC_API_KEY` | `OLLAMA_BASE_URL`).
- Services: none required, optional `BITGRIT_API_KEY` for virality_check on X-like text.
- Platform logins: the platform you're growing.
- Doctor flags: `ok_for_<platform>_existing_media=true`.
- Account: `<label>`, default `"default"` (douyin/xhs only). Playbook lives at `state/playbook/<platform>/<account>.yaml`.
- Setup command: `broadcast-kit setup --for tier1` plus user-written `state/playbook/<platform>/<account>.yaml`.

The agent runs this in its own scheduler (launchd plist, cron job, agent's own daemon — your choice).

```python
from broadcast_kit.optimizers import (
    load_playbook, evolve_playbook, write_playbook,
    Draft, analyze, polish, review, virality_score,
    analyze_misses, top_performers, rank_records,
)
from broadcast_kit.publishers import publish
from broadcast_kit.commands import fetch_metrics  # or call your own ingester

def wake(platform: str):
    pb = load_playbook(platform)

    # 1. Analyze — refresh metrics, identify what's working
    raw = fetch_metrics.run(platform, account=None, since=None, days=7,
                            dry_run=False)
    measured = {"followers": raw.get("followers"), "avg_engagement_rate": raw.get("rate")}
    pb = evolve_playbook(pb, measured)
    write_playbook(pb)

    # 2. Pre-draft retrieval — what beat me last week?
    misses = analyze_misses(Draft(platform=platform, body="(seed)"))
    seed_context = {
        "audience_hint": pb.current_state.top_content_type,
        "miss_insights": misses.diff_insights,
        "hook_examples": misses.recommended_hook_examples,
    }

    # 3. Draft (you decide how — LLM call, manual template, etc.)
    draft = your_draft_function(seed_context)

    # 4. Polish chain
    if analyze(draft).publish_decision == "hold": return
    draft = polish(draft).as_draft(platform=platform)
    if not review(draft, max_rounds=3).recommend_publish: return
    _ = virality_score(draft)  # log, don't block

    # 5. Ship
    publish(platform, job=draft_to_job(draft), dry_run=False, config={})
```

### Recipe C: single-post polish (no playbook, no daemon)

**Prerequisites**:

- Env: `BROADCAST_KIT_LLM_PROVIDER` + matching API key (`OPENAI_API_KEY` | `ANTHROPIC_API_KEY` | `OLLAMA_BASE_URL`).
- Services: none.
- Platform logins: none required (output is just the polished Draft; user copies it elsewhere).
- Doctor flags: none (LLM only).
- Setup command: `broadcast-kit setup --for tier1` (then user can `--skip douyin --skip xhs`).

User says "polish this tweet for me" → run just Recipe A's stages 1-3, no playbook needed.

### Recipe E: known-good video → Douyin + XHS (internal staff one-shot)

**Prerequisites**:

- Env: `BROADCAST_KIT_LLM_PROVIDER` + matching API key (`OPENAI_API_KEY` | `ANTHROPIC_API_KEY` | `OLLAMA_BASE_URL`).
- Tier 1 variant (`--video-file` provided):
  - Services: none.
  - Platform logins: the platforms you're publishing to.
  - Doctor flags: `ok_for_<platform>_existing_media=true`.
  - Account: `<label>`, default `"default"` (douyin/xhs only). Pass `--account <label>` to `produce-publish` to scope the run.
  - Setup command: `broadcast-kit setup --for tier1`.
- Tier 3 variant (no `--video-file`):
  - Services: notebooklm-py (pip + `notebooklm login`), SlideSync CLI.
  - Platform logins: the platforms you're publishing to.
  - Doctor flags: `ok_for_source_to_video=true` and `ok_for_<platform>_existing_media=true`.
  - Account: `<label>`, default `"default"` (douyin/xhs only).
  - Setup command: `broadcast-kit setup --for tier3`.

User says "I have a finished video — publish it to Douyin and Xiaohongshu". This is the first path to prove on a new machine because it does not require source-to-video generation.

```bash
# First time only (idempotent):
broadcast-kit setup
broadcast-kit doctor

# Then:
broadcast-kit produce-publish \
  --input /path/to/source-or-notes.md \
  --video-file /path/to/final-with-subtitles.mp4 \
  --platforms douyin,xhs \
  --schedule "2026-05-25T20:00:00+08:00"
```

What it does, stage by stage (each stage is graceful-skip — none raise):

1. **assets** — accepts `--video-file` as the publishable media and skips generation.
2. **notebooklm / slidesync** — skipped when `--video-file` is present.
3. **content_brain** — structured diagnostic on a seed draft derived from the input filename. If `publish_decision == "hold"`, downstream stages are blocked and the reason is surfaced.
4. **market_role** — platform-specific marketing-persona polish on the caption.
5. **reviewer** — 10-dimension severity audit. `recommend_publish == False` blocks publish.
6. **publish** — per-platform `publish()` call with the polished draft + video. Honors `--schedule` for Douyin.

Final output: a stage-by-stage JSON report. Inspect what was skipped, what was blocked, what was published. Use `--dry-run` to exercise every stage without irreversible actions.

If you want full source-to-video generation, run `broadcast-kit doctor` first and require `ok_for_source_to_video=true`, then omit `--video-file`:

```bash
broadcast-kit produce-publish \
  --input /path/to/source.pdf \
  --platforms douyin,xhs \
  --schedule "2026-05-25T20:00:00+08:00"
```

In that mode, NotebookLM uploads the source and downloads slides + audio, then SlideSync merges them into a `.mp4`. If either dependency is unavailable, publish is blocked with a clear asset-gate error instead of sending an empty job.

Skip flags: `--skip publish` stops right before sending; `--skip content_brain` or `--skip reviewer` bypasses a specific AI gate.

### Recipe D: post-publish-only feedback loop

**Prerequisites**:

- Env: `BROADCAST_KIT_LLM_PROVIDER` + matching API key (`OPENAI_API_KEY` | `ANTHROPIC_API_KEY` | `OLLAMA_BASE_URL`).
- Services: none.
- Platform logins: the platform whose metrics you're scraping (typically douyin; X uses bearer token).
- Doctor flags: `ok_for_<platform>_existing_media=true` for the scraper to log in.
- Account: `<label>`, default `"default"` (douyin/xhs only). `fetch-metrics --account <label>` writes to `state/<platform>/<account>/work/metrics/<date>.jsonl`.
- Setup command: `broadcast-kit setup --for tier1`.

User has already published 50 things and wants to find the patterns:

```bash
broadcast-kit fetch-metrics --platform x --account <handle>
broadcast-kit optimize engagement --metrics state/x/work/metrics/<handle>/<date>.jsonl --scorer heavy
broadcast-kit optimize engagement --metrics ... --scorer composite
```

Then in Python: `analyze_misses(some_new_draft)` to get the diff-explain.

---

## How to ask the user (interview script for the agent)

If the user just says "help me grow on XHS", run this interview before writing the playbook:

1. **Current state** — "how many followers now, posts so far, average engagement rate, what content type usually works?"
2. **Target** — "by when, and what's the success number — followers, engagement rate, posts/week?"
3. **Strategy** — "is this phase about widening reach, going deep on one vertical, experimenting with formats, or consolidating what works?" Map to `wide_net` / `narrow_vertical` / `experiment` / `consolidate`.
4. **Wake times** — "two windows per day work best — when does your audience usually scroll? Skip 1am-7am."
5. **Per-task targets** — "what's a 'good' impressions/saves/replies number for one post?"
6. **Vertical tag** — "any specific topic to anchor miss-analysis on?" (optional)

Then `write_playbook(Playbook(platform="xhs", ...))`. From here, the user's own scheduler triggers Recipe B per wake.

---

## What this kit does NOT do

- **No daemon / supervisor / launchd installer**. You (the consuming agent) decide when to wake. Use launchd, cron, agent's own loop, etc.
- **No content generation guarantees**. `your_draft_function(seed_context)` in Recipe B is yours to write — LLM call, template, human input.
- **No automatic credential management**. Each platform's login is a one-time interactive step; cookies live in `state/`.
- **No SlideSync internals, no NotebookLM browser automation, no HyperFrames code**. Those are external tools called as subprocesses.
- **No daemon for tiktok / instagram**. We don't ship publishers for those.

---

## Recipes by user goal (quick lookup)

| User says | Tier | Run |
|---|---|---|
| "polish this post" | 1 | Recipe C (content_brain + market_role + reviewer) |
| "help me grow on XHS for the next 4 weeks" | Sprint | Interview + write playbook + Recipe B in their scheduler |
| "rank my last 50 posts" | 1 | Recipe D (fetch-metrics → engagement_score) |
| "why didn't my last 5 posts work" | Analysis | analyze_misses + diff_insights |
| "give me 3 hook variants" | Polish | variants.best_variant |
| "publish this manifest now" | 1 | `broadcast-kit publish --platform <p> --manifest <m>` |
| "check if this video would go viral" | Polish | `higgsfield(clip_path)` |
| "check if this tweet would do well" | Polish | `bitgrit(text, followers, following)` |
| "I have a finished video, publish it" | 1 | Recipe E (`broadcast-kit produce-publish --video-file ...`) |
| "I have a PDF, make a video and publish it" | 3 | Recipe E source-to-video variant after `broadcast-kit doctor` shows `ok_for_source_to_video=true` |
| "first-time setup, configure everything" | — | `broadcast-kit setup` |
| "check if this machine is ready" | — | `broadcast-kit doctor` |

---

## Source files for an agent inspecting this kit

```
broadcast_kit/optimizers/
  base.py              # Draft, ContentBrainReport, ReviewerReport, severity scoring
  content_brain.py     # dbskill-style structured diagnostic
  reviewer.py          # 10-dim audit + bundled rubrics
  variants.py          # generate-N + rank
  market_role.py       # vendored strategist persona polish
  virality_check.py    # bitgrit + higgsfield CLI
  miss_analysis.py     # top-K + LLM diff
  engagement_score.py  # HeavyRanker + weighted composite (pure math)
  playbook.py          # Pydantic schema for state/playbook/<platform>.yaml
  llm.py               # openai / anthropic / ollama provider abstraction
  role_agents/         # vendored MIT prompts from msitarzewski/agency-agents
  rubrics/             # bundled reviewer rubrics per platform

broadcast_kit/publishers/
  douyin/              # full Playwright Douyin (login, publish, metrics, queue_verify)
  xhs/                 # full Playwright XHS (login, publish)
  x.py                 # NyxID + X API

playbook/templates/    # YAML templates for the interview output
docs/publishers/       # per-platform usage docs (douyin.md, xhs.md)
docs/optimizers.md     # optimizer deep-dive
contracts/             # JSON Schemas
```

For deeper docs see `docs/optimizers.md`, `docs/publishers/<platform>.md`, and the source of each module (each has a top docstring).
