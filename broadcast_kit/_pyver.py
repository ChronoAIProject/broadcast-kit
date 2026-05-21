"""Minimal Python-version guard for broadcast-kit CLI entry points.

The package declares ``requires-python = ">=3.11"`` in ``pyproject.toml`` and pip
honors that at install time. But when broadcast-kit is invoked via ``python -m``
under an older interpreter (common during onboarding where ``python`` is 3.10),
the failure mode is a deep ``ImportError`` from a downstream dependency. This
helper produces a friendly, actionable message instead.

Keep this module dependency-free (stdlib only) and importable under Python 3.8+
so the version check itself doesn't blow up before it can run.
"""

from __future__ import annotations

import sys

MIN_PY = (3, 11)


def require_min_python(module_hint: str) -> None:
    """Exit with code 2 and a friendly message if running under Python < 3.11.

    Call this as the FIRST statement of each CLI ``main()`` function — before
    any other import that might transitively pull in code using 3.11+ syntax
    (``X | Y`` unions, ``Self`` from typing, structural typing extras, etc.).

    ``module_hint`` is the dotted module path the user should re-invoke under
    a newer interpreter, e.g. ``"broadcast_kit.cli"`` or
    ``"broadcast_kit.publishers.xhs.cli"``. It is substituted into the
    suggested commands.
    """

    if sys.version_info >= MIN_PY:
        return
    current = ".".join(str(x) for x in sys.version_info[:3])
    msg = (
        f"broadcast-kit requires Python >= {MIN_PY[0]}.{MIN_PY[1]} (you have {current}).\n"
        f"On macOS/Linux try: python3.11 -m {module_hint} ...\n"
        f"On Windows try:     py -3.12 -m {module_hint} ..."
    )
    print(msg, file=sys.stderr)
    raise SystemExit(2)


__all__ = ["MIN_PY", "require_min_python"]
