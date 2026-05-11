from tests.rpg.autoplay_llm_campaign import (
    _build_100_turn_evaluation_summary,
    _build_canonical_progress_quality_summary,
)


def test_100_turn_evaluation_summary_passes_clean_inputs():
    summary = _build_100_turn_evaluation_summary(
        turns_executed=100,
        requested_turns=100,
        runtime_errors=[],
        warnings=[],
        transcript=[{"meaningful_progress": True, "turn_seconds": 1.0} for _ in range(100)],
        performance_summary={"avg_turn_seconds": 1.0, "p95_turn_seconds": 2.0},
        narration_grounding_summary={
            "checked_count": 100,
            "invalid_count": 0,
            "provider_json_parse_failed_count": 0,
            "provider_invalid_count": 0,
        },
        progress_quality_summary={
            "meaningful_progress_rate": 0.50,
            "fallback_player_action_rate": 0.0,
            "no_change_turns": 0,
        },
        checkpoint_summary={"failure_count": 0},
        loop_detection_summary={"repeated_action_window_count": 0, "loop_warning_count": 0},
    )

    assert summary["ok"] is True
    assert summary["failed_gate_count"] == 0


def test_100_turn_evaluation_summary_fails_missing_grounding():
    summary = _build_100_turn_evaluation_summary(
        turns_executed=100,
        requested_turns=100,
        runtime_errors=[],
        warnings=[],
        transcript=[],
        performance_summary={},
        narration_grounding_summary={"checked_count": 0},
        progress_quality_summary={
            "meaningful_progress_rate": 0.50,
            "fallback_player_action_rate": 0.0,
            "no_change_turns": 0,
        },
        checkpoint_summary={"failure_count": 0},
        loop_detection_summary={"repeated_action_window_count": 0, "loop_warning_count": 0},
    )

    assert summary["ok"] is False
    assert "narration_grounding_checked" in summary["failed_gates"]


def test_canonical_progress_quality_counts_meaningful_rows():
    transcript = [
        {"meaningful_progress": True, "action_type": "talk", "location": "tavern"},
        {"meaningful_progress": False, "action_type": "observe", "location": "tavern"},
        {"state_delta": {"quest_log_delta": {"updated": True}}, "action_type": "quest", "location": "road"},
    ]

    summary = _build_canonical_progress_quality_summary(
        transcript=transcript,
        existing_progress={},
        strict_progress={},
    )

    assert summary["turn_count"] == 3
    assert summary["meaningful_progress_count"] == 1
    assert summary["unique_location_count"] == 2