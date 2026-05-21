# Broadcast Architecture: Where broadcast-kit Fits

## What you're reading

This is the broadcast-kit-side orientation for a 4-piece Omega broadcast architecture. It tells a maintainer of *this* repo which kinds of work belong here and which kinds belong in one of the sibling repos.

The authoritative and most detailed version of this architecture lives in `omega-broadcast-local/ARCHITECTURE.md` on the user's local machine. That document is **not publicly distributed** because it covers the user's experimental Omega setup (auth state, content registries, in-flight campaigns). This file is the condensed, public-safe view.

## The 4 pieces

```text
                       ┌──────────────────────────────┐
                       │    omega-broadcast-local     │
                       │    (local harness only)      │
                       │  workspace, auth, evidence,  │
                       │  raw metrics, runs, inbox    │
                       └──────────────┬───────────────┘
                                      │ exports reusable
                                      │ capabilities as PRs
                                      ▼
                       ┌──────────────────────────────┐
                       │        broadcast-kit         │
                       │   (this repo, public OSS)    │
                       │  publishers, optimizers,     │
                       │  schemas, agent skills       │
                       └──────────────────────────────┘
                                      ▲
                  consumed by         │           consumed by
              ┌─────────────────┐     │     ┌──────────────────────────┐
              │ Omega-paper-    │     │     │ omega-ancient-texts-     │
              │ series          │     │     │ analysis                 │
              │ (academic       │     │     │ (Yijing, Daodejing,      │
              │  content +      │     │     │  classical-text content  │
              │  retrospectives)│     │     │  + retrospectives)       │
              └─────────────────┘     │     └──────────────────────────┘
                                      │
                                 (pulls in the
                                  publisher kit)
```

- **omega-broadcast-local** — Local harness only. Holds auth state, temporary runs, publish queue state, evidence, raw metrics, raw feedback, experiments, and export staging. Not a reusable library.
- **broadcast-kit** — Generic reusable publishing toolkit. Platform automation, schemas, metrics adapters, and reusable agent skills.
- **Omega-paper-series** — Academic content source and archive. Paper-series media outputs, distribution summaries, and academic retrospectives.
- **omega-ancient-texts-analysis** — Traditional literature and ancient-text content source and archive. Yijing, Daodejing, and other classical-text media outputs and retrospectives.

## Where broadcast-kit fits

broadcast-kit is the **reusable-capability layer**. The local harness (`omega-broadcast-local`) is where Omega-specific publishing actually runs day to day; broadcast-kit is what it imports when it needs to push pixels to Douyin / XHS / X, score a draft, or scrape metrics.

When the local harness produces something that is generic and reusable — a new publisher, a schema, an optimizer, a metrics adapter, a doctor check, an agent skill — that capability lands in broadcast-kit as a PR. The harness then upgrades and consumes it.

In effect, broadcast-kit is downstream of broadcast-local in *direction of code movement*, and upstream of broadcast-local in *direction of dependency*. The local harness depends on the kit; new capabilities flow the other way.

## Routing matrix (for upstream contributions to this repo)

If you're considering a PR to broadcast-kit, here's what belongs here vs elsewhere:

| Output kind                                          | Belongs in                       |
|------------------------------------------------------|----------------------------------|
| New platform publisher (Playwright or API)           | **broadcast-kit**                |
| Cross-platform JSON Schema / Pydantic contract       | **broadcast-kit**                |
| Generic optimizer (content_brain, reviewer, …)       | **broadcast-kit**                |
| Metrics scraper / adapter for a public API           | **broadcast-kit**                |
| Reusable agent skill (`skills/<name>/`)              | **broadcast-kit**                |
| Doctor capability check                              | **broadcast-kit**                |
| Account auth cookies, `auth.json`, login state       | omega-broadcast-local            |
| Per-item evidence, screenshots, queue verification   | omega-broadcast-local            |
| Per-item raw metrics jsonl + raw feedback            | omega-broadcast-local            |
| Publish queue, run logs, inbox, export staging       | omega-broadcast-local            |
| Paper-series media + distribution summary            | Omega-paper-series               |
| Academic retrospective tied to a paper               | Omega-paper-series               |
| Hexagram / Daodejing / classical-text media          | omega-ancient-texts-analysis     |
| Ancient-text retrospective or interpretation         | omega-ancient-texts-analysis     |

The mental shortcut: *reusable capability → here. Operating state → broadcast-local. Content asset → paper-series or ancient-texts.*

## What does NOT belong in broadcast-kit

To keep this repo a true generic toolkit, the following should not be merged here, even if it would be convenient:

- **Auth state of any kind** — no cookies, `storage_state`, account YAMLs, bearer tokens, or per-account session JSON. `state/` is gitignored for exactly this reason.
- **Paper-specific content** — no Omega paper PDFs, paper-derived scripts, paper retrospectives, paper covers. Those live in Omega-paper-series.
- **Hexagram / Daodejing / Yijing / classical-text content** — no source markdown, no per-hexagram media, no interpretation essays. Those live in omega-ancient-texts-analysis.
- **Anything tied to a single experiment or campaign** — no `hexagram04`-specific manifests, no Phoenix-launch campaign decks, no single-account growth playbooks (templates yes; filled-in YAMLs no).
- **Hand-edited "published truth" tables** — the canonical inventory is the harness's `published_inventory.jsonl`, not a markdown table in this repo.
- **A daemon / launchd plist / supervisor** — broadcast-kit is intentionally library-shaped. The consuming agent or harness owns scheduling.

If a PR feels like it would only ever be useful to one experiment, it probably belongs in `omega-broadcast-local` (private) or in the matching content repo.

## Links

- [`../README.md`](../README.md) — broadcast-kit overview and CLI
- [`../CATALOG.md`](../CATALOG.md) — agent-readable menu of every callable part
- [`./optimizers.md`](./optimizers.md) — optimizer deep-dive
- [`./publishers/`](./publishers/) — per-platform usage (Douyin, XHS)
- [`./omega-local-harness.md`](./omega-local-harness.md) — boundary note pointing back at the local harness
