from __future__ import annotations

from typing import Any, Mapping

from app.rpg.interactive_cli_commerce_response_quality import apply_commerce_sell_state_to_matrix_result
from app.rpg.interactive_cli_equipment_response_quality import apply_equipment_inventory_to_matrix_result
from app.rpg.interactive_cli_memory_response_quality import apply_short_session_memory_recall_to_matrix_result
from app.rpg.interactive_cli_response_quality import apply_response_quality_to_matrix_result
from app.rpg.interactive_cli_travel_response_quality import apply_travel_state_to_matrix_result
from tests.rpg import interactive_feature_matrix as feature_matrix
from tests.rpg.interactive_feature_matrix_zip import _revalidate_after_cleanup


_STATE_SCENARIOS = {
    "shop_sell_attempt",
    "travel_round_trip_route",
    "npc_memory_recall_probe",
    "equipment_inventory_probe",
}


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _generic_turn(command: str, turn_index: int) -> dict[str, Any]:
    narration = "The moment responds without producing a major new consequence."
    diagnostics = {
        "provider_called": True,
        "final_classification": {
            "action_type": "observe",
            "service_kind": "unknown",
            "target_npc": "",
            "requested_terms": [],
        },
    }
    raw_result = {
        "narration": narration,
        "npc": {"speaker": "", "line": ""},
        "interactive_cli_intent_diagnostics": diagnostics,
    }
    return {
        "turn_index": turn_index,
        "player_input": command,
        "player_action": command,
        "raw_narration": narration,
        "narration": narration,
        "narration_preview": narration,
        "raw_npc": {"speaker": "", "line": ""},
        "npc": {"speaker": "", "line": ""},
        "raw_result": raw_result,
        "result": raw_result,
        "interactive_cli_intent_diagnostics": diagnostics,
    }


def _state_scenario_result(scenario: Any) -> dict[str, Any]:
    turns = [_generic_turn(command, index + 1) for index, command in enumerate(scenario.commands)]
    return {
        "turns": turns,
        "summary": {
            "completed_turns": len(scenario.commands),
            "error_count": 0,
        },
    }


def _state_matrix_result() -> dict[str, Any]:
    scenarios = [
        scenario
        for scenario in feature_matrix.default_feature_matrix_scenarios()
        if scenario.scenario_id in _STATE_SCENARIOS
    ]
    return {
        "results": [
            {
                "scenario": scenario,
                "result": _state_scenario_result(scenario),
                "validation": {"ok": False, "scenario_id": scenario.scenario_id, "failures": ["synthetic pre-cleanup failure"]},
            }
            for scenario in scenarios
        ],
        "summary": {
            "scenario_count": len(scenarios),
            "failed": [],
            "feature_gaps": [],
            "feature_gap_count": 0,
            "known_feature_gap_scenarios": sorted(feature_matrix.KNOWN_FEATURE_GAP_SCENARIO_IDS),
        },
    }


def _apply_all_feature_state_cleanups(result: Mapping[str, Any]) -> dict[str, Any]:
    matrix_result = dict(result)
    response_cleanup = apply_response_quality_to_matrix_result(matrix_result)
    commerce_cleanup = apply_commerce_sell_state_to_matrix_result(matrix_result)
    travel_cleanup = apply_travel_state_to_matrix_result(matrix_result)
    memory_cleanup = apply_short_session_memory_recall_to_matrix_result(matrix_result)
    equipment_cleanup = apply_equipment_inventory_to_matrix_result(matrix_result)
    matrix_result["summary"]["response_quality_cleanup"] = response_cleanup
    matrix_result["summary"]["commerce_response_quality_cleanup"] = commerce_cleanup
    matrix_result["summary"]["travel_state_cleanup"] = travel_cleanup
    matrix_result["summary"]["memory_response_quality_cleanup"] = memory_cleanup
    matrix_result["summary"]["equipment_response_quality_cleanup"] = equipment_cleanup
    _revalidate_after_cleanup(matrix_result)
    matrix_result["summary"]["response_quality_cleanup"] = response_cleanup
    matrix_result["summary"]["commerce_response_quality_cleanup"] = commerce_cleanup
    matrix_result["summary"]["travel_state_cleanup"] = travel_cleanup
    matrix_result["summary"]["memory_response_quality_cleanup"] = memory_cleanup
    matrix_result["summary"]["equipment_response_quality_cleanup"] = equipment_cleanup
    return matrix_result


def _result_for(cleaned_result: Mapping[str, Any], scenario_id: str) -> dict[str, Any]:
    for item in cleaned_result.get("results") or []:
        scenario = item.get("scenario")
        if getattr(scenario, "scenario_id", "") == scenario_id:
            return _safe_dict(item.get("result"))
    raise AssertionError(f"missing scenario result: {scenario_id}")


def test_phase13_62_feature_state_layers_revalidate_together() -> None:
    result = _state_matrix_result()

    cleaned = _apply_all_feature_state_cleanups(result)

    summary = _safe_dict(cleaned.get("summary"))
    assert summary["known_feature_gap_scenarios"] == []
    assert summary["feature_gap_count"] == 0
    assert summary["failed"] == []
    assert summary["passed"] == len(_STATE_SCENARIOS)
    assert summary["commerce_response_quality_cleanup"]["changed_turns"] == 3
    assert summary["travel_state_cleanup"]["changed_turns"] == 4
    assert summary["memory_response_quality_cleanup"]["changed_turns"] == 2
    assert summary["equipment_response_quality_cleanup"]["changed_turns"] == 3

    for item in cleaned.get("results") or []:
        assert item["validation"]["ok"] is True, item["validation"].get("failures")

    commerce_turns = _result_for(cleaned, "shop_sell_attempt")["turns"]
    assert commerce_turns[-1]["interactive_cli_commerce_state"]["inventory_mutated"] is False
    assert commerce_turns[-1]["interactive_cli_commerce_state"]["currency_delta_copper"] == 0
    assert len(commerce_turns[-1]["interactive_cli_commerce_state"]["attempted_sells"]) == 3

    travel_turns = _result_for(cleaned, "travel_round_trip_route")["turns"]
    assert [turn["interactive_cli_travel_state"]["current_location_id"] for turn in travel_turns] == [
        "location:road-north",
        "location:old-mill",
        "location:old-mill",
        "location:tavern",
    ]
    assert travel_turns[-1]["interactive_cli_travel_state"]["campaign_map_state"]["seed_scope"] == "local_region_seed"

    memory_turns = _result_for(cleaned, "npc_memory_recall_probe")["turns"]
    assert memory_turns[-1]["interactive_cli_memory_state"]["facts"]["trail_name"] == "Ash Lantern"
    assert memory_turns[-1]["interactive_cli_memory_state"]["remembered_by"]["trail_name"] == "Bran"

    equipment_turns = _result_for(cleaned, "equipment_inventory_probe")["turns"]
    assert equipment_turns[-1]["interactive_cli_equipment_state"]["readied_items"] == ["sword", "shield"]
