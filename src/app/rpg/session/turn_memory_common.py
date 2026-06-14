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
    return [deepcopy(value) for value in values if isinstance(value, Mapping)][-max(1, int(limit)) :]


def memory_state(session: Mapping[str, Any] | None) -> dict[str, Any]:
    memory = d(d(d(session).get("runtime_state")).get("turn_memory"))
    return {
        "format_version": FORMAT_VERSION,
        "recent_turns": bounded(l(memory.get("recent_turns")), RECENT_TURN_LIMIT),
        "dialogue_memories": bounded(l(memory.get("dialogue_memories")), DIALOGUE_MEMORY_LIMIT),
    }
