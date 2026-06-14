from __future__ import annotations

from typing import Any, Mapping

from app.rpg.session.turn_memory_common import i


def memory_dialogue(
    turn: Mapping[str, Any],
    facts: list[dict[str, str]],
    npc: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "id": f"memory-dialogue:{turn['turn_id']}:0",
        "turn_id": str(turn["turn_id"]),
        "tick": i(turn.get("tick")),
        "speaker_id": "player",
        "listener_ids": [npc["id"]] if npc.get("id") else [],
        "location_id": str(turn.get("location_id") or ""),
        "player_text": str(turn.get("player_input") or ""),
        "npc_line": npc.get("line", ""),
        "facts": facts,
        "visibility": "private" if npc.get("id") else "session",
        "salience": 0.9 if facts else 0.6,
    }
