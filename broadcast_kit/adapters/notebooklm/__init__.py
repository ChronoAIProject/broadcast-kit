"""NotebookLM adapter — generate slides + audio from PDF/markdown via Google NotebookLM.

Thin wrapper around the `notebooklm-py` pip package + its `notebooklm` CLI.
First-time setup:

    pip install notebooklm-py
    notebooklm login   # OAuth browser flow

Public API:

    from broadcast_kit.adapters.notebooklm import (
        generate,
        list_notebooks,
        status,
        download,
        NotebookLMArtifacts,
    )

See ``adapters/notebooklm.md`` for the boundary contract.
"""

from __future__ import annotations

from .generate import (
    NotebookLMArtifacts,
    download,
    generate,
    list_notebooks,
    status,
)

__all__ = [
    "NotebookLMArtifacts",
    "download",
    "generate",
    "list_notebooks",
    "status",
]
