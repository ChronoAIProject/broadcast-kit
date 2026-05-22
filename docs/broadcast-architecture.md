# Broadcast Kit Architecture

## Purpose

`broadcast-kit` is a reusable publishing and feedback framework. It provides platform automation, manifest contracts, metric extraction, and optional content-optimization helpers that can be embedded in any team's own workflow.

It does not prescribe a private operating harness, content repository layout, campaign calendar, or account strategy. Consuming teams decide where to keep their source content, scheduling logic, run logs, and business-specific analytics.

## Main Components

```text
content source / scheduler / agent
              |
              v
       platform manifest
              |
              v
        broadcast-kit
    +---------------------+
    | publishers          | -> Douyin, XHS, X
    | contracts           | -> JSON Schemas and Pydantic manifests
    | metrics adapters    | -> platform snapshots
    | optimizers          | -> draft review, variants, engagement scoring
    | doctor/setup        | -> host readiness checks
    +---------------------+
              |
              v
      publish result / metrics
              |
              v
consuming team's datastore, reports, or next planning loop
```

## What Belongs Here

The repo should contain capabilities that are useful across projects:

- Platform login and publishing automation
- Manifest schemas and validation rules
- Public-content guards that prevent internal notes from being published
- Queue verification and publish-result contracts
- Metrics collectors and normalized metrics snapshots
- Optional draft optimizers, scoring utilities, and playbook schemas
- Setup and doctor checks for host readiness
- Reusable agent skills and examples

## What Does Not Belong Here

Keep project-specific state and content outside this kit:

- Auth cookies, browser storage state, bearer tokens, account credentials
- Live run logs, temporary screenshots, queue evidence, raw private comments
- Filled-in campaign calendars, project-specific inventories, or account strategies
- Source content for a single brand, research program, product, creator, or campaign
- One-off experiment manifests that are not reusable examples
- A daemon, supervisor, or launchd service that assumes a particular operating environment

The rule of thumb is simple: reusable capability belongs in `broadcast-kit`; private operating state and project-specific content belong in the consuming project.

## Extension Points

- Add a publisher under `broadcast_kit/publishers/<platform>/`.
- Add or revise a platform manifest schema near the publisher.
- Add cross-platform JSON Schemas under `contracts/`.
- Add metrics extraction under a publisher or `broadcast_kit/metrics/`.
- Add optional scoring or draft-improvement logic under `broadcast_kit/optimizers/`.
- Add setup checks in `broadcast_kit/commands/doctor.py` when a feature has host dependencies.

Every extension should be documented in [`../CATALOG.md`](../CATALOG.md) when it is callable by an agent or user.
