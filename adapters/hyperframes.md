# Adapter: hyperframes

## External Boundary

Broadcast Kit emits and validates storyboard and HTML composition contracts. HyperFrames owns HTML rendering, animation timing, validation, previews, and video export.

## Authentication

No Broadcast Kit credential is introduced. Use whatever upstream HyperFrames renderer requires in its own environment.

## Invocation

Validation route:

```bash
hyperframes validate <index.html> --json
```

The expected composition shape is upstream HyperFrames HTML with `data-composition-id`, `data-width`, `data-height`, `data-duration`, `data-fps`, `.clip` nodes, and paused timelines on `window.__timelines`.

## Dry-Run

Dry-run plans or runs validation only. It must not render or submit external jobs unless the user asks for a real render through the upstream CLI.
