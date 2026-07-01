from __future__ import annotations

from app.assist_core.hermes_rpg_command_card import hermes_rpg_command_card


def test_hermes_rpg_command_card_fills_input_only() -> None:
    payload = hermes_rpg_command_card({"ok": True, "ticket_id": "t1", "command": "check inventory"})

    assert payload["ok"] is True
    assert payload["ticket_id"] == "t1"
    assert payload["command_text"] == "check inventory"
    assert payload["fills_input"] is True
    assert payload["submits"] is False
    assert payload["state_changed"] is False


def test_hermes_rpg_command_card_rejects_empty_command() -> None:
    payload = hermes_rpg_command_card({"ok": True, "ticket_id": "t1", "command": ""})

    assert payload["ok"] is False
    assert payload["fills_input"] is False
    assert payload["submits"] is False
    assert payload["state_changed"] is False
