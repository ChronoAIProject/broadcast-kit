# Douyin Publisher

Self-contained Playwright-based Douyin publisher. Lives at `broadcast_kit/publishers/douyin/`. No external repo dependency.

## What it does

- Logs into `creator.douyin.com` with a persisted Playwright `storage_state`.
- Uploads a `.mp4`, fills title and description.
- Uploads horizontal (4:3, 1200x900) and vertical (3:4, 900x1200) cover JPEGs/PNGs. Auto-generates them from a video frame when missing (requires `ffmpeg` on PATH).
- Switches to "定时发布" and writes the scheduled time.
- Clicks the final publish button.
- Navigates to the creator-micro queue page and verifies the scheduled item is listed.
- Returns a three-part verdict: `JUDGEMENT` + `COVER_VERIFY` + `QUEUE_VERIFY`. Success requires all three.

## Required tools

- Python 3.11+
- `pip install playwright pydantic pyyaml typer python-dotenv pillow` (covered by `pip install .` from the kit root)
- `python -m playwright install chromium`
- `ffmpeg` on PATH (for auto cover generation)

## Environment variables

All paths default under `$BROADCAST_KIT_STATE_DIR/douyin/` (which defaults to `./state/douyin/`).

| Variable | Purpose | Default |
|---|---|---|
| `BROADCAST_KIT_STATE_DIR` | Root for all runtime state | `./state` |
| `DOUYIN_AUTH_STATE` | Playwright storage_state json path | `state/douyin/auth.json` |
| `DOUYIN_WORK_ROOT` | Working dir for screenshots and queue evidence | `state/douyin/work` |
| `DOUYIN_SCREENSHOT_DIR` | Screenshot output | `state/douyin/work/screenshots` |
| `DOUYIN_METRICS_DIR` | Metrics jsonl output dir | `state/douyin/work/metrics` |
| `DOUYIN_PUBLISH_URL` | Creator publish entrypoint | `https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page` |
| `DOUYIN_SKIP_SUBMIT` | If true/1, never click final publish | unset |
| `DOUYIN_KEEP_OPEN` | If true/1, leave Chromium open after run (debugging) | unset |
| `DOUYIN_INVENTORY_FILE` | Path to a Markdown file of already-published IDs (dedupe gate) | unset (dedupe disabled) |
| `DOUYIN_INVENTORY_ID_PATTERN` | Regex with one capture group, applied per line of inventory file | `^\|\s*([A-Za-z][A-Za-z0-9_-]+)\b` |
| `DOUYIN_METRICS_TITLE_SUFFIX` | Optional title suffix; when set, only work blocks whose title contains it are parsed | unset |

## First-time login

```bash
python -m broadcast_kit.publishers.douyin.cli login --fresh
```

A non-headless Chromium opens. Scan QR or finish login. Return to the terminal and press Enter — storage_state is saved to `DOUYIN_AUTH_STATE`. Login state survives until cookies expire (~weeks). Re-run with `--fresh` when expired.

Check login validity without re-logging in:

```bash
python -m broadcast_kit.publishers.douyin.cli login
# prints "valid" or "expired"
```

## Manifest

YAML format (call it `manifest.yaml` next to the video):

```yaml
id: example_001
title: "示例标题"
caption: "单段文案,不分段落,不用 markdown 列表。#示例 #知识 #视频"
video_file: "/absolute/path/to/video.mp4"
cover_horizontal_file: "covers/cover_4_3_1200x900.png"   # optional, auto-generated if absent
cover_vertical_file: "covers/cover_3_4_900x1200.png"     # optional, auto-generated if absent
schedule_at: "2026-05-23T19:55:00+08:00"                 # internal trigger time
douyin_schedule_publish_at: "2026-05-23T20:00:00+08:00"  # Douyin-side scheduled publish time
```

Required: `id`, `title`, `caption`, one of `video_file`/`video_url`, `douyin_schedule_publish_at`. Time fields must include timezone offset.

### Forbidden caption terms

The CLI rejects captions containing `来源`, `*`, `notebooklm`, `slidesync`, or `#notebooklm`. Strip these before writing the manifest.

## Commands

Publish a scheduled video (live):

```bash
python -m broadcast_kit.publishers.douyin.cli publish \
  --manifest /path/to/manifest.yaml \
  --schedule-publish-at "2026-05-23T20:00:00+08:00"
```

Validate-only (no final publish click):

```bash
python -m broadcast_kit.publishers.douyin.cli publish \
  --manifest /path/to/manifest.yaml \
  --schedule-publish-at "2026-05-23T20:00:00+08:00" \
  --dry-run
```

Fetch creator-center metrics (writes a jsonl line per work block):

```bash
python -m broadcast_kit.publishers.douyin.cli fetch-metrics \
  --days 7 --account default
# writes state/douyin/work/metrics/default/<YYYY-MM-DD>.jsonl
```

Alternative — invoke through the top-level broadcast-kit CLI:

```bash
broadcast-kit publish --platform douyin --manifest /path/to/manifest.yaml
broadcast-kit fetch-metrics --platform douyin --account default --days 7
```

## Success contract

A run is `success` only when all three are true:

- `JUDGEMENT: success` — publish-after page shows `审核中` / `正在发布` / `发布成功`.
- `COVER_VERIFY: True` — both horizontal and vertical covers accepted in the cover dialog.
- `QUEUE_VERIFY: True` — the scheduled title is visible in the creator-micro queue page with the matching time.

The Python entrypoint returns:

```python
{
    "platform": "douyin",
    "status": "success" | "failed" | "not_submitted" | "forbidden_caption" | "video_missing" | "cover_missing" | "schedule_missing",
    "judgement": "success" | "failed" | "not_submitted",
    "detail": "...",
    "cover_verify": True | False,
    "queue_verify": True | False,
    "screenshots": ["/abs/path/upload-after-...png", ...],
    "queue_evidence_txt": "/abs/path/...txt" | None,
    "queue_evidence_png": "/abs/path/...png" | None,
    "manifest_path": "/abs/path/manifest.yaml",
}
```

## Inventory dedupe

If `DOUYIN_INVENTORY_FILE` points at a Markdown table tracking already-published IDs, the CLI refuses to republish unless `--force-republish` is passed. The regex `DOUYIN_INVENTORY_ID_PATTERN` extracts the ID from each table line (default: leading `|` then a word-like ID).

## Auto cover generation

If a manifest cover path is missing, the publisher pulls a frame at `--cover-at-seconds 6.0` (configurable) from the video, then center-crops to 4:3 1200x900 PNG and 3:4 900x1200 PNG. Requires `ffmpeg`.

## Operational notes

- Chromium runs **non-headless**. Don't run on a machine without a display unless you have a virtual display.
- The publisher screenshots five stages: `upload-after`, `upload-meta`, `cover-after`, `publish-before`, `publish-after`. Use these for forensic checks.
- A scheduled-time fill failure aborts the run before any final publish click.
- Queue verification is best-effort. A `partial` queue status means the title was found but the time string didn't match the renderer's format — usually a `success`, but treat manually.
