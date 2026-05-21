---
name: broadcast-publish-douyin
description: Publish one Douyin manifest via the in-package Playwright publisher.
---

# Broadcast Publish Douyin

Use this skill for a single Douyin publish run.

## Agent Instructions

- Douyin publishes are one manifest per run. Do not batch multiple manifests.
- Required manifest fields: `id`, `title`, `caption`, `video_file` (or `video_url`), `douyin_schedule_publish_at` (ISO 8601 with timezone). Covers (`cover_horizontal_file`, `cover_vertical_file`) auto-generate from a video frame if missing.
- Scan `caption` for forbidden terms: `来源`, `*`, `notebooklm`, `slidesync`, `#notebooklm`. Refuse on hit.
- Optional inventory dedupe: set `DOUYIN_INVENTORY_FILE` to a Markdown table of already-published IDs.
- Live success requires the triple: `JUDGEMENT: success`, `COVER_VERIFY: True`, `QUEUE_VERIFY: True`.
- Dry-run validates manifest, opens Playwright, and exercises every step except the final publish click.
- First-time login: `python -m broadcast_kit.publishers.douyin.cli login --fresh`. Storage state lives at `state/douyin/auth.json`.

## Command Template

Dry-run:

```bash
broadcast-kit publish \
  --platform douyin \
  --manifest <manifest.yaml-or-json> \
  --dry-run
```

Or via the publisher's own CLI:

```bash
python -m broadcast_kit.publishers.douyin.cli publish \
  --manifest <manifest.yaml> \
  --schedule-publish-at "<ISO-8601-with-tz>" \
  --dry-run
```

For live publish, remove `--dry-run` only after the login state and inventory checks are clean. See `docs/publishers/douyin.md` for env vars, manifest format, success contract, and return shape.
