---
name: broadcast-publish-xhs
description: Validate and publish a Xiaohongshu manifest through Broadcast Kit's self-contained Playwright publisher.
---

# Broadcast Publish XHS

Use this skill when the user wants to publish an existing image set or one finished video to Xiaohongshu through Broadcast Kit.

Broadcast Kit owns the XHS Playwright flow in `broadcast_kit/publishers/xhs/`. There is no external daemon handoff and no `--adapter-repo` option.

## Agent Instructions

- XHS is published through a visible Playwright browser against `creator.xiaohongshu.com`; it is not an HTTP API.
- Login is stored at `state/xhs/auth.json`. If login is missing or expired, run:

```bash
python -m broadcast_kit.publishers.xhs.cli login --fresh
```

- Use the platform manifest shape below. Keep title and body within XHS limits before live publish.
- Use `--dry-run` first when validating a new machine, new account, or unfamiliar asset type.
- XHS metrics are not implemented in this kit yet; only publish is self-contained.

## Manifest Shape

```yaml
id: "stable-content-id"
platform: "xhs"
title: "20字以内标题"
body: "正文，1000字以内"
topics:
  - "话题1"
  - "话题2"
asset_kind: "video"   # "video" or "image"
asset_paths:
  - "/absolute/path/to/final.mp4"
```

Rules:

- `title` must be 20 characters or fewer.
- `body` must be 1000 characters or fewer.
- `asset_kind: video` expects exactly one video path.
- `asset_kind: image` expects one or more image paths, up to the platform limit.
- Put topics in `topics`; do not rely on raw `#hashtag` text in the body.

## Command Template

Dry-run:

```bash
broadcast-kit publish \
  --platform xhs \
  --manifest <manifest.yaml> \
  --dry-run
```

Live publish:

```bash
broadcast-kit publish \
  --platform xhs \
  --manifest <manifest.yaml>
```

## Known-Good Existing-Video Path

If the user has a finished video and wants the one-command orchestrator to build a draft then publish:

```bash
broadcast-kit produce-publish \
  --input <source-or-notes.md> \
  --video-file /absolute/path/to/final.mp4 \
  --platforms xhs \
  --dry-run
```

Remove `--dry-run` only after the browser flow and manifest validation look correct.
