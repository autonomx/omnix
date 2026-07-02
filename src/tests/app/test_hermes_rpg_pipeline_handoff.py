from __future__ import annotations

from app.assist_core.hermes_rpg_pipeline_handoff import hermes_rpg_pipeline_handoff


def test_hermes_rpg_pipeline_handoff_requires_ready_inputs() -> None:
    payload = hermes_rpg_pipeline_handoff(
        {"ready": True, "command_text": "check inventory"},
        {"ok": True, "command_text": "check inventory"},
    )

    assert payload["ok"] is True
    assert payload["command_text"] == "check inventory"
    assert payload["canonical_path"] == "rpg_command_input"
    assert payload["ready_for_rpg_pipeline"] is True
    assert payload["state_changed"] is False


def test_hermes_rpg_pipeline_handoff_rejects_not_ready_user_step() -> None:
    payload = hermes_rpg_pipeline_handoff(
        {"ready": False, "command_text": "check inventory"},
        {"ok": True, "command_text": "check inventory"},
    )

    assert payload["ok"] is False
    assert payload["ready_for_rpg_pipeline"] is False
    assert payload["state_changed"] is False
