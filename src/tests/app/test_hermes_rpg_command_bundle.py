from __future__ import annotations

from app.assist_core.hermes_rpg_command_bundle import hermes_rpg_command_bundle


def test_hermes_rpg_command_bundle_returns_card_for_matching_ticket() -> None:
    ticket = {"ticket_id": "t1", "command": "check inventory", "valid": True}

    payload = hermes_rpg_command_bundle(ticket, "t1")

    assert payload["ok"] is True
    assert payload["match"]["matched"] is True
    assert payload["card"]["command_text"] == "check inventory"
    assert payload["card"]["submits"] is False
    assert payload["state_changed"] is False


def test_hermes_rpg_command_bundle_rejects_mismatch() -> None:
    ticket = {"ticket_id": "t1", "command": "check inventory", "valid": True}

    payload = hermes_rpg_command_bundle(ticket, "wrong")

    assert payload["ok"] is False
    assert payload["match"]["error"] == "ticket_mismatch"
    assert payload["card"]["fills_input"] is False
    assert payload["state_changed"] is False
