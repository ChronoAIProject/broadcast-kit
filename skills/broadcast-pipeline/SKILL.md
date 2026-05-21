---
name: broadcast-pipeline
description: Interview the user's content-publishing goal, map it to a capability tier, recommend the minimum setup, then run the matching recipe from CATALOG.md. Use this skill for any "publish / grow / analyze on Douyin / XHS / X" request.
---

# Broadcast Pipeline

Goal-first wrapper around `broadcast-kit`. Catch the user's goal in plain English first, then narrow the setup and recipe to fit. CATALOG.md is the reference menu, not the starting point.

## When to use

Trigger this skill when the user says any of:

- "help me publish this"
- "help me grow on Douyin / XHS / X"
- "polish this draft / tweet / caption"
- "why did my last 5 posts flop"
- "I have a PDF, make a video and publish it"
- "set up a content sprint"

## Workflow

### Step 1 — Capture goal (ask, don't dump)

Open with one wide question. Do **not** paste the playbook template, capability tier table, or recipe list yet.

> "What do you want to do with broadcast-kit? In your own words is fine."

Then ask **at most 2-4 clarifying questions**, scoped to what you still don't know:

- What media do you already have (finished video, image set, draft text, PDF, nothing)?
- Which platforms (Douyin / XHS / X / multiple)?
- Is this a one-shot publish, a recurring sprint, or post-publish analysis of stuff you already shipped?
- (Sprint only) Over what timeframe? Current followers / engagement?

Stop interviewing as soon as you can place the user on the tier table below.

### Step 2 — Map goal to tier

| User signal                                                | Tier    | Recipe |
|------------------------------------------------------------|---------|--------|
| "I have a finished video / image set, just publish it"     | Tier 1  | E (with `--video-file`) or direct `publish` |
| "Polish this draft before I publish"                       | Tier 1  | A or C |
| "I have a publish-registry / inventory"                    | Tier 2  | B-style with `registry-to-manifest` |
| "I have a PDF / markdown, make the video"                  | Tier 3  | E (full source-to-video) |
| "Grow my account over N weeks"                             | Sprint  | B with playbook |
| "Why did my last posts underperform"                       | (any)   | `analyze_misses` + `engagement_score` |

Tier definitions live in [`CATALOG.md` → Capability tiers](../../CATALOG.md#capability-tiers).

### Step 3 — Recommend minimum setup

Pick the smallest setup that satisfies the goal. **Do not ask the user for NotebookLM or SlideSync credentials unless their goal lands on Tier 3.** Likewise, skip `BITGRIT_API_KEY` / `higgsfield` prompts unless they asked for virality scoring.

```bash
broadcast-kit setup --for tier1      # publishers + LLM only
broadcast-kit setup --for tier2      # tier1 + publish-registry path
broadcast-kit setup --for tier3      # tier1 + NotebookLM + SlideSync
```

For **Sprint**, run `setup --for tier1` (or `tier2` if they have a registry) plus write `state/playbook/<platform>.yaml` from the interview answers. For **Analysis-only**, `setup --for tier1` is enough — they already have data, they just need LLM creds.

Always end the setup step with:

```bash
broadcast-kit doctor
```

and confirm the relevant `ok_for_*` flag is `true` before running the recipe.

If `doctor` fails, fix the gap (login, missing binary, missing env var) before moving on. Don't proceed and hope.

### Step 4 — Run the matching recipe

Pull the recipe straight from CATALOG.md — don't re-copy it here. Anchors:

- Tier 1 finished media → [Recipe E (with `--video-file`)](../../CATALOG.md#recipe-e-known-good-video--douyin--xhs-internal-staff-one-shot)
- Tier 1 polish only → [Recipe A](../../CATALOG.md#recipe-a-one-shot-polished-publish-most-common) or [Recipe C](../../CATALOG.md#recipe-c-single-post-polish-no-playbook-no-daemon)
- Tier 2 registry → Recipe B adapted with `broadcast-kit registry-to-manifest`
- Tier 3 source-to-video → [Recipe E (full)](../../CATALOG.md#recipe-e-known-good-video--douyin--xhs-internal-staff-one-shot)
- Sprint → [Recipe B](../../CATALOG.md#recipe-b-account-growth-sprint-twice-daily-loop) (user owns the scheduler)
- Analysis-only → [Recipe D](../../CATALOG.md#recipe-d-post-publish-only-feedback-loop) + `analyze_misses`

Read CATALOG.md only at this point, and only the section you need.

## What you do NOT do

- Do **not** bypass `content_brain.publish_decision == "hold"` or `reviewer.recommend_publish == False`. Surface the reasoning to the user and ask.
- Do **not** invent virality scores when the backend is missing — `virality_score` returns `status="skipped"`, which is correct.
- Do **not** commit `state/`. Auth cookies live there; it is gitignored.
- Do **not** ship or install a daemon from this skill. If the user wants twice-daily wakeups, they install their own launchd plist / cron job that invokes Recipe B.
- Do **not** front-load the full interview (8 playbook fields) on a user whose goal is "just publish this finished video".

## References

- [`CATALOG.md` — Capability tiers](../../CATALOG.md#capability-tiers) — full menu of parts and recipes
- [`docs/internal-onboarding.md`](../../docs/internal-onboarding.md) — step-by-step for internal staff
- [`docs/optimizers.md`](../../docs/optimizers.md) — optimizer deep-dive
- [`docs/publishers/`](../../docs/publishers/) — per-platform manifest shape and success contracts
