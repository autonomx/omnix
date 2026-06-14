from __future__ import annotations

from app.rpg.session.turn_memory_contract import retrieve_relevant_memories, write_turn_memory
from tests.rpg.turn_memory_test_helpers import bran_result, memory_session


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
