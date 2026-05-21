---
name: broadcast-render-narration
description: Prepare NotebookLM/HyperFrames narration handoff artifacts and a storyboard contract for a content-batch item.
---

# Broadcast Render Narration

Use this skill when the user wants hook, opening, or brand-frame narration assets for a batch item.

## Agent Instructions

- Read `content-batch.json` and choose an `item_id`.
- Keep the storyboard contract as `contracts/storyboard.schema.json`.
- Variants are only `hook-a`, `hook-b`, `brand`, and `opening`.
- NotebookLM is reached only through an existing user-supplied content workflow when available.
- HyperFrames remains an external adapter; do not rewrite the renderer.
- In dry-run, validate contract shape and produce the planned storyboard without live NotebookLM submission.

## Command Template

```bash
broadcast-kit render-narration \
  --batch <content-batch.json> \
  --item-id <content_id> \
  --variant <hook-a|hook-b|brand|opening> \
  --dry-run
```

For a real storyboard write, remove `--dry-run`.
