# Broadcast Kit

A self-contained, agent-facing publisher kit. Clone, install, log in once per platform, publish. Optional polish + scoring layer for content optimization sprints.

**Publishers**: Douyin (full Playwright + scheduled + queue verify + metrics), XHS (Playwright note publish), X (NyxID-brokered or direct API), **Reddit** (Playwright stealth + Cloudflare bypass · old.reddit OP-reply + anon shadowban detection), **Discourse** (generic — n8n forum / huggingface community / any self-hosted Discourse · Topic JSON API shadowban detection).
**Optimizers (optional)**: content_brain (LLM diagnostic, dbskill-style), market_role (vendored marketing-persona prompts), reviewer (10-dim severity audit with bundled rubrics), variants (A/B generate+rank), virality_check (Higgsfield CLI + bitgrit API), miss_analysis (top-K corpus + LLM diff), engagement_score (HeavyRanker + weighted composite scoring), playbook (sprint schema), public_copy_gate (deterministic caption/topic release gate).

## For agents reading this for the first time

**Start at [CATALOG.md](CATALOG.md)** — agent-readable menu of every callable part with input/output shapes, when-to-use, and copy-paste recipes. If a user asks you to grow an account, polish a draft, or set up a content sprint, CATALOG.md tells you which parts to pick and in what order.

## For internal staff (non-developers)

Read [`docs/internal-onboarding.md`](docs/internal-onboarding.md). It walks through `broadcast-kit setup`, `broadcast-kit doctor`, then the known-good path: publish an already finished video through Douyin/XHS. Source-to-video through NotebookLM + SlideSync is supported when those external tools are installed.

Quick orientation:

1. **What it is** — a Python package with `broadcast-kit <command>` CLI. Each platform's Playwright code lives in `broadcast_kit/publishers/<platform>/`. No external repo dependency.
2. **What you need on the host** — Python 3.11+, Chromium (`python -m playwright install chromium`), `ffmpeg` (for Douyin cover gen), a display (Playwright runs non-headless).
3. **Where state lives** — `state/<platform>/auth.json` (gitignored). First login is interactive; subsequent runs reuse the cookie.
4. **What you must NOT do** — don't pass raw API keys into manifests or docs; don't `--force-republish` without checking the inventory; don't run a live publish without confirming the verdict triple (Douyin) or the note-manager verification (XHS); don't bypass `publish_decision: hold` from content_brain.
5. **No daemon shipped** — you (the consuming agent) decide when to wake. Use launchd / cron / your own loop. CATALOG.md Recipe B shows the full closed-loop sequence.

## Install

```bash
pip install .
python -m playwright install chromium
```

For the advanced NotebookLM + SlideSync source-to-video path:

```bash
pip install '.[source-to-video]'
```

## First-time login (per platform)

```bash
python -m broadcast_kit.publishers.douyin.cli login --fresh
python -m broadcast_kit.publishers.xhs.cli login --fresh
broadcast-kit-reddit login --fresh --account <handle>
broadcast-kit-discourse login --fresh --account <handle> --instance https://community.n8n.io
```

Each opens a non-headless Chromium. Scan QR / finish login. Press Enter in the terminal. `storage_state` is saved to `state/<platform>/auth.json`. Check validity later with `... login` (no `--fresh`).

## Top-level CLI

```bash
broadcast-kit doc-to-batch         # markdown/dir/repo → content-batch
broadcast-kit render-narration     # storyboard handoff
broadcast-kit render-video         # SlideSync preflight
broadcast-kit publish              # one manifest → platform
broadcast-kit produce-publish      # known-good video or generated video → polish → publish
broadcast-kit registry-to-manifest # publish-registry → platform manifest
broadcast-kit fetch-metrics        # creator-center scraper / API call
broadcast-kit enrich-metrics       # raw metrics + registry → scored feedback jsonl
broadcast-kit doctor               # read-only local capability check
broadcast-kit optimize ...         # content_brain | reviewer | variants | engagement
```

Recommended setup check:

```bash
broadcast-kit doctor
broadcast-kit doctor --live-login-check
```

Each Playwright publisher also exposes its own `python -m broadcast_kit.publishers.<platform>.cli`.

## Optimize (optional polish layer)

```bash
# Structured LLM diagnostic — audience, hooks, titles, ai-taste, publish_decision
broadcast-kit optimize content-brain --draft draft.yaml

# 10-dimension severity-weighted audit (bundled rubric per platform)
broadcast-kit optimize reviewer --draft draft.yaml --max-rounds 3

# Generate N variants and pick the best by reviewer score
broadcast-kit optimize variants --draft draft.yaml --n 3

# Score post-publish metrics with HeavyRanker (X) or platform-neutral composite weights
broadcast-kit optimize engagement --metrics metrics.jsonl --scorer composite
```

Configure the LLM provider via env: `BROADCAST_KIT_LLM_PROVIDER=openai|anthropic|ollama`, plus the matching API key. See `docs/optimizers.md`.

## Publishers

