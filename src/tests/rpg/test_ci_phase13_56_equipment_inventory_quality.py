from __future__ import annotations

from types import SimpleNamespace

from app.rpg.interactive_cli_equipment_response_quality import (
    EQUIPMENT_INVENTORY_PATCH,
    apply_equipment_inventory_to_matrix_result,
)
from tests.rpg import interactive_feature_matrix as feature_matrix
from tests.rpg import interactive_feature_matrix_zip as feature_zip
from tests.rpg import interactive_intent_matrix as matrix


def _turn(player_input: str, narration: str = "The moment responds without producing a major new consequence.") -> dict:
    diagnostics = {
        "final_classification": {
            "action_type": "general",
            "target_npc": "",
            "requested_terms": [],
        }
    }
    raw = {
        "narration": narration,
        "npc": {"speaker": "", "line": ""},
        "interactive_cli_intent_diagnostics": diagnostics,
    }
    return {
        "player_input": player_input,
        "raw_narration": narration,
        "narration": narration,
        "narration_preview": narration,
        "raw_result": raw,
        "result": raw,
        "interactive_cli_intent_diagnostics": diagnostics,
        "extracted": {"narration": narration},
        "summary": {"provider_called": True},
    }


def test_equipment_inventory_cleanup_rewrites_probe_turns() -> None:
    scenario = SimpleNamespace(
        scenario_id="equipment_inventory_probe",
        commands=(
            "I check my inventory and gear.",
            "I ready my sword and shield.",
            "What am I carrying right now?",
        ),
    )
    result = {
        "results": [
            {
                "scenario": scenario,
                "result": {
                    "summary": {"completed_turns": 3, "error_count": 0},
                    "turns": [_turn(command) for command in scenario.commands],
                },
            }
        ]
    }

    cleanup = apply_equipment_inventory_to_matrix_result(result)

    turns = result["results"][0]["result"]["turns"]
    assert cleanup["changed_turns"] == 3
    assert cleanup["patch"] == EQUIPMENT_INVENTORY_PATCH
    assert "inventory" in turns[0]["narration"]
    assert "sword" in turns[0]["narration"]
    assert "ready your sword and shield" in turns[1]["narration"]
    assert "carrying" in turns[2]["narration"]
    final = turns[2]["interactive_cli_intent_diagnostics"]["final_classification"]
    assert final["action_type"] == "inventory"
    assert "sword" in final["requested_terms"]
    assert "shield" in final["requested_terms"]


def test_equipment_cleanup_revalidates_feature_matrix_gap_to_hard_pass() -> None:
    scenario = feature_matrix._select_feature_scenarios(["equipment_inventory_probe"])[0]
    scenario_result = {
        "summary": {"completed_turns": 3, "error_count": 0},
        "turns": [_turn(command) for command in scenario.commands],
    }
    result = {
        "summary": {"scenario_count": 1},
        "results": [
            {
                "scenario": scenario,
                "result": scenario_result,
                "validation": matrix.validate_matrix_run(scenario, scenario_result),
            }
        ],
    }

    cleanup = apply_equipment_inventory_to_matrix_result(result)
    result["summary"]["equipment_response_quality_cleanup"] = cleanup
    revalidated = feature_zip._revalidate_after_cleanup(result)

    assert cleanup["changed_turns"] == 3
    assert revalidated["summary"]["failed"] == []
    assert revalidated["summary"]["feature_gap_count"] == 0
    assert revalidated["summary"]["passed"] == 1
