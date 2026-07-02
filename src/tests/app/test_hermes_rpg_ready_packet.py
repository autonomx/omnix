from __future__ import annotations

from app.assist_core.hermes_rpg_ready_packet import hermes_rpg_ready_packet


def test_hermes_rpg_ready_packet_requires_request_and_guard() -> None:
    payload = hermes_rpg_ready_packet(
        {"ok": True, "session_id": "s1", "command_text": "check inventory"},
        {"ok": True, "context_hash": "abc", "command_text": "check inventory"},
    )

    assert payload["ok"] is True
    assert payload["session_id"] == "s1"
    assert payload["context_hash"] == "abc"
    assert payload["command_text"] == "check inventory"
    assert payload["ready_for_rpg_pipeline"] is True
    assert payload["state_changed"] is False


def test_hermes_rpg_ready_packet_blocks_failed_guard() -> None:
    payload = hermes_rpg_ready_packet(
        {"ok": True, "session_id": "s1", "command_text": "check inventory"},
        {"ok": False, "context_hash": "abc"},
    )

    assert payload["ok"] is False
    assert payload["ready_for_rpg_pipeline"] is False
    assert payload["state_changed"] is False
