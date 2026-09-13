from __future__ import annotations

from app.rpg.session.item_loadout_hooks import build_loadout_item_hook_plan, run_loadout_item_hooks


def _state() -> dict:
    return {
        "current_turn": 20,
        "player": {
            "resources": {"health": {"current": 10, "max": 12}},
            "inventory": [
                {
                    "id": "map_01",
                    "item_id": "forgotten_map",
                    "name": "Forgotten Map",
                    "type": "knowledge",
                    "quantity": 1,
                    "effects": [
                        {
                            "id": "map_focus",
                            "kind": "add_affordance",
                            "affordance": "travel:old_road",
                        }
                    ],
                    "tags": ["knowledge"],
                },
                {
                    "id": "scrap_01",
                    "item_id": "iron_scrap",
                    "name": "Iron scrap",
                    "type": "material",
                    "quantity": 2,
                    "stackable": True,
                    "material_id": "iron",
                    "material_role": "metal",
                    "properties": ["metal"],
                },
            ],
        },
        "mechanics": {"item_traces": [{"event": "existing"}]},
    }


def test_build_loadout_item_hook_plan_marks_item_actions_without_mutation() -> None:
    state = _state()
    plan = build_loadout_item_hook_plan(
        state,
        action="craft",
        current_turn=20,
        diagnostics_interval=10,
        maintenance_interval=25,
        report_interval=20,
    )

    assert plan["ok"] is True
    assert plan["should_run"] is True
    assert plan["reason"] == "item_loadout_action"
    assert "recipe_discovery" in plan["enabled_actions"]
    assert "diagnostics" in plan["enabled_actions"]
    assert "report" in plan["enabled_actions"]
    assert state["mechanics"] == {"item_traces": [{"event": "existing"}]}


def test_run_loadout_item_hooks_records_bridge_and_underlying_hook_traces() -> None:
    state = _state()
    result = run_loadout_item_hooks(
        state,
        action="salvage",
        current_turn=20,
        diagnostics_interval=10,
        maintenance_interval=25,
        report_interval=20,
    )

    assert result["ok"] is True
    assert result["skipped"] is False
    assert result["executed_actions"] == ["recipe_discovery", "diagnostics", "report", "objectives"]
    assert result["mechanics_trace"]["event"] == "item_loadout_hooks_ran"
    mechanics = state["mechanics"]
    assert mechanics["item_loadout_hook_traces"][0]["event"] == "item_loadout_hooks_ran"
    assert mechanics["item_turn_hook_traces"][0]["event"] == "item_turn_hooks_ran"
    assert mechanics["item_traces"][0]["event"] == "item_loadout_hooks_ran"
    assert mechanics["item_report_sections"]


def test_run_loadout_item_hooks_skips_non_item_actions_without_trace_noise() -> None:
    state = _state()
    result = run_loadout_item_hooks(state, action="unlock_ability", current_turn=20)

    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["reason"] == "non_item_loadout_action"
    assert "item_loadout_hook_traces" not in state["mechanics"]
    assert state["mechanics"]["item_traces"] == [{"event": "existing"}]


def test_run_loadout_item_hooks_can_silence_bridge_trace_but_keep_hook_result() -> None:
    state = _state()
    result = run_loadout_item_hooks(
        state,
        action="use",
        current_turn=20,
        diagnostics_interval=10,
        report_interval=20,
        record_trace=False,
        record_hook_trace=True,
    )

    assert result["recorded"] is False
    assert "item_loadout_hook_traces" not in state["mechanics"]
    assert state["mechanics"]["item_turn_hook_traces"][0]["event"] == "item_turn_hooks_ran"
    assert state["mechanics"]["item_traces"][0]["event"] == "item_turn_hooks_ran"


def test_run_loadout_item_hooks_skips_duplicate_action_turn_trace() -> None:
    state = _state()
    first = run_loadout_item_hooks(state, action="use", current_turn=20)
    second = run_loadout_item_hooks(state, action="use", current_turn=20)

    assert first["skipped"] is False
    assert second["skipped"] is True
    assert second["reason"] == "already_ran"
    assert len(state["mechanics"]["item_loadout_hook_traces"]) == 1
