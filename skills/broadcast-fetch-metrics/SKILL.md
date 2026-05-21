---
name: broadcast-fetch-metrics
description: Fetch and normalize platform metrics into the Broadcast Kit metrics snapshot shape.
---

# Broadcast Fetch Metrics

Use this skill after publish runs to collect performance feedback for the next topic-selection pass.

## Agent Instructions

- Metrics lines should follow `contracts/metrics-snapshot.schema.json`.
- Douyin metrics use the in-package Playwright scraper at `broadcast_kit/publishers/douyin/metrics.py` (reads creator-center content-manage page, writes jsonl).
- X uses the built-in X API v2 collector with `X_BEARER_TOKEN`.
- YouTube uses the built-in YouTube Data API v3 collector with `YOUTUBE_API_KEY`.
- XHS metrics are not implemented in this kit; the collector returns `status: stub`.
- Dry-run validates route and output path without scraping live browser pages.

## Command Template

```bash
broadcast-kit fetch-metrics \
  --platform <douyin|xhs|x|youtube|all> \
  --account <account-label> \
  --since <date-or-window> \
  --dry-run
```

For Douyin day windows, use:

```bash
broadcast-kit fetch-metrics --platform douyin --account <account-label> --days 7 --dry-run
```
