from __future__ import annotations

from app.rpg.session.turn_memory_contract import retrieve_relevant_memories, write_turn_memory
from tests.rpg.turn_memory_test_helpers import bran_result, memory_session


def test_turn_memory_hides_private_bran_memory_from_guard() -> None:
    session_after_fact, _ = write_turn_memory(
        memory_session(),
        bran_result(tick=1, player_input="Bran, my trail name is Red Fox."),
        player_input="Bran, my trail name is Red Fox.",
    )

    retrieved = retrieve_relevant_memories(
        session_after_fact["runtime_state"]["turn_memory"],
        player_input="Guard, do you remember my trail name?",
        addressed_actor_id="npc:guard",
        location_id="loc:rusty_flagon",
    )

    assert retrieved == []
