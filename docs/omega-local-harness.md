# Omega Local Harness Boundary

`broadcast-kit` is the generic publishing toolkit. It should stay reusable by teams that are not working on Omega.

The Omega-specific local harness lives beside this repo:

```text
../omega-broadcast-local
```

## Responsibilities

`broadcast-kit` owns reusable capabilities:

- platform login helpers
- platform publish flows
- manifest schemas
- cover generation
- queue verification
- metrics adapters
- feedback enrichment contracts
- setup and doctor checks
- reusable agent skills

`broadcast-kit` does not own Omega operating state:

- Omega account cookies or auth files
- raw creator-backend screenshots
- Omega publish queues
- Omega campaign strategy
- Omega content registry
- raw comments or private feedback
- quarantined legacy Omega packages

## Where Omega Outputs Go

When local Omega testing produces reusable platform capability, update this repo.

Examples:

- Douyin selector fixes
- XHS publish flow improvements
- X thread or metrics support
- manifest contract improvements
- workspace/export commands useful to non-Omega users
- generic feedback schemas

When local Omega testing produces content-specific assets or retrospectives, write them to the source repo instead:

```text
../Omega-paper-series
../omega-ancient-texts-analysis
```

When local Omega testing produces private or temporary operating state, keep it in:

```text
../omega-broadcast-local
```

## Agent Entry Point

If an agent starts here and the user asks about Omega-specific publishing, first read:

```text
../omega-broadcast-local/README.md
../omega-broadcast-local/config.yaml
```

Then decide whether the requested change is generic enough to belong in `broadcast-kit`.
