from __future__ import annotations

from app.assist_core.hermes_rpg_request_guard import hermes_rpg_request_guard


def test_hermes_rpg_request_guard_accepts_matching_context() -> None:
    payload = hermes_rpg_request_guard(
        {"ok": True, "session_id": "s1", "context_hash": "abc", "command_text": "check inventory"},
        {"session_id": "s1", "context_hash": "abc"},
    )

    assert payload["ok"] is True
    assert payload["session_ok"] is True
    assert payload["context_ok"] is True
    assert payload["command_text"] == "check inventory"
    assert payload["state_changed"] is False


def test_hermes_rpg_request_guard_rejects_context_mismatch() -> None:
    payload = hermes_rpg_request_guard(
        {"ok": True, "session_id": "s1", "context_hash": "abc"},
        {"session_id": "s1", "context_hash": "def"},
    )

    assert payload["ok"] is False
    assert payload["context_ok"] is False
    assert payload["state_changed"] is False
