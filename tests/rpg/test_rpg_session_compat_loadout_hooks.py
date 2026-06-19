from __future__ import annotations

from typing import Any

from app.platform import rpg_session_compat
from app.rpg.session import loadout_with_hooks


def test_loadout_action_compat_routes_through_hook_wrapper(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    def apply_loadout_action_with_item_hooks(session_id: str, request: Any, **options: Any) -> dict[str, Any]:
        seen["session_id"] = session_id
        seen["request"] = request
        seen["options"] = options
        state = {"mechanics": {"item_loadout_hook_traces": [{"event": "item_loadout_hooks_ran"}]}}
        session = {"manifest": {"session_id": session_id}, "state": state}
        return {
            "ok": True,
            "session_id": session_id,
            "status": "ready",
            "session": session,
            "game": state,
            "item_hook_result": {"skipped": False, "action": request.action},
        }

    monkeypatch.setattr(
        loadout_with_hooks,
        "apply_loadout_action_with_item_hooks",
        apply_loadout_action_with_item_hooks,
    )

    result = rpg_session_compat.get_rpg_session_payload(
        {
            "action": "loadout_action",
            "session_id": "rpg_test",
            "loadout": {"action": "use", "item_name": "Health Potion", "station": "tavern"},
            "diagnostics_interval": 1,
            "maintenance_interval": 2,
            "report_interval": 3,
            "objective_limit": 4,
            "record_trace": True,
            "record_hook_trace": False,
        }
    )

    assert result["ok"] is True
    assert result["item_hook_result"] == {"skipped": False, "action": "use"}
    assert seen["session_id"] == "rpg_test"
    assert seen["request"].action == "use"
    assert seen["request"].item_name == "Health Potion"
    assert seen["request"].station == "tavern"
    assert seen["options"] == {
        "diagnostics_interval": 1,
        "maintenance_interval": 2,
        "report_interval": 3,
        "objective_limit": 4,
        "record_trace": True,
        "record_hook_trace": False,
    }


def test_loadout_action_compat_uses_hook_defaults(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    def apply_loadout_action_with_item_hooks(session_id: str, request: Any, **options: Any) -> dict[str, Any]:
        seen["options"] = options
        return {
            "ok": False,
            "error": "item_not_found",
            "session_id": session_id,
            "item_name": request.item_name,
        }

    monkeypatch.setattr(
        loadout_with_hooks,
        "apply_loadout_action_with_item_hooks",
        apply_loadout_action_with_item_hooks,
    )

    result = rpg_session_compat.get_rpg_session_payload(
        {
            "action": "loadout_action",
            "session_id": "rpg_test",
            "loadout": {"action": "use", "item_name": "Missing Potion"},
        }
    )

    assert result == {
        "ok": False,
        "error": "item_not_found",
        "session_id": "rpg_test",
        "item_name": "Missing Potion",
    }
    assert seen["options"] == {
        "diagnostics_interval": 10,
        "maintenance_interval": 25,
        "report_interval": 20,
        "objective_limit": 5,
        "record_trace": True,
        "record_hook_trace": True,
    }


def test_loadout_action_compat_still_requires_session_id() -> None:
    result = rpg_session_compat.get_rpg_session_payload(
        {"action": "loadout_action", "loadout": {"action": "use", "item_name": "Health Potion"}}
    )

    assert result == {"ok": False, "error": "missing_session_id"}
