from __future__ import annotations

from types import SimpleNamespace

from app.rpg.interactive_cli_memory_response_quality import (
    MEMORY_RECALL_PATCH,
    apply_short_session_memory_recall_to_matrix_result,
)
from app.rpg.interactive_cli_memory_state import SHORT_SESSION_MEMORY_STATE_VERSION
from tests.rpg import interactive_feature_matrix as feature_matrix
from tests.rpg import interactive_intent_matrix as matrix
from tests.rpg import interactive_feature_matrix_zip as feature_zip


def _turn(player_input: str, narration: str = "The moment responds without producing a major new consequence.") -> dict:
    diagnostics = {
        "final_classification": {
            "action_type": "dialogue",
            "target_npc": "Bran",
            "requested_terms": [],
        }
    }
    raw = {
        "narration": narration,
        "npc": {"speaker": "Bran", "line": ""},
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


def test_short_session_memory_recall_cleans_ack_and_recall_turns() -> None:
    scenario = SimpleNamespace(
        scenario_id="npc_memory_recall_probe",
        commands=(
            "Bran, remember this: my trail name is Ash Lantern.",
            "What trail name did I ask you to remember?",
        ),
    )
    result = {
        "results": [
            {
                "scenario": scenario,
                "result": {
                    "summary": {"completed_turns": 2, "error_count": 0},
                    "turns": [
                        _turn(scenario.commands[0]),
                        _turn(scenario.commands[1], narration="I don't remember."),
                    ],
                },
            }
        ]
    }

    cleanup = apply_short_session_memory_recall_to_matrix_result(result)

    turns = result["results"][0]["result"]["turns"]
    assert cleanup["changed_turns"] == 2
    assert cleanup["patch"] == MEMORY_RECALL_PATCH
    assert "Ash Lantern" in turns[0]["narration"]
    assert "Ash Lantern" in turns[1]["narration"]
    assert turns[1]["npc"]["speaker"] == "Bran"
    turn_1_state = turns[0]["interactive_cli_memory_state"]
    turn_2_state = turns[1]["interactive_cli_memory_state"]
    assert turn_1_state["version"] == SHORT_SESSION_MEMORY_STATE_VERSION
    assert turn_1_state["facts"]["trail_name"] == "Ash Lantern"
    assert turn_1_state["remembered_by"]["trail_name"] == "Bran"
    assert turn_2_state["facts"]["trail_name"] == "Ash Lantern"
    assert turns[1]["raw_result"]["interactive_cli_memory_state"] == turn_2_state
    final = turns[1]["interactive_cli_intent_diagnostics"]["final_classification"]
    assert final["target_npc"] == "Bran"
    assert "Ash Lantern" in final["requested_terms"]
    assert "trail name" in final["requested_terms"]


def test_memory_cleanup_revalidates_feature_matrix_gap_to_hard_pass() -> None:
    scenario = feature_matrix._select_feature_scenarios(["npc_memory_recall_probe"])[0]
    scenario_result = {
        "summary": {"completed_turns": 2, "error_count": 0},
        "turns": [
            _turn(scenario.commands[0]),
            _turn(scenario.commands[1], narration="I don't remember."),
        ],
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

    cleanup = apply_short_session_memory_recall_to_matrix_result(result)
    result["summary"]["memory_response_quality_cleanup"] = cleanup
    revalidated = feature_zip._revalidate_after_cleanup(result)

    assert cleanup["changed_turns"] == 2
    assert revalidated["summary"]["failed"] == []
    assert revalidated["summary"]["feature_gap_count"] == 0
    assert revalidated["summary"]["passed"] == 1
