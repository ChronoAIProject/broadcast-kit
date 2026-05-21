# Adapter: slidesync

## External Boundary

Broadcast Kit delegates PPT/PDF plus audio composition to SlideSync. It does not implement ASR, diarization, slide vision, review UI, or video rendering.

## Authentication

Use existing SlideSync environment variables:

- `SLIDESYNC_LLM_PROVIDER`
- `SLIDESYNC_LLM_BASE_URL`
- `SLIDESYNC_LLM_MODEL`
- `SLIDESYNC_LLM_API_KEY`
- `SLIDESYNC_LLM_TIMEOUT_SECONDS`
- `SLIDESYNC_LLM_RETRIES`
- `SLIDESYNC_SLIDE_VISION_MAX_WORKERS`
- `SLIDESYNC_GENERATE_PREP_PARALLEL`
- `SLIDESYNC_AUDIO_ANALYSIS_PARALLEL`
- `SLIDESYNC_ENABLE_ASR`
- `SLIDESYNC_ENABLE_DIARIZATION`
- `SLIDESYNC_APT_MIRROR`
- `SLIDESYNC_PYPI_INDEX_URL`
- `SLIDESYNC_TORCH_INDEX_URL`
- `SLIDESYNC_REVIEW_PORT`
- `SLIDESYNC_WHISPER_MODEL`
- `SLIDESYNC_WHISPER_LANGUAGE`
- `SLIDESYNC_INSTALL_DIARIZATION`
- `SLIDESYNC_TRANSCRIPT_CORRECTION`

## Invocation

Preflight:

```bash
slidesync preflight \
  --input-dir <inputCase> \
  --project-dir <project> \
  --llm-provider <none|openai_compatible|codex_cli> \
  --json
```

Generate:

```bash
slidesync generate \
  --input-dir <inputCase> \
  --project-dir <project> \
  --llm-provider <none|openai_compatible|codex_cli> \
  --json
```

Broadcast Kit parses JSON stdout and maps artifacts to `slidesync-job`.

## Dry-Run

Dry-run uses preflight and command planning. It does not invoke full generation.
