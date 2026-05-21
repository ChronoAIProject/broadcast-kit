---
name: broadcast-publish-x
description: Publish a tweet or thread to X via NyxID proxy (preferred) or direct API (fallback).
---

# Broadcast Publish X

Use this skill when the user wants to publish a tweet or thread from a Broadcast Kit `publish-job`.

## Inputs

- `title`: optional lead text.
- `body`: required post body. Use `---` between sections to publish a thread.

## Agent Instructions

- Prefer NyxID CLI for live publish.
- Fall back to direct X API only when NyxID is unavailable and `X_BEARER_TOKEN` exists.
- Do not copy any voice-analysis, archive, or approval workflow into Broadcast Kit.
- Dry-run must generate a plan and JSON payload without publishing.
- Return a standard `publish-result` with `platform`, `status`, `post_id`, `post_url`, and `thread` when available.

## Command Template

```bash
broadcast-kit publish \
  --platform x \
  --manifest <x-job.yaml> \
  --dry-run
```

For live publish, remove `--dry-run` only after the manifest is reviewed.
