from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from broadcast_kit.contracts import ContractError, validate_publish_registry


def read_publish_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ContractError(f"publish registry not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ContractError("publish registry must be a JSON object")
    validate_publish_registry(data, path)
    return data

