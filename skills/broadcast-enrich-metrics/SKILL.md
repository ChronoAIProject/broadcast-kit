---
name: broadcast-enrich-metrics
description: Join raw platform metrics JSONL back to registry/manifest metadata and compute experiment scoring priors.
---

# Broadcast Enrich Metrics

Use this skill after `broadcast-kit fetch-metrics` has produced raw metrics JSONL and the user wants feedback records for learning loops, A/B tests, or topic selection.

## Agent Instructions

- Input is raw metrics JSONL, usually from `state/<platform>/work/metrics/<account>/<date>.jsonl`.
- Provide either a `publish-registry` or one or more platform manifests so records can be attributed back to content metadata.
- Output is JSONL with `schema_version: broadcast.feedback.v0`.
- Preserve the raw metrics inside the `metrics` object.
- Use the computed `scores` only as priors, not as final business truth.
- Use `--dry-run` first to inspect match rate before writing output.

## Command Template

```bash
broadcast-kit enrich-metrics \
  --metrics <raw-metrics.jsonl> \
  --registry <publish_registry.json> \
  --manifest <optional-manifest.yaml> \
  --output <feedback_enriched.jsonl> \
  --dry-run
```

Remove `--dry-run` to write the enriched JSONL.
