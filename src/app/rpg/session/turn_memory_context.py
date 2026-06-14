from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from app.rpg.session.turn_memory_common import FORMAT_VERSION, d, l, memory_state, s
from app.rpg.session.turn_memory_retrieval import retrieve_relevant_memories
from app.rpg.session.turn_memory_writer import write_turn_memory


def _payload(memory: Mapping[str, Any], written: Mapping[str, Any], player_input: str) -> dict[str, Any]:
    turn_entry = d(written.get("recent_turn"))
    retrieved = retrieve_relevant_memories(
        memory,
        player_input=player_input,
        addressed_actor_id=s(turn_entry.get("npc_id")),
        location_id=s(turn_entry.get("location_id")),
    )
    return {
        "format_version": FORMAT_VERSION,
        "written": written,
        "retrieved": retrieved,
        "recent_turn_count": len(l(memory.get("recent_turns"))),
        "dialogue_memory_count": len(l(memory.get("dialogue_memories"))),
        "state_path": "runtime_state.turn_memory",
        "deterministic": True,
        "presentation_only": True,
    }


def attach_turn_memory_context_with_session(
    result: Mapping[str, Any],
    *,
    session: Mapping[str, Any] | None,
    player_input: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    updated_session, written = write_turn_memory(session, result, player_input=player_input)
    payload = _payload(memory_state(updated_session), written, player_input)
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
