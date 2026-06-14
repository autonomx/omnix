from __future__ import annotations

from app.rpg.session.turn_memory_contract import retrieve_relevant_memories, write_turn_memory
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
    assert written["facts"] == [
        {"type": "identity_alias", "subject": "player", "key": "trail_name", "value": "Red Fox"}
    ]
    assert memory["dialogue_memories"][0]["listener_ids"] == ["npc:bran"]
    assert memory["dialogue_memories"][0]["visibility"] == "private"


def test_turn_memory_retrieves_private_bran_memory_for_bran_recall() -> None:
    session_after_fact, _ = write_turn_memory(
        memory_session(),
        bran_result(tick=1, player_input="Bran, my trail name is Red Fox."),
        player_input="Bran, my trail name is Red Fox.",
    )
    session_after_filler, _ = write_turn_memory(
        session_after_fact,
        bran_result(tick=2, player_input="What food is on hand?"),
        player_input="What food is on hand?",
    )
    retrieved = retrieve_relevant_memories(
        session_after_filler["runtime_state"]["turn_memory"],
        player_input="Bran, do you remember my trail name?",
        addressed_actor_id="npc:bran",
        location_id="loc:rusty_flagon",
    )
    assert retrieved[0]["facts"][0]["value"] == "Red Fox"
    assert retrieved[0]["listener_ids"] == ["npc:bran"]
