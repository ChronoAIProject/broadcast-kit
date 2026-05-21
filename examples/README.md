# Examples

This directory is intentionally light in the scaffold. Keep examples sanitized and generic.

## `content-registry/`

Fixture shape:

- `publish_registry.json`
- `expected-content-batch.json`
- Items with fields from `contracts/publish-registry.schema.json`: `content_id`, `title`, `language`, `ready`, `platform_targets`, and `artifacts`

Use placeholder repositories such as `<your-org>/<your-content-repo>`.

## `weekly-batch/`

Suggested fixture shape:

- `content-batch.json`
- `publish-job-douyin.yaml`
- `publish-job-xhs.json`
- `publish-job-x.yaml`
- `raw_metrics.jsonl`

Do not include real account handles, tokens, unpublished media paths, or platform cookies.

## Common conversions

Generate a Douyin manifest from the generic registry:

```bash
broadcast-kit registry-to-manifest \
  --registry examples/content-registry/publish_registry.json \
  --content-id demo_video_001 \
  --platform douyin \
  --output examples/weekly-batch/publish-job-douyin.yaml \
  --schedule-at "2026-01-07T19:55:00+08:00" \
  --douyin-schedule-publish-at "2026-01-07T20:00:00+08:00" \
  --dry-run
```

Enrich raw metrics with registry metadata and experiment fields:

```bash
broadcast-kit enrich-metrics \
  --metrics examples/weekly-batch/raw_metrics.jsonl \
  --registry examples/content-registry/publish_registry.json \
  --output examples/weekly-batch/feedback_enriched.jsonl \
  --dry-run
```
