from __future__ import annotations

from app.rpg.session.turn_memory_contract import attach_turn_memory_context_with_session
from tests.rpg.turn_memory_test_helpers import bran_result, memory_session


def test_attach_turn_memory_context_adds_top_level_and_nested_payload() -> None:
    result, updated_session = attach_turn_memory_context_with_session(
        bran_result(tick=1, player_input="My trail name is Red Fox."),
        session=memory_session(),
        player_input="My trail name is Red Fox.",
    )

    assert result["turn_memory"]["deterministic"] is True
    assert result["turn_memory"]["dialogue_memory_count"] == 1
    assert result["result"]["turn_memory"]["written"]["facts"][0]["value"] == "Red Fox"
    memories = updated_session["runtime_state"]["turn_memory"]["dialogue_memories"]
    assert memories[0]["facts"][0]["value"] == "Red Fox"
