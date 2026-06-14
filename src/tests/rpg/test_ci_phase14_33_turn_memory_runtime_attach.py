from __future__ import annotations

from app.rpg.session.turn_memory_runtime_hook import attach_turn_memory_to_runtime_result
from tests.rpg.turn_memory_test_helpers import bran_result, memory_session


def test_attach_turn_memory_runtime_result_reports_payload_without_persistence_for_override() -> None:
    result = attach_turn_memory_to_runtime_result(
        bran_result(tick=4, player_input="Bran, my name is Mara."),
        call_context={
            "session_id": "",
            "player_input": "Bran, my name is Mara.",
            "session_override": memory_session(),
        },
    )

    assert result["turn_memory_runtime_hook"]["attached"] is True
    assert result["turn_memory_runtime_hook"]["persisted"] is False
    assert result["turn_memory"]["written"]["facts"][0] == {
        "type": "identity_alias",
        "subject": "player",
        "key": "name",
        "value": "Mara",
    }
