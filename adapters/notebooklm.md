# Adapter: notebooklm

## External Boundary

The NotebookLM adapter generates slide decks and audio podcasts from arbitrary
content (PDF, markdown, plain text, or a directory of those) via Google
NotebookLM. It is an in-package adapter shipped at
`broadcast_kit/adapters/notebooklm/` and uses the third-party `notebooklm-py`
pip package under the hood (the `notebooklm` CLI is invoked as a subprocess).

Broadcast Kit owns the input normalization, output layout, status polling, and
manifest writing; it does not own Google credentials or the NotebookLM RPC
protocol.

## Authentication

One-time setup outside Broadcast Kit:

```bash
pip install notebooklm-py
notebooklm login   # OAuth browser flow against your Google account
```

Or via the adapter CLI:

```bash
python -m broadcast_kit.adapters.notebooklm.cli login
```

Cookies are persisted by `notebooklm-py` itself; Broadcast Kit does not store
Google credentials.

## Inputs

The `generate()` entry point accepts:

| Input type           | Handling                                                |
|----------------------|---------------------------------------------------------|
| `*.pdf`              | Uploaded as-is to a new notebook.                       |
| `*.md`, `*.markdown` | Pre-converted to PDF.                                   |
| `*.txt`              | Pre-converted to PDF.                                   |
| Directory            | All `.md` / `.markdown` / `.txt` files concatenated then converted to PDF. |

Conversion tries `pandoc`, then `weasyprint`, then `markdown-pdf` in that
order. If none are installed, the adapter raises `OptimizerError` with an
install hint and does not call NotebookLM.

## Outputs

Artifacts land in `output_dir` (default
`$BROADCAST_KIT_STATE_DIR/notebooklm/<slug>/`, or `./state/notebooklm/<slug>/`
if the env var is unset):

- `<slug>_slides.pdf` — slide deck PDF (if `slides` requested)
- `<slug>_podcast.wav` — deep-dive audio (if `audio` requested)
- `<slug>_manifest.json` — timestamp, notebook id, status, paths
- Intermediate PDFs (when input was markdown/text) live alongside the artifacts

The `<slug>` is derived from the input filename via the same regex
normalization used elsewhere in Broadcast Kit (drops `submitted_YYYY_` /
`YYYY_` prefixes, collapses non-alphanumeric runs).

## Environment Variables

| Variable                    | Effect                                                  |
|-----------------------------|---------------------------------------------------------|
| `BROADCAST_KIT_STATE_DIR`   | Root for default output (`<root>/notebooklm/<slug>/`).  |
| `PYTHONIOENCODING`          | Forced to `utf-8` for subprocess calls on Windows.      |

No NotebookLM-specific env vars; auth state belongs to `notebooklm-py`.

## Invocation

Library:

```python
from pathlib import Path
from broadcast_kit.adapters.notebooklm import generate

artifacts = generate(
    input_path=Path("paper.pdf"),
    output_dir=Path("state/notebooklm/paper"),
    kinds=["slides", "audio"],
    poll_interval_seconds=15,
    max_wait_seconds=600,
)
print(artifacts.slide_deck_path, artifacts.audio_path)
```

CLI:

```bash
python -m broadcast_kit.adapters.notebooklm.cli generate --input paper.pdf
python -m broadcast_kit.adapters.notebooklm.cli generate --input notes/ --kinds slides
python -m broadcast_kit.adapters.notebooklm.cli list
python -m broadcast_kit.adapters.notebooklm.cli status --notebook-id <id>
python -m broadcast_kit.adapters.notebooklm.cli download --notebook-id <id> --output-dir out/
```

The `broadcast-kit-notebooklm` console script (registered in `pyproject.toml`)
is equivalent to the `python -m ...cli` form.

## Dry-Run

`generate(..., dry_run=True)` and `--dry-run` emit the planned command sequence
via `command_plan(...)` and return a `NotebookLMArtifacts` with
`status="dry_run"`. No subprocess is invoked.

## Failure Modes

| Status        | Meaning                                                            |
|---------------|--------------------------------------------------------------------|
| `complete`    | All requested artifacts downloaded and non-trivial in size.        |
| `partial`     | Some artifacts downloaded; poll timed out or NotebookLM reported failures. |
| `error`       | No artifacts downloaded.                                           |
| `dry_run`     | Plan-only invocation; no work performed.                           |

The adapter raises `OptimizerError` (from `broadcast_kit.optimizers.base`) when:

- `notebooklm-py` is not installed or the `notebooklm` CLI is not on `PATH`.
- A non-PDF input is supplied but no PDF converter (`pandoc`, `weasyprint`,
  `markdown-pdf`) is available.
- The `notebooklm` CLI exits non-zero or times out during create / source-add
  / generate calls.

Download failures for individual artifacts are demoted to `partial` / `error`
on the returned dataclass rather than raised, so a single missing slide deck
does not lose the audio.
