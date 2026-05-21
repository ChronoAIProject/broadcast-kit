---
name: broadcast-render-video
description: Use SlideSync to turn PPT/PDF plus audio inputCase material into video artifacts.
---

# Broadcast Render Video

Use this skill when the user has SlideSync input material and wants a draft or final video.

## Agent Instructions

- Expect `inputCase/` to contain text or Markdown, one PDF deck, and one audio file.
- Use SlideSync through the adapter only; do not implement slide/audio alignment in Broadcast Kit.
- Allowed LLM providers are `none`, `openai_compatible`, and `codex_cli`.
- Dry-run means preflight or command planning; it must not require live platform actions.
- Return or persist a `slidesync-job` shape matching `contracts/slidesync-job.schema.json`.

## Command Template

```bash
broadcast-kit render-video \
  --input-dir <inputCase> \
  --project-dir <project-dir> \
  --llm-provider <none|openai_compatible|codex_cli> \
  --dry-run
```

For a real SlideSync generation, remove `--dry-run`.
