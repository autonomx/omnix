from tests.rpg.autoplay_llm_campaign import _build_100_turn_evaluation_summary


def test_evaluation_uses_turn_action_consistency_summary():
    evaluation = _build_100_turn_evaluation_summary(
        turns_executed=100,
        requested_turns=100,
        runtime_errors=[],
        warnings=[],
        transcript=[{"turn_index": i + 1} for i in range(100)],
        performance_summary={
            "avg_turn_seconds": 1.0,
            "p95_turn_seconds": 2.0,
            "max_turn_seconds": 3.0,
        },
        narration_grounding_summary={"checked_count": 100},
        progress_quality_summary={"meaningful_progress_rate": 1.0},
        checkpoint_summary={"checkpoint_validation_failures": 0},
        loop_detection_summary={"loop_warning_count": 0},
        mechanics_coverage_summary={"required_ok": True, "real_required_ok": True},
        turn_action_consistency_summary={
            "ok": True,
            "checked_count": 100,
            "mismatch_count": 1,
            "mismatch_rate": 0.01,
            "repaired_count": 1,
            "unrepaired_count": 0,
            "by_field": {"progress_quality.player_action": 1},
        },
    )

    gate = evaluation["gates"]["turn_action_consistency_ok"]
    assert gate["ok"] is True
    assert gate["value"]["checked_count"] == 100
    assert gate["value"]["unrepaired_count"] == 0
    assert "turn_action_consistency_ok" not in evaluation["failed_gates"]