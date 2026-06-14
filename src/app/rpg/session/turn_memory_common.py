from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

FORMAT_VERSION = "rpg_turn_memory_contract_v1"
RECENT_TURN_LIMIT = 12
DIALOGUE_MEMORY_LIMIT = 20
RETRIEVAL_LIMIT = 5


def d(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def l(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def s(value: Any) -> str:
    return "" if value is None else str(value)


def i(value: Any, default: int = 0) -> int:
    try:
        return default if isinstance(value, bool) else int(value)
    except (TypeError, ValueError):
        return default


def first(*values: Any) -> str:
    return next((text for value in values if (text := s(value).strip())), "")


def bounded(values: list[Any], limit: int) -> list[dict[str, Any]]:
    entries = [deepcopy(value) for value in values if isinstance(value, Mapping)]
    return entries[-max(1, int(limit)) :]
