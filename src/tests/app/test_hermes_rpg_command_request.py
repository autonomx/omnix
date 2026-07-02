from __future__ import annotations

from app.assist_core.hermes_rpg_command_request import hermes_rpg_command_request


def test_hermes_rpg_command_request_requires_session_and_command() -> None:
    payload = hermes_rpg_command_request(
        {"ok": True, "command_text": "check inventory", "canonical_path": "rpg_command_input"},
        session_id="s1",
    )

    assert payload["ok"] is True
    assert payload["session_id"] == "s1"
    assert payload["command_text"] == "check inventory"
    assert payload["canonical_path"] == "rpg_command_input"
    assert payload["ready_for_rpg_pipeline"] is True
    assert payload["state_changed"] is False


def test_hermes_rpg_command_request_blocks_missing_session() -> None:
    payload = hermes_rpg_command_request({"ok": True, "command_text": "check inventory"}, session_id="")

    assert payload["ok"] is False
    assert payload["ready_for_rpg_pipeline"] is False
    assert payload["state_changed"] is False
