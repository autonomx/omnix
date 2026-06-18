from __future__ import annotations

from typing import Any

from app.platform import rpg_session_compat
from app.rpg.session import item_command_adapter, service


def _session() -> dict[str, Any]:
    return {
        "manifest": {"session_id": "rpg_test", "title": "Test"},
        "state": {
            "session_id": "rpg_test",
            "player": {"inventory": []},
            "mechanics": {},
        },
    }


def test_item_command_compat_routes_command_and_saves_session(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    seen: list[tuple[dict[str, Any], Any]] = []

    def apply_item_command(state: dict[str, Any], command: Any) -> dict[str, Any]:
        seen.append((state, command))
        state.setdefault("mechanics", {})["item_command_traces"] = [{"event": "item_command_applied"}]
        return {
            "ok": True,
            "session_action": "report",
            "command": command,
            "normalized_action": {"action": "report"},
        }

    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(service, "save_session", lambda session, *, compact=False: saved.append(session) or session)
    monkeypatch.setattr(item_command_adapter, "apply_item_command", apply_item_command)

    result = rpg_session_compat.get_rpg_session_payload(
        {"action": "item_command", "session_id": "rpg_test", "command": "item report"}
    )

    assert result["ok"] is True
    assert result["session_id"] == "rpg_test"
    assert result["status"] == "ready"
    assert result["session_action"] == "report"
    assert result["normalized_action"] == {"action": "report"}
    assert result["game"] is saved[0]["state"]
    assert seen == [(saved[0]["state"], "item report")]
    assert saved[0]["state"]["mechanics"]["item_command_traces"] == [{"event": "item_command_applied"}]


def test_item_command_compat_requires_session_id() -> None:
    result = rpg_session_compat.get_rpg_session_payload({"action": "item_command", "command": "item report"})

    assert result == {"ok": False, "error": "missing_session_id"}


def test_item_command_compat_rejects_missing_session(monkeypatch) -> None:
    monkeypatch.setattr(service, "load_session", lambda session_id: None)

    result = rpg_session_compat.get_rpg_session_payload(
        {"action": "item_command", "session_id": "missing", "command": "item report"}
    )

    assert result == {"ok": False, "error": "session_not_found", "session_id": "missing"}


def test_item_command_compat_does_not_save_failed_command(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []

    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(service, "save_session", lambda session, *, compact=False: saved.append(session) or session)
    monkeypatch.setattr(
        item_command_adapter,
        "apply_item_command",
        lambda state, command: {"ok": False, "error": "unsupported_item_command", "command": command},
    )

    result = rpg_session_compat.get_rpg_session_payload(
        {"action": "item_command", "session_id": "rpg_test", "command": "dance"}
    )

    assert result == {"session_id": "rpg_test", "ok": False, "error": "unsupported_item_command", "command": "dance"}
    assert saved == []
