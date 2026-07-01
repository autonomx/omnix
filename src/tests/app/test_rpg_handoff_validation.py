from __future__ import annotations

from app.assist_core.rpg_handoff_validation import validate_rpg_handoff_payload


def test_rpg_handoff_validation_accepts_review_payload() -> None:
    payload = validate_rpg_handoff_payload(
        {"command_text": "inspect", "simulation_must_validate": True}
    )

    assert payload["ok"] is True
    assert payload["status"] == "valid_for_review"
    assert payload["review_required"] is True
    assert payload["read_only"] is True
    assert payload["executes"] is False


def test_rpg_handoff_validation_blocks_state_keys_without_marker() -> None:
    payload = validate_rpg_handoff_payload({"command_text": "inspect", "state_delta": {}})

    assert payload["ok"] is False
    assert payload["status"] == "simulation_validation_required"
    assert payload["blocked_keys"] == ["state_delta"]
    assert payload["executes"] is False


def test_rpg_handoff_validation_allows_state_keys_only_for_review_with_marker() -> None:
    payload = validate_rpg_handoff_payload(
        {"command_text": "inspect", "state_delta": {}, "simulation_must_validate": True}
    )

    assert payload["ok"] is True
    assert payload["blocked_keys"] == ["state_delta"]
    assert payload["review_required"] is True
    assert payload["executes"] is False
