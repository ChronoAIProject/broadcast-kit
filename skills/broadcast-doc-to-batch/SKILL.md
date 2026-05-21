---
name: broadcast-doc-to-batch
description: Generate a Broadcast Kit content-batch contract from Markdown, a directory, a repo path, or a publish registry.
---

# Broadcast Doc To Batch

Use this skill when the user wants an agent to turn source material into promotion documents: title, caption, hashtags, chapter hints, visual direction, and platform targets.

## Agent Instructions

- Keep the output contract as `content-batch.json`.
- Do not invent fields outside `contracts/content-batch.schema.json`.
- For Douyin targets, scan `caption` only for forbidden terms: `来源`, `*`, `notebooklm`, `slidesync`, `#notebooklm`.
- Prefer existing source registries when the input project exposes `publish-registry`.
- Use `--dry-run` first unless the user explicitly asks to write artifacts.

## Command Template

```bash
broadcast-kit doc-to-batch \
  --input <path-or-repo> \
  --output-dir <dir> \
  --platform <douyin|xhs|x|all> \
  --dry-run
```

For a real write, remove `--dry-run`.
