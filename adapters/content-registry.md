# Adapter: content-registry

## External Boundary

Broadcast Kit can consume any repository or workspace that emits a JSON publish registry matching `contracts/publish-registry.schema.json`. It reads ready media metadata and normalizes it into Broadcast Kit contracts; it does not generate source content or mutate the upstream project.

## Registry Shape

Use a JSON file such as:

```json
{
  "schema_version": "broadcast.publish_registry.v0",
  "registry_id": "weekly-batch",
  "generated_at": "2026-05-18T00:00:00Z",
  "source": {
    "type": "repo",
    "repo": "<your-org>/<your-content-repo>",
    "path": "workspace/publish_registry.json"
  },
  "items": [
    {
      "content_id": "item-001",
      "title": "Example title",
      "language": "zh",
      "ready": true,
      "platform_targets": ["douyin", "xhs", "x"],
      "artifacts": {
        "video_file": "/absolute/path/to/video.mp4",
        "cover_horizontal_file": "/absolute/path/to/cover-4x3.png",
        "cover_vertical_file": "/absolute/path/to/cover-3x4.png"
      }
    }
  ]
}
```

## Authentication

Use the upstream repository or release system's existing authentication, such as `gh auth` or `GITHUB_TOKEN` for release reads. Broadcast Kit does not store repository credentials.

## Dry-Run

Dry-run validates the registry contract and reports the normalization plan. It must not regenerate upstream media or publish anything.
