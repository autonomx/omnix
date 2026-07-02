from __future__ import annotations

from app.assist_core.hermes_rpg_audit_entry import hermes_rpg_audit_entry
from app.assist_core.hermes_rpg_command_bundle import hermes_rpg_command_bundle
from app.assist_core.hermes_rpg_intent_guard import hermes_rpg_intent_guard
from app.assist_core.hermes_rpg_user_step import hermes_rpg_user_step


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


def test_hermes_rpg_user_step_requires_confirmation() -> None:
    intent = hermes_rpg_intent_guard(
        hermes_rpg_command_bundle({"ticket_id": "t1", "command": "check inventory", "valid": True}, "t1")
    )

    blocked = hermes_rpg_user_step(intent, confirmed=False)
    ready = hermes_rpg_user_step(intent, confirmed=True)

    assert blocked["ready"] is False
    assert ready["ready"] is True
    assert ready["command_text"] == "check inventory"
    assert ready["state_changed"] is False


def test_hermes_rpg_audit_entry_records_command_metadata() -> None:
    payload = hermes_rpg_audit_entry(
        {"ticket_id": "t1", "context_hash": "abc", "command_text": "check inventory", "confirmed": True}
    )

    assert payload["ok"] is True
    assert payload["ticket_id"] == "t1"
    assert payload["context_hash"] == "abc"
    assert payload["command_text"] == "check inventory"
    assert payload["confirmed"] is True
    assert payload["state_changed"] is False
