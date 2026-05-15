from argparse import Namespace

from tests.rpg.autoplay_llm_campaign import _rebuild_final_100_turn_evaluation


def test_final_eval_rebuild_uses_dialogue_relevance_summary():
    summary = {
        "requested_turns": 100,
        "turns_executed": 100,
        "runtime_errors": [],
        "warnings": [],
        "performance_seconds_summary": {
            "avg_turn_seconds": 1.0,
            "p95_turn_seconds": 2.0,
            "max_turn_seconds": 3.0,
        },
        "narration_grounding_summary": {
            "checked_count": 100,
            "selected_output_invalid_count": 0,
            "provider_json_parse_failed_count": 0,
            "provider_invalid_count": 0,
            "deterministic_fallback_rate": 0.0,
        },
        "canonical_progress_quality": {
            "meaningful_progress_rate": 1.0,
            "no_change_turn_count": 0,
            "max_no_change_streak": 0,
        },
        "checkpoint_validation_summary": {
            "checkpoint_validation_failures": 0,
            "checkpoint_count": 4,
            "validated_count": 4,
        },
        "loop_detection_summary": {
            "repeated_action_window_count": 0,
            "loop_warning_count": 0,
        },
        "mechanics_coverage_summary": {
            "required_ok": True,
            "real_required_ok": True,
            "coverage_rate": 1.0,
            "real_coverage_rate": 1.0,
            "missing_required": [],
            "missing_real_required": [],
        },
        "dialogue_action_relevance_summary": {
            "ok": True,
            "checked_count": 100,
            "mismatch_count": 28,
            "mismatch_rate": 0.28,
            "repaired_count": 28,
            "unrepaired_count": 0,
            "source_gate_block_count": 0,
            "by_reason": {"travel_action_dialogue_mismatch": 19},
        },
    }

    rebuilt = _rebuild_final_100_turn_evaluation(
        args=Namespace(turns=100),
        summary=summary,
        transcript=[{"turn_index": i + 1} for i in range(100)],
        dialogue_action_relevance_summary=summary["dialogue_action_relevance_summary"],
    )

    gate = rebuilt["hundred_turn_evaluation"]["gates"]["dialogue_action_relevance_ok"]
    assert gate["ok"] is True
    assert gate["value"]["checked_count"] == 100
    assert "dialogue_action_relevance_ok" not in rebuilt["hundred_turn_evaluation"]["failed_gates"]