from __future__ import annotations

from app.assist_core.hermes_rpg_command_bundle import hermes_rpg_command_bundle
from app.assist_core.hermes_rpg_intent_guard import hermes_rpg_intent_guard


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


def test_hermes_rpg_intent_guard_requires_user_approval() -> None:
    bundle = hermes_rpg_command_bundle({"ticket_id": "t1", "command": "check inventory", "valid": True}, "t1")

    payload = hermes_rpg_intent_guard(bundle)

    assert payload["ok"] is True
    assert payload["command_text"] == "check inventory"
    assert payload["requires_user_approval"] is True
    assert payload["armed"] is False
    assert payload["state_changed"] is False
