from __future__ import annotations

from app.rpg.session.item_scenarios import build_item_scenario_plan, run_item_scenario


def _state() -> dict:
    return {
        "current_turn": 9,
        "player": {
            "inventory": [
                {
                    "item_id": "calm_focus",
                    "name": "Calm Focus",
                    "item_type": "relic",
                    "quantity": 1,
                    "item_signals": [
                        {"signal_id": "steady", "op": "restore_resource", "resource": "mana", "amount": 3, "consume": False}
                    ],
                },
                {
                    "item_id": "training_kit",
                    "name": "Training Kit",
                    "item_type": "weapon",
                    "quantity": 1,
                    "damage": {"amount": 2, "type": "blunt"},
                    "value": {"copper": 12},
                },
            ],
            "resources": {"mana": {"current": 2, "max": 8}},
        },
        "scene_state": {
            "item_nodes": [
                {
                    "id": "field_pack",
                    "name": "Field Pack",
                    "remaining": 1,
                    "outputs": [{"item_id": "travel_ration", "name": "Travel ration", "quantity": 1, "stackable": True}],
                }
            ]
        },
        "mechanics": {},
    }


def test_build_item_scenario_plan_marks_executable_and_blocked_steps() -> None:
    plan = build_item_scenario_plan(_state(), limit=6)

    assert plan["summary"]["step_count"] >= 3
    assert plan["summary"]["executable_count"] >= 2
    assert any(step["action"]["action"] == "effect" and step["executable"] is True for step in plan["steps"])
    assert any(step["action"]["action"] == "pickup" and step["executable"] is True for step in plan["steps"])
    assert any(step["action"]["action"] == "equip" and step["blocked_reason"] == "requires_loadout_or_route" for step in plan["steps"])
    assert plan["trace"]["mechanics_source"] == "engine_item_scenarios_v1"


def test_run_item_scenario_executes_dispatcher_steps_and_records_trace() -> None:
    state = _state()
    steps = [
        {
            "step_id": "effect:calm_focus",
            "label": "Apply focus",
            "action": {"action": "effect", "item_id": "calm_focus", "effect_id": "steady"},
            "executable": True,
        },
        {
            "step_id": "pickup:field_pack",
            "label": "Collect field pack",
            "action": {"action": "pickup", "node_id": "field_pack"},
            "executable": True,
        },
        {
            "step_id": "report:item",
            "label": "Record item report",
            "action": {"action": "report", "record": True},
            "executable": True,
        },
        {
            "step_id": "craft:torch",
            "label": "Craft torch",
            "action": {"action": "craft", "recipe_id": "torch"},
            "executable": False,
            "blocked_reason": "requires_loadout_or_route",
        },
    ]

    result = run_item_scenario(state, steps=steps, source="unit")

    assert result["ok"] is True
    assert result["summary"] == {"attempted_count": 3, "ok_count": 3, "failed_count": 0, "skipped_count": 1}
    assert result["skipped"] == [{"step_id": "craft:torch", "action": "craft", "reason": "requires_loadout_or_route"}]
    assert state["player"]["resources"]["mana"]["current"] == 5
    assert any(item.get("item_id") == "travel_ration" for item in state["player"]["inventory"])
    assert state["scene_state"]["item_nodes"][0]["remaining"] == 0
    assert state["mechanics"]["item_scenario_traces"][0]["ok_count"] == 3
    assert state["mechanics"]["item_traces"][0]["mechanics_source"] == "engine_item_scenarios_v1"
    assert any(trace.get("mechanics_source") == "engine_item_pickup_session_v1" for trace in state["mechanics"]["item_traces"])
