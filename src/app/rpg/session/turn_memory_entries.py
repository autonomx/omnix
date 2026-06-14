from __future__ import annotations

from typing import Any, Mapping

from app.rpg.session.turn_memory_common import d, first, i
from app.rpg.session.turn_memory_dialogue_entry import build_dialogue_memory_entry
from app.rpg.session.turn_memory_facts import extract_player_memory_facts
from app.rpg.session.turn_memory_result_extractors import action_type, npc, runtime_state, simulation_state, summary
from app.rpg.session.turn_memory_turn_entry import turn_entry_dict


def build_turn_memory_entry(
    *, session: Mapping[str, Any] | None, result: Mapping[str, Any] | None, player_input: str
) -> dict[str, Any]:
    resolved_runtime = runtime_state(session, result)
    resolved_simulation = simulation_state(session, result)
    result_dict = d(result)
    tick = i(result_dict.get("tick"), i(resolved_runtime.get("tick"), 0))
    resolved_action_type = action_type(result)
    return turn_entry_dict(
        turn_id=first(result_dict.get("turn_id"), f"turn:{tick}"),
        tick=tick,
        player_input=player_input,
        action_type=resolved_action_type,
        summary=summary(result),
        simulation=resolved_simulation,
        npc=npc(result),
        facts=extract_player_memory_facts(player_input),
    )


def is_dialogue_memory(player_input: str, result: Mapping[str, Any] | None, facts: list[dict[str, str]]) -> bool:
    resolved_npc = npc(result)
    resolved_action_type = action_type(result).lower()
    return bool(resolved_npc["speaker"] or resolved_npc["line"] or facts or "dialogue" in resolved_action_type or "npc" in resolved_action_type)


__all__ = ["build_dialogue_memory_entry", "build_turn_memory_entry", "is_dialogue_memory"]
