from __future__ import annotations


def memory_session() -> dict:
    return {
        "manifest": {"session_id": "session-memory-1"},
        "simulation_state": {"current_location_id": "loc:rusty_flagon", "location_name": "Rusty Flagon"},
        "runtime_state": {"tick": 1},
    }


def bran_result(*, tick: int = 1, player_input: str = "") -> dict:
    npc = {"id": "npc:bran", "speaker": "Bran", "line": "I'll remember what matters."}
    return {
        "ok": True,
        "turn_id": f"turn-{tick}",
        "tick": tick,
        "action_type": "npc_interpretive_dialogue",
        "summary": "Bran answers carefully.",
        "npc": npc,
        "result": {"action_type": "npc_interpretive_dialogue", "summary": "Bran answers carefully.", "npc": npc},
        "simulation_state": {"current_location_id": "loc:rusty_flagon", "location_name": "Rusty Flagon"},
        "runtime_state": {"tick": tick},
        "player_input": player_input,
    }
