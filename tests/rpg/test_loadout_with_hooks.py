from __future__ import annotations

from typing import Any

from app.rpg.session import loadout, loadout_with_hooks


def _session() -> dict[str, Any]:
    return {
        "manifest": {"id": "rpg_test", "session_id": "rpg_test", "title": "Test", "updated_at": "before"},
        "state": {
            "session_id": "rpg_test",
            "current_turn": 0,
            "turn_count": 0,
            "world": {"time": "Day 1 • 08:00"},
            "summary": "Before",
            "player": {
                "name": "Test Hero",
                "resources": {
                    "hp": {"current": 50, "max": 100},
                    "stamina": {"current": 50, "max": 100},
                    "mana": {"current": 20, "max": 40},
                },
                "inventory": [
                    {"id": "health_potion", "name": "Health Potion", "quantity": 2, "type": "consumable"},
                    {"id": "simple_bow", "name": "Simple bow", "quantity": 1, "type": "weapon"},
                ],
                "equipment": [],
            },
            "timeline": [],
            "journal": {"entries": []},
        },
    }


def test_loadout_wrapper_runs_item_hooks_after_successful_item_action(monkeypatch) -> None:
    loadout_saves: list[dict[str, Any]] = []
    monkeypatch.setattr(loadout, "load_session", lambda session_id: _session())
    monkeypatch.setattr(loadout, "save_session", lambda session, *, compact=False: loadout_saves.append(session) or session)

    result = loadout_with_hooks.apply_loadout_action_with_item_hooks(
        "rpg_test",
        loadout.RpgLoadoutActionRequest(action="use", item_name="Health Potion"),
        diagnostics_interval=1,
        maintenance_interval=1,
        report_interval=1,
    )

    assert result["ok"] is True
    assert result["item_hook_result"]["skipped"] is False
    assert result["item_hook_result"]["action"] == "use"
    assert len(loadout_saves) == 1
    state = loadout_saves[0]["state"]
    assert state["player"]["resources"]["hp"] == {"current": 75, "max": 100}
    assert state["mechanics"]["item_loadout_hook_traces"][0]["event"] == "item_loadout_hooks_ran"
    assert state["mechanics"]["item_loadout_hook_traces"][0]["action"] == "use"
    assert "maintenance" in result["item_hook_result"]["executed_actions"]
    assert "report" in result["item_hook_result"]["executed_actions"]
    assert state["mechanics"]["item_traces"][0]["event"] in {
        "item_loadout_hooks_ran",
        "item_turn_hooks_ran",
    }


def test_loadout_wrapper_skips_successful_non_item_actions_without_second_save(monkeypatch) -> None:
    loadout_saves: list[dict[str, Any]] = []
    monkeypatch.setattr(loadout, "load_session", lambda session_id: _session())
    monkeypatch.setattr(loadout, "save_session", lambda session, *, compact=False: loadout_saves.append(session) or session)

    result = loadout_with_hooks.apply_loadout_action_with_item_hooks(
        "rpg_test",
        loadout.RpgLoadoutActionRequest(action="hotbar", hotbar_slot="2", target="the nearest foe"),
    )

    assert result["ok"] is True
    assert result["item_hook_result"]["skipped"] is True
    assert result["item_hook_result"]["action"] == "hotbar"
    assert len(loadout_saves) == 1


def test_loadout_wrapper_does_not_run_hooks_after_failed_item_action(monkeypatch) -> None:
    loadout_saves: list[dict[str, Any]] = []
    monkeypatch.setattr(loadout, "load_session", lambda session_id: _session())
    monkeypatch.setattr(loadout, "save_session", lambda session, *, compact=False: loadout_saves.append(session) or session)

    result = loadout_with_hooks.apply_loadout_action_with_item_hooks(
        "rpg_test",
        loadout.RpgLoadoutActionRequest(action="use", item_name="Missing Potion"),
    )

    assert result == {"ok": False, "error": "item_not_found", "session_id": "rpg_test", "item_name": "Missing Potion"}
    assert loadout_saves == []
