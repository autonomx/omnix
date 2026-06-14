from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from app.rpg.session.turn_memory_common import DIALOGUE_MEMORY_LIMIT, RECENT_TURN_LIMIT, bounded, d, memory_state
from app.rpg.session.turn_memory_entries import (
    build_dialogue_memory_entry,
    build_turn_memory_entry,
    is_dialogue_memory,
)
from app.rpg.session.turn_memory_facts import extract_player_memory_facts


def write_turn_memory(
    session: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None,
    *,
    player_input: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    updated_session = deepcopy(d(session))
    resolved_runtime = d(updated_session.get("runtime_state"))
    memory = memory_state(updated_session)
    turn_entry = build_turn_memory_entry(
        session=updated_session,
        result=result,
        player_input=player_input,
    )
    facts = extract_player_memory_facts(player_input)
    memory["recent_turns"] = bounded(
        [*memory["recent_turns"], turn_entry],
        RECENT_TURN_LIMIT,
    )
    written: dict[str, Any] = {
        "recent_turn": deepcopy(turn_entry),
        "dialogue_memory": None,
        "facts": deepcopy(facts),
    }
    if is_dialogue_memory(player_input, result, facts):
        dialogue_entry = build_dialogue_memory_entry(turn_entry, facts)
        memory["dialogue_memories"] = bounded(
            [*memory["dialogue_memories"], dialogue_entry],
            DIALOGUE_MEMORY_LIMIT,
        )
        written["dialogue_memory"] = deepcopy(dialogue_entry)
    resolved_runtime["turn_memory"] = memory
    updated_session["runtime_state"] = resolved_runtime
    return updated_session, written
