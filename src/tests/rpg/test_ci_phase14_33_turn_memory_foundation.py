from __future__ import annotations

from app.rpg.session.turn_memory_contract import write_turn_memory
from tests.rpg.turn_memory_test_helpers import bran_result, memory_session


def test_turn_memory_writes_recent_turn_and_dialogue_fact() -> None:
    updated_session, written = write_turn_memory(
        memory_session(),
        bran_result(player_input="Bran, my trail name is Red Fox."),
        player_input="Bran, my trail name is Red Fox.",
    )
    memory = updated_session["runtime_state"]["turn_memory"]
    assert memory["format_version"] == "rpg_turn_memory_contract_v1"
    assert len(memory["recent_turns"]) == 1
    assert len(memory["dialogue_memories"]) == 1
    assert written["facts"] == [{
        "type": "identity_alias",
        "subject": "player",
        "key": "trail_name",
        "value": "Red Fox",
    }]
    assert memory["dialogue_memories"][0]["listener_ids"] == ["npc:bran"]
    assert memory["dialogue_memories"][0]["visibility"] == "private"
