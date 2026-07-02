from __future__ import annotations

from app.assist_core.hermes_rpg_pipeline_result import hermes_rpg_pipeline_result


def test_hermes_rpg_pipeline_result_carries_rpg_result() -> None:
    payload = hermes_rpg_pipeline_result(
        {"session_id": "s1", "context_hash": "abc", "command_text": "check inventory"},
        {"ok": True, "turn_id": 7},
    )

    assert payload["ok"] is True
    assert payload["session_id"] == "s1"
    assert payload["context_hash"] == "abc"
    assert payload["command_text"] == "check inventory"
    assert payload["rpg_result"] == {"ok": True, "turn_id": 7}
    assert payload["state_changed"] is True
