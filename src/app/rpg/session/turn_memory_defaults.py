from __future__ import annotations

from typing import Any, Mapping

from app.rpg.session.turn_memory_common import (
    DIALOGUE_MEMORY_LIMIT,
    FORMAT_VERSION,
    RECENT_TURN_LIMIT,
    bounded,
    d,
    l,
)


def memory_state(session: Mapping[str, Any] | None) -> dict[str, Any]:
    memory = d(d(d(session).get("runtime_state")).get("turn_memory"))
    return {
        "format_version": FORMAT_VERSION,
        "recent_turns": bounded(l(memory.get("recent_turns")), RECENT_TURN_LIMIT),
        "dialogue_memories": bounded(
            l(memory.get("dialogue_memories")),
            DIALOGUE_MEMORY_LIMIT,
        ),
    }
