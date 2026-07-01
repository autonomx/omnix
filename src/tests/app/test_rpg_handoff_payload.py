from __future__ import annotations

from app.assist_core.rpg_handoff_payload import rpg_handoff_payload


def test_rpg_handoff_payload_is_proposal_only_and_not_applied() -> None:
    payload = rpg_handoff_payload("inspect the door")

    assert payload["ok"] is True
    assert payload["command_text"] == "inspect the door"
    assert payload["proposal_only"] is True
    assert payload["applied"] is False
    assert payload["simulation_must_validate"] is True
    assert payload["review_required"] is True
    assert payload["read_only"] is True
    assert payload["executes"] is False


def test_rpg_handoff_payload_rejects_blank_command_text_safely() -> None:
    payload = rpg_handoff_payload("   ")

    assert payload["ok"] is False
    assert payload["command_text"] == ""
    assert payload["applied"] is False
    assert payload["simulation_must_validate"] is True
    assert payload["executes"] is False
