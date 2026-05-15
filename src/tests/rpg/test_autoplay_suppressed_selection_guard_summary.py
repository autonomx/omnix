from tests.rpg.autoplay_llm_campaign import (
    _build_100_turn_evaluation_summary,
    _build_suppressed_selection_guard_summary,
)


def test_suppressed_selection_guard_summary_counts_retarget():
    summary = _build_suppressed_selection_guard_summary(
        transcript=[
            {
                "turn_index": 15,
                "selected_command_before_suppression_guard": (
                    "I ask Garran to join me on the mill road."
                ),
                "player_action": "I buy two rations from Bran.",
                "suppressed_selected_action_guard": {
                    "retargeted": True,
                    "reason": "suppressed_selected_action_retargeted",
                    "suppressed_match": {"action_id": "ask_garran_to_join"},
                    "replacement_action": {"action_id": "buy_rations_from_bran"},
                },
            }
        ]
    )

    assert summary["checked_count"] == 1
    assert summary["retargeted_count"] == 1
    assert summary["no_replacement_count"] == 0
    assert summary["ok"] is True


def test_evaluation_uses_suppressed_selection_guard_summary():
    evaluation = _build_100_turn_evaluation_summary(
        turns_executed=100,
        requested_turns=100,
        runtime_errors=[],
        warnings=[],
        transcript=[{"turn_index": i + 1} for i in range(100)],
        performance_summary={"avg_turn_seconds": 1, "p95_turn_seconds": 2, "max_turn_seconds": 3},
        narration_grounding_summary={"checked_count": 100},
        progress_quality_summary={"meaningful_progress_rate": 1.0},
        checkpoint_summary={"checkpoint_validation_failures": 0},
        loop_detection_summary={"loop_warning_count": 0},
        mechanics_coverage_summary={"required_ok": True, "real_required_ok": True},
        suppressed_selection_guard_summary={
            "ok": True,
            "checked_count": 100,
            "retargeted_count": 3,
            "no_replacement_count": 0,
            "by_action_id": {"ask_garran_to_join": 3},
        },
    )

    gate = evaluation["gates"]["suppressed_selection_guard_ok"]

    assert gate["ok"] is True
    assert gate["value"]["checked_count"] == 100
    assert gate["value"]["retargeted_count"] == 3