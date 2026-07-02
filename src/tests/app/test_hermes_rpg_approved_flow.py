from __future__ import annotations

from typing import Any

from app.assist_core.hermes_rpg_approved_flow import hermes_rpg_approved_flow


def test_hermes_rpg_approved_flow_submits_ready_command() -> None:
    seen: list[dict[str, Any]] = []

    def submitter(payload: dict[str, Any]) -> dict[str, Any]:
        seen.append(payload)
        return {"ok": True, "turn_id": 11}

    payload = hermes_rpg_approved_flow(
        {"ready": True, "command_text": "check inventory"},
        {"ok": True, "command_text": "check inventory"},
        {"session_id": "s1", "context_hash": "abc"},
        submitter,
    )

    assert seen == [{"session_id": "s1", "command_text": "check inventory"}]
    assert payload["ok"] is True
    assert payload["packet"]["ready_for_rpg_pipeline"] is True
    assert payload["result"]["rpg_result"] == {"ok": True, "turn_id": 11}
    assert payload["state_changed"] is True


def test_hermes_rpg_approved_flow_blocks_unready_user_step() -> None:
    def submitter(payload: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("submitter should not be called")

    payload = hermes_rpg_approved_flow(
        {"ready": False, "command_text": "check inventory"},
        {"ok": True, "command_text": "check inventory"},
        {"session_id": "s1", "context_hash": "abc"},
        submitter,
    )

    assert payload["ok"] is False
    assert payload["packet"]["ready_for_rpg_pipeline"] is False
    assert payload["state_changed"] is False
