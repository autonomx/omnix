from __future__ import annotations

from types import SimpleNamespace

from app.rpg.interactive_cli_equipment_response_quality import (
    EQUIPMENT_INVENTORY_PATCH,
    apply_equipment_inventory_to_matrix_result,
)
from app.rpg.interactive_cli_equipment_state import (
    EQUIPMENT_STATE_VERSION,
    apply_ready_command,
    default_equipment_state,
    describe_inventory,
    normalize_equipment_state,
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


def test_equipment_state_helper_tracks_readied_items() -> None:
    state = default_equipment_state()

    assert state["version"] == EQUIPMENT_STATE_VERSION
    assert state["carried_items"] == ["sword", "shield", "ration", "waterskin"]
    assert state["readied_items"] == []
    assert "Nothing is readied yet" in describe_inventory(state)

    readied = apply_ready_command(state)

    assert normalize_equipment_state(readied)["readied_items"] == ["sword", "shield"]
    assert "Readied gear: sword, shield" in describe_inventory(readied)


def test_equipment_inventory_cleanup_rewrites_probe_turns_with_state() -> None:
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
    assert "sword" in turns[0]["narration"]
    assert "Nothing is readied yet" in turns[0]["narration"]
    assert "ready your sword and shield" in turns[1]["narration"]
    assert "Readied gear: sword, shield" in turns[2]["narration"]
    assert turns[2]["interactive_cli_equipment_state"]["readied_items"] == ["sword", "shield"]
    assert turns[2]["interactive_cli_equipment_state"]["carried_items"] == ["sword", "shield", "ration", "waterskin"]
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
