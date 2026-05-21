# Tests

This repository intentionally leaves tests empty for v0 scaffolding.

Future test coverage should include:

- Contract validation for all six JSON schemas.
- Douyin BRIEF v2 manifest validation, including `cover_horizontal_file`, `cover_vertical_file`, `douyin_schedule_publish_at`, forbidden caption terms, inventory dedupe, and success triple enforcement.
- Dry-run behavior for all five CLI subcommands.
- Subprocess adapter JSON parsing and non-zero exit handling.
- Skill installation idempotency for Claude, Codex, and Cursor skill directories.

Do not add real credentials, cookies, account data, or platform artifacts to tests.
