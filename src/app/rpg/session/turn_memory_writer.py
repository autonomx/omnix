from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from app.rpg.session.turn_memory_common import (
    DIALOGUE_MEMORY_LIMIT,
    RECENT_TURN_LIMIT,
    bounded,
    d,
)
from app.rpg.session.turn_memory_defaults import memory_state
from app.rpg.session.turn_memory_dialogue import memory_dialogue
from app.rpg.session.turn_memory_turn_entry import turn_entry


def write_turn_memory(
    session: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None,
    *,
    player_input: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    updated = deepcopy(d(session))
    runtime = d(updated.get("runtime_state"))
    memory = memory_state(updated)
    turn, facts, npc = turn_entry(result, updated, player_input)
    memory["recent_turns"] = bounded([*memory["recent_turns"], turn], RECENT_TURN_LIMIT)
    dialogue = memory_dialogue(turn, facts, npc) if npc["id"] or facts else None
    if dialogue:
        memory["dialogue_memories"] = bounded(
            [*memory["dialogue_memories"], dialogue],
            DIALOGUE_MEMORY_LIMIT,
        )
    runtime["turn_memory"] = memory
    updated["runtime_state"] = runtime
    return updated, {
        "recent_turn": deepcopy(turn),
        "dialogue_memory": deepcopy(dialogue),
        "facts": deepcopy(facts),
    }
