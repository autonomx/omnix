from __future__ import annotations

from typing import Any

from app.rpg.session.turn_memory_common import first, s
from app.rpg.session.turn_memory_topics import topic_tags


def turn_entry_dict(
    *,
    turn_id: str,
    tick: int,
    player_input: str,
    action_type: str,
    summary: str,
    simulation: dict[str, Any],
    npc: dict[str, str],
    facts: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "id": f"memory-turn:{turn_id}",
        "turn_id": turn_id,
        "tick": tick,
        "player_input": s(player_input).strip()[:500],
        "action_type": action_type,
        "summary": summary,
        "location_id": first(simulation.get("current_location_id"), simulation.get("location_id")),
        "location_name": first(simulation.get("location_name"), simulation.get("current_location_name")),
        "npc_id": npc["id"],
        "npc_speaker": npc["speaker"],
        "npc_line": npc["line"][:500],
        "topic_tags": topic_tags(player_input, action_type, facts),
        "salience": 0.85 if facts else (0.65 if npc["speaker"] else 0.35),
        "source": "deterministic_turn_memory_writer_v1",
    }
