from __future__ import annotations

from app.assist_core.hermes_sequence_loop_guard import hermes_sequence_loop_guard


def test_loop_guard_detects_duplicate_command_text() -> None:
    result = hermes_sequence_loop_guard(
        {"state_owner": "rpg_sim", "items": [{"item_id": "one", "statement": "look"}, {"item_id": "two", "statement": "look"}]}
    )

    assert result["ok"] is False
    assert result["stop_reason"] == "duplicate_command"


def test_loop_guard_detects_repeated_item_id() -> None:
    result = hermes_sequence_loop_guard(
        {"state_owner": "rpg_sim", "items": [{"item_id": "same", "statement": "look"}, {"item_id": "same", "statement": "listen"}]}
    )

    assert result["ok"] is False
    assert result["stop_reason"] == "loop_detected"


def test_loop_guard_detects_no_progress_from_last_result() -> None:
    result = hermes_sequence_loop_guard({"state_owner": "rpg_sim", "items": []}, {"last_result": {"state_changed": False}})

    assert result["ok"] is False
    assert result["stop_reason"] == "no_progress"


def test_loop_guard_detects_state_owner_mismatch() -> None:
    result = hermes_sequence_loop_guard({"state_owner": "external", "items": []})

    assert result["ok"] is False
    assert result["stop_reason"] == "state_mismatch"
