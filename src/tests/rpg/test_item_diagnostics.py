from __future__ import annotations

from copy import deepcopy

from app.rpg.session.item_diagnostics import build_item_diagnostics, record_item_diagnostics


def _state() -> dict:
    return {
        "current_turn": 7,
        "player": {
            "currency": {"gold": 1, "silver": 2, "copper": 3},
            "inventory": [
                {
                    "id": "field-pack-1",
                    "item_id": "field_pack",
                    "name": "Field Pack",
                    "display_name": "Field Pack",
                    "type": "gear",
                    "quantity": 1,
                    "stackable": False,
                    "item_effects": [
                        {
                            "effect_id": "calm_focus",
                            "name": "Calm Focus",
                            "effects": [{"type": "resource_delta", "resource": "focus", "amount": 1}],
                        }
                    ],
                },
                {
                    "id": "iron-scrap",
                    "item_id": "iron_scrap",
                    "name": "Iron scrap",
                    "display_name": "Iron scrap",
                    "type": "material",
                    "material_id": "iron_fragment",
                    "quantity": 3,
                    "stackable": True,
                },
            ],
        },
        "scene": {
            "item_nodes": [
                {
                    "node_id": "cache-1",
                    "name": "Small Cache",
                    "outputs": [
                        {"item_id": "rations", "name": "Rations", "type": "consumable", "quantity": 1, "stackable": True}
                    ],
                    "depleted": False,
                }
            ]
        },
        "crafting": {"known_recipes": ["field_torch"]},
        "mechanics": {
            "item_use_traces": [{"event": "item_used"}],
            "crafting_traces": [{"event": "item_crafted"}],
            "item_traces": [{"event": "existing"}],
        },
    }


def test_build_item_diagnostics_combines_report_scenario_and_objectives_without_mutation() -> None:
    state = _state()
    before = deepcopy(state)

    diagnostics = build_item_diagnostics(state, station="campfire", scenario_limit=5, objective_limit=4)

    assert state == before
    assert diagnostics["mechanics_source"] == "engine_item_diagnostics_v1"
    assert diagnostics["summary"]["coverage_score"] is not None
    assert diagnostics["summary"]["scenario_step_count"] >= diagnostics["summary"]["scenario_executable_count"]
    assert diagnostics["summary"]["objective_count"] == len(diagnostics["objectives"]["objectives"])
    assert diagnostics["report"]["title"] == "Item System Coverage"
    assert diagnostics["maintenance"]["actions"][0] == "audit"
    assert diagnostics["top_objectives"]
    assert "coverage_missing" in diagnostics["gaps"]


def test_record_item_diagnostics_adds_compact_trace_only() -> None:
    state = _state()

    result = record_item_diagnostics(state, station="campfire", scenario_limit=3, objective_limit=3)

    trace = result["mechanics_trace"]
    assert trace["event"] == "item_diagnostics_built"
    assert trace["mechanics_source"] == "engine_item_diagnostics_v1"
    assert trace["turn"] == 7
    assert state["mechanics"]["item_diagnostic_traces"][0] == trace
    assert state["mechanics"]["item_traces"][0] == trace
    assert state["mechanics"]["item_traces"][1]["event"] == "existing"


def test_build_item_diagnostics_surfaces_audit_issues_and_attention() -> None:
    state = _state()
    state["player"]["inventory"].append(
        {
            "id": "bad-stack",
            "item_id": "oddity",
            "name": "Oddity",
            "type": "misc",
            "quantity": -2,
            "stackable": True,
        }
    )

    diagnostics = build_item_diagnostics(state)

    assert diagnostics["ok"] is False
    assert diagnostics["summary"]["needs_attention"] is True
    assert diagnostics["summary"]["audit_issue_count"] >= 1
    assert diagnostics["gaps"]["audit_issues"]
