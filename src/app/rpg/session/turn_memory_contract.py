from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from app.rpg.session.turn_memory_common import (
    DIALOGUE_MEMORY_LIMIT,
    FORMAT_VERSION,
    RECENT_TURN_LIMIT,
    bounded,
    d,
    extract_player_memory_facts,
    l,
    memory_state,
    s,
)
from app.rpg.session.turn_memory_entries import (
    build_dialogue_memory_entry,
    build_turn_memory_entry,
    is_dialogue_memory,
)
from app.rpg.session.turn_memory_retrieval import retrieve_relevant_memories


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


def attach_turn_memory_context_with_session(
    result: Mapping[str, Any],
    *,
    session: Mapping[str, Any] | None,
    player_input: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    updated_session, written = write_turn_memory(session, result, player_input=player_input)
    memory = memory_state(updated_session)
    turn_entry = d(written.get("recent_turn"))
    retrieved = retrieve_relevant_memories(
        memory,
        player_input=player_input,
        addressed_actor_id=s(turn_entry.get("npc_id")),
        location_id=s(turn_entry.get("location_id")),
    )
    payload = {
        "format_version": FORMAT_VERSION,
        "written": written,
        "retrieved": retrieved,
        "recent_turn_count": len(l(memory.get("recent_turns"))),
        "dialogue_memory_count": len(l(memory.get("dialogue_memories"))),
        "state_path": "runtime_state.turn_memory",
        "deterministic": True,
        "presentation_only": True,
    }
    updated_result = deepcopy(d(result))
    updated_result["turn_memory"] = deepcopy(payload)
    nested = d(updated_result.get("result"))
    if nested:
        nested["turn_memory"] = deepcopy(payload)
        updated_result["result"] = nested
    result_session = d(updated_result.get("session"))
    if result_session:
        result_session["runtime_state"] = d(updated_session.get("runtime_state"))
        updated_result["session"] = result_session
    return updated_result, updated_session
