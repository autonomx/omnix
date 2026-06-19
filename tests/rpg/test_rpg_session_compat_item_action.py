from __future__ import annotations

from typing import Any

from app.platform import rpg_session_compat
from app.rpg.session import item_session_actions, service


def _session() -> dict[str, Any]:
    return {
        "manifest": {"session_id": "rpg_test", "title": "Test"},
        "state": {
            "session_id": "rpg_test",
            "player": {"inventory": []},
            "mechanics": {},
        },
    }


def test_item_action_compat_routes_nested_action_and_saves_session(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    seen: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def apply_item_session_action(
        state: dict[str, Any],
        action: dict[str, Any],
    ) -> dict[str, Any]:
        seen.append((state, action))
        state.setdefault("mechanics", {})["item_traces"] = [{"event": "item_action_applied"}]
        return {
            "ok": True,
            "session_action": "pickup",
            "picked_up": ["Field Pack"],
        }

    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(service, "save_session", lambda session, *, compact=False: saved.append(session) or session)
    monkeypatch.setattr(item_session_actions, "apply_item_session_action", apply_item_session_action)

    result = rpg_session_compat.get_rpg_session_payload(
        {
            "action": "item_action",
            "session_id": "rpg_test",
            "item_action": {"action": "pickup", "node_id": "field_pack_node"},
        }
    )

    assert result["ok"] is True
    assert result["session_id"] == "rpg_test"
    assert result["status"] == "ready"
    assert result["session_action"] == "pickup"
    assert result["picked_up"] == ["Field Pack"]
    assert result["game"] is saved[0]["state"]
    assert seen == [(saved[0]["state"], {"action": "pickup", "node_id": "field_pack_node"})]
    assert saved[0]["state"]["mechanics"]["item_traces"] == [{"event": "item_action_applied"}]


def test_item_action_compat_routes_flat_action_alias(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    seen: list[dict[str, Any]] = []

    def apply_item_session_action(
        state: dict[str, Any],
        action: dict[str, Any],
    ) -> dict[str, Any]:
        seen.append(action)
        return {"ok": True, "session_action": "effect", "used": action.get("item_name")}

    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(service, "save_session", lambda session, *, compact=False: saved.append(session) or session)
    monkeypatch.setattr(item_session_actions, "apply_item_session_action", apply_item_session_action)

    result = rpg_session_compat.get_rpg_session_payload(
        {
            "action": "item_action",
            "session_id": "rpg_test",
            "item_action_kind": "effect",
            "item_name": "Calm Focus",
            "source": "compat_test",
        }
    )

    assert result["ok"] is True
    assert result["session_action"] == "effect"
    assert result["used"] == "Calm Focus"
    assert seen == [
        {
            "item_action_kind": "effect",
            "item_name": "Calm Focus",
            "source": "compat_test",
            "action": "effect",
        }
    ]
    assert len(saved) == 1


def test_item_action_compat_requires_session_id() -> None:
    result = rpg_session_compat.get_rpg_session_payload(
        {"action": "item_action", "item_action": {"action": "report"}}
    )

    assert result == {"ok": False, "error": "missing_session_id"}


def test_item_action_compat_rejects_missing_session(monkeypatch) -> None:
    monkeypatch.setattr(service, "load_session", lambda session_id: None)

    result = rpg_session_compat.get_rpg_session_payload(
        {"action": "item_action", "session_id": "missing", "item_action": {"action": "report"}}
    )

    assert result == {"ok": False, "error": "session_not_found", "session_id": "missing"}


def test_item_action_compat_does_not_save_failed_action(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []

    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(service, "save_session", lambda session, *, compact=False: saved.append(session) or session)
    monkeypatch.setattr(
        item_session_actions,
        "apply_item_session_action",
        lambda state, action: {
            "ok": False,
            "error": "unsupported_item_session_action",
            "action": action.get("action"),
        },
    )

    result = rpg_session_compat.get_rpg_session_payload(
        {"action": "item_action", "session_id": "rpg_test", "item_action": {"action": "dance"}}
    )

    assert result == {
        "session_id": "rpg_test",
        "ok": False,
        "error": "unsupported_item_session_action",
        "action": "dance",
    }
    assert saved == []
