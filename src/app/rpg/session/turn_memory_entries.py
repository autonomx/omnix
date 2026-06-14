from __future__ import annotations

from typing import Any, Mapping

from app.rpg.session.turn_memory_common import d, first, i, s
from app.rpg.session.turn_memory_dialogue_entry import build_dialogue_memory_entry
from app.rpg.session.turn_memory_facts import extract_player_memory_facts
from app.rpg.session.turn_memory_result_extractors import action_type, npc, runtime_state, simulation_state, summary
from app.rpg.session.turn_memory_topics import topic_tags


def build_turn_memory_entry(
    *,
    session: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None,
    player_input: str,
) -> dict[str, Any]:
    resolved_runtime = runtime_state(session, result)
    resolved_simulation = simulation_state(session, result)
    result_dict = d(result)
    tick = i(result_dict.get("tick"), i(resolved_runtime.get("tick"), 0))
    turn_id = first(result_dict.get("turn_id"), f"turn:{tick}")
    resolved_action_type = action_type(result)
    resolved_npc = npc(result)
    facts = extract_player_memory_facts(player_input)
    return {
        "id": f"memory-turn:{turn_id}",
        "turn_id": turn_id,
        "tick": tick,
        "player_input": s(player_input).strip()[:500],
        "action_type": resolved_action_type,
        "summary": summary(result),
        "location_id": first(resolved_simulation.get("current_location_id"), resolved_simulation.get("location_id")),
        "location_name": first(resolved_simulation.get("location_name"), resolved_simulation.get("current_location_name")),
        "npc_id": resolved_npc["id"],
        "npc_speaker": resolved_npc["speaker"],
        "npc_line": resolved_npc["line"][:500],
        "topic_tags": topic_tags(player_input, resolved_action_type, facts),
        "salience": 0.85 if facts else (0.65 if resolved_npc["speaker"] else 0.35),
        "source": "deterministic_turn_memory_writer_v1",
    }


def is_dialogue_memory(player_input: str, result: Mapping[str, Any] | None, facts: list[dict[str, str]]) -> bool:
    resolved_npc = npc(result)
    resolved_action_type = action_type(result).lower()
    return bool(resolved_npc["speaker"] or resolved_npc["line"] or facts or "dialogue" in resolved_action_type or "npc" in resolved_action_type)


__all__ = ["build_dialogue_memory_entry", "build_turn_memory_entry", "is_dialogue_memory"]
