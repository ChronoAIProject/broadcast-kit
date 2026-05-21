---
name: broadcast-registry-to-manifest
description: Convert a generic Broadcast Kit publish-registry item into a platform-specific manifest or publish job.
---

# Broadcast Registry To Manifest

Use this skill when a content project already exposes `contracts/publish-registry.schema.json` and the user wants a Douyin, XHS, or X manifest/job.

## Agent Instructions

- Input is a `publish_registry.json` plus one `content_id`.
- Do not require project-specific paths or private upstream repositories.
- For Douyin, require `--douyin-schedule-publish-at` and ensure the generated caption avoids forbidden terms.
- For XHS, registry artifacts need image/video assets.
- For X, the output is a generic `publish-job` JSON/YAML shape.
- Use `--dry-run` first when inspecting a new registry.

## Command Template

```bash
broadcast-kit registry-to-manifest \
  --registry <publish_registry.json> \
  --content-id <content_id> \
  --platform <douyin|xhs|x> \
  --output <manifest-or-job-path> \
  --schedule-at "<ISO-8601-with-tz>" \
  --douyin-schedule-publish-at "<ISO-8601-with-tz>" \
  --dry-run
```

Remove `--dry-run` to write the manifest/job.