| Platform | Implementation | Login | Scheduled publish | Metrics | Multi-account |
|---|---|---|---|---|---|
| `douyin` | `broadcast_kit/publishers/douyin/` | Playwright `storage_state` | Yes | content-manage scraper | Yes (`--account <label>`) |
| `xhs` | `broadcast_kit/publishers/xhs/` | Playwright `storage_state` | No | not implemented | Yes (`--account <label>`) |
| `x` | `broadcast_kit/publishers/x.py` | NyxID or `X_BEARER_TOKEN` | n/a | X API v2 | No (future) |
| `reddit` | `broadcast_kit/publishers/reddit/` | Playwright `storage_state` + stealth | n/a (post on demand) | use Reddit JSON API directly | Yes (`--account <label>`) |
| `discourse` | `broadcast_kit/publishers/discourse/` | Playwright `storage_state` + stealth (per-instance) | n/a | use Topic JSON API directly | Yes (`--account <label>` × per-instance) |
| `youtube` | `broadcast_kit/metrics/youtube.py` | `YOUTUBE_API_KEY` | n/a | Data API v3 | n/a |

TikTok and Instagram are intentionally not shipped — we don't ship stubs.

Reddit and Discourse target **peer-help comment-reply** specifically (not OP-post). They share a stealth + storage_state architecture but ship anon-fetch shadowban detection because new-account anti-spam (AutoMod / staff-review staging) silently hides posts on those platforms. See [`docs/publishers/reddit.md`](docs/publishers/reddit.md) and [`docs/publishers/discourse.md`](docs/publishers/discourse.md).

### Multi-account

Douyin and XHS support publishing from multiple accounts on the same host via `--account <label>`. State is partitioned at `state/<platform>/<account>/{auth.json, work/, ...}`; the default label is `"default"`, so existing single-account flows keep working unchanged (legacy `state/<platform>/auth.json` is auto-migrated to `state/<platform>/default/auth.json` on first call with a one-line warning). The flag works on `publish`, `fetch-metrics`, `produce-publish`, `doctor` (single account or `--all-accounts`), and the per-publisher `accounts` subcommand. The env var `DOUYIN_AUTH_STATE` / `XHS_AUTH_STATE` still takes precedence if you set it explicitly. Playbooks live at `state/playbook/<platform>/<account>.yaml`. X publisher is single-account in this version; multi-account for X is a future task. See [`docs/publishers/douyin.md`](docs/publishers/douyin.md) and [`docs/publishers/xhs.md`](docs/publishers/xhs.md) for the deep dive.

## Contracts

JSON Schemas in `contracts/` define cross-platform shapes: `content-batch`, `storyboard`, `slidesync-job`, `publish-job`, `publish-result`, `metrics-snapshot`, `publish-registry`, `feedback-enriched`. Each publisher additionally ships its own platform-specific Pydantic manifest schema.

## State

Runtime state (auth cookies, screenshots, scheduled state, metrics jsonl) lives under `state/`. Gitignored. Override the root with `BROADCAST_KIT_STATE_DIR=/path/to/state`.

## Contract rules (read before live publish)

- **Douyin**: live success requires `JUDGEMENT: success` + `COVER_VERIFY: True` + `QUEUE_VERIFY: True`. Caption forbidden terms: `来源`, `*`, `notebooklm`, `slidesync`, `#notebooklm`. Manifest needs `id`, `title`, `caption`, `video_file`/`video_url`, `douyin_schedule_publish_at` (ISO 8601 + timezone). Covers auto-generate from a video frame if missing.
- **Public content guard**: Douyin and XHS manifest parsers reject obvious internal operating language in public text fields, such as `测试`, `短图文版本`, `Test`, `A/B`, `experiment`, and `Broadcast Test`. Keep those words in local metrics/status, not public title/body/caption/topics.
- **Public copy release gate**: `broadcast_kit.public_guard.PublicCopyGateConfig` and `assert_public_copy_gate(...)` provide a reusable deterministic gate for caption density, required context markers, explanatory markers, allowed platform topics, forbidden public terms, and excessive Latin-letter ratio. Consuming repos should pass their own account-specific markers and topic allowlist.
- **XHS**: title ≤20 chars, body ≤1000 chars, topics through the topic-picker UI (raw `#hashtag` text is ignored by XHS as plain text). Up to 18 images or exactly 1 video per note. `published=true` is only a submit-page signal; production runs should verify the note in creator-center note manager and confirm the edit page shows the intended public body and media count.
- **X**: thread separator is `---` between tweets. NyxID is preferred; `X_BEARER_TOKEN` is the fallback.
- **Dry-run**: every publisher's dry-run mode opens Playwright, exercises every step except the final publish click. Treat it as a smoke test, not a no-op.

## Out of scope

This kit publishes, scores, and provides a dependency-gated source-to-video bridge. The primary supported path is existing media or a publish registry → manifest → publish → metrics → enriched feedback. NotebookLM/SlideSync generation is available when the host has those external tools configured; it is not a guarantee that every source document can become a video without setup. The kit does not operate a publish daemon.

## Where things are

```
broadcast_kit/
  publishers/
    douyin/        Playwright Douyin (login, publish, metrics, queue_verify, cover_gen, cli)
    xhs/           Playwright XHS (login, publish, cli)
    x.py           NyxID + X API
  commands/        top-level CLI command implementations
  optimizers/      content_brain, reviewer, variants, engagement_score (optional)
  metrics/         x, youtube standalone collectors
  adapters/        slidesync, hyperframes, notebooklm, content-registry adapters
contracts/         JSON Schemas
docs/
  publishers/      per-platform usage (douyin.md, xhs.md)
  optimizers.md    optional polish + scoring layer
skills/            agent skill packages
state/             runtime state (gitignored)
```
