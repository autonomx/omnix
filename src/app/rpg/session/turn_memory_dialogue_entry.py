from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from app.rpg.session.turn_memory_common import first, i, l, s


def build_dialogue_memory_entry(turn_entry: Mapping[str, Any], facts: list[dict[str, str]]) -> dict[str, Any]:
    npc_id = s(turn_entry.get("npc_id"))
    npc_speaker = s(turn_entry.get("npc_speaker"))
    listener_id = npc_id or (f"npc:{npc_speaker.lower().replace(' ', '_')}" if npc_speaker else "")
    return {
        "id": f"memory-dialogue:{s(turn_entry.get('turn_id'))}:{len(facts)}",
        "turn_id": s(turn_entry.get("turn_id")),
        "tick": i(turn_entry.get("tick"), 0),
        "speaker_id": "player",
        "listener_ids": [listener_id] if listener_id else [],
        "listener_names": [npc_speaker] if npc_speaker else [],
        "location_id": s(turn_entry.get("location_id")),
        "player_text": s(turn_entry.get("player_input")),
        "npc_line": s(turn_entry.get("npc_line")),
        "summary": first(turn_entry.get("summary"), f"Player spoke with {npc_speaker}." if npc_speaker else "Player had a dialogue exchange."),
        "facts": deepcopy(facts),
        "topic_tags": l(turn_entry.get("topic_tags")),
        "visibility": "private" if listener_id else "session",
        "salience": 0.9 if facts else 0.6,
        "source": "deterministic_dialogue_memory_writer_v1",
    }
