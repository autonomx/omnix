from __future__ import annotations

from typing import Any, Mapping

from app.rpg.session.turn_memory_common import d, first, i, s
from app.rpg.session.turn_memory_writer_helpers import memory_facts, memory_npc


def turn_entry(
    result: Mapping[str, Any] | None,
    session: Mapping[str, Any] | None,
    player_input: str,
) -> tuple[dict[str, Any], list[dict[str, str]], dict[str, str]]:
    result_dict = d(result)
    runtime = d(d(session).get("runtime_state"))
    sim = d(result_dict.get("simulation_state") or d(session).get("simulation_state"))
    npc = memory_npc(result)
    tick = i(result_dict.get("tick"), i(runtime.get("tick"), 0))
    turn_id = first(result_dict.get("turn_id"), f"turn:{tick}")
    facts = memory_facts(player_input)
    return {
        "id": f"memory-turn:{turn_id}",
        "turn_id": turn_id,
        "tick": tick,
        "player_input": s(player_input)[:500],
        "summary": first(result_dict.get("summary")),
        "location_id": first(sim.get("current_location_id"), sim.get("location_id")),
        "npc_id": npc["id"],
        "npc_speaker": npc["speaker"],
        "npc_line": npc["line"][:500],
        "salience": 0.85 if facts else 0.35,
    }, facts, npc
