from __future__ import annotations

from app.rpg.session.item_turn_hooks import build_item_turn_hook_plan, run_item_turn_hooks


def _state() -> dict:
    return {
        "current_turn": 20,
        "player": {
            "resources": {"health": 10, "max_health": 12},
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
        "mechanics": {
            "item_traces": [{"event": f"old_{index}"} for index in range(3)],
        },
    }


def test_build_item_turn_hook_plan_marks_due_actions_without_mutation() -> None:
    state = _state()
    plan = build_item_turn_hook_plan(state, current_turn=20, diagnostics_interval=10, maintenance_interval=25, report_interval=20)

    assert plan["ok"] is True
    assert plan["turn"] == 20
    assert "recipe_discovery" in plan["enabled_actions"]
    assert "diagnostics" in plan["enabled_actions"]
    assert "report" in plan["enabled_actions"]
    assert "maintenance" not in plan["enabled_actions"]
    assert "objectives" in plan["enabled_actions"]
    assert plan["summary"]["should_report"] is True
    assert "item_turn_hook_traces" not in state["mechanics"]


def test_run_item_turn_hooks_records_due_traces_and_report() -> None:
    state = _state()
    result = run_item_turn_hooks(state, current_turn=20, diagnostics_interval=10, maintenance_interval=25, report_interval=20)

    assert result["ok"] is True
    assert result["turn"] == 20
    assert result["executed_actions"] == ["recipe_discovery", "diagnostics", "report", "objectives"]
    assert result["results"]["diagnostics"]["ok"] in {True, False}
    assert result["results"]["report"]["ok"] is True
    mechanics = state["mechanics"]
    assert mechanics["item_turn_hook_traces"][0]["event"] == "item_turn_hooks_ran"
    assert mechanics["item_turn_hook_traces"][0]["executed_actions"] == result["executed_actions"]
    assert mechanics["item_traces"][0]["event"] == "item_turn_hooks_ran"
    assert mechanics["item_report_sections"]


def test_run_item_turn_hooks_can_execute_maintenance_and_skip_trace_recording() -> None:
    state = _state()
    state["mechanics"]["item_traces"] = [{"event": f"trace_{index}"} for index in range(60)]

    result = run_item_turn_hooks(
        state,
        current_turn=25,
        diagnostics_interval=10,
        maintenance_interval=25,
        report_interval=20,
        record_trace=False,
    )

    assert result["recorded"] is False
    assert "maintenance" in result["executed_actions"]
    assert "diagnostics" not in result["executed_actions"]
    assert "report" not in result["executed_actions"]
    assert "item_turn_hook_traces" not in state["mechanics"]
    assert len(state["mechanics"]["item_traces"]) <= 50
    assert state["mechanics"]["item_state_maintenance_traces"][0]["event"] == "item_state_maintained"


def test_turn_zero_runs_diagnostics_but_not_report_or_maintenance() -> None:
    state = _state()
    result = run_item_turn_hooks(state, current_turn=0, diagnostics_interval=10, maintenance_interval=25, report_interval=20)

    assert result["turn"] == 0
    assert "diagnostics" in result["executed_actions"]
    assert "maintenance" not in result["executed_actions"]
    assert "report" not in result["executed_actions"]
