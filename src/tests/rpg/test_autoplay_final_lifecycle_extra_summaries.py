from argparse import Namespace

from tests.rpg.autoplay_llm_campaign import _build_authoritative_final_lifecycle_summary


def test_authoritative_lifecycle_accepts_turn_action_and_scenario_repeat_summaries():
    summary = _build_authoritative_final_lifecycle_summary(
        args=Namespace(turns=100),
        summary={
            "requested_turns": 100,
            "turns_executed": 100,
            "runtime_errors": [],
            "warnings": [],
            "performance_seconds_summary": {
                "avg_turn_seconds": 1.0,
                "p95_turn_seconds": 2.0,
                "max_turn_seconds": 3.0,
            },
            "narration_grounding_summary": {"checked_count": 100},
            "canonical_progress_quality": {"meaningful_progress_rate": 1.0},
            "checkpoint_validation_summary": {"checkpoint_validation_failures": 0},
            "loop_detection_summary": {"loop_warning_count": 0},
            "mechanics_coverage_summary": {
                "required_ok": True,
                "real_required_ok": True,
            },
        },
        runtime_state={},
        transcript=[{"turn_index": i + 1} for i in range(100)],
        background_drain_events=[],
        pre_turn_advisory_promotion_slow_events=[],
        pre_turn_advisory_promotion_auto_disabled=False,
        pre_turn_advisory_promotion_disable_reason="",
        dialogue_action_relevance_summary={
            "ok": True,
            "checked_count": 100,
            "mismatch_count": 0,
            "mismatch_rate": 0.0,
            "repaired_count": 0,
            "unrepaired_count": 0,
        },
        turn_action_consistency_summary={
            "ok": True,
            "checked_count": 100,
            "mismatch_count": 0,
            "mismatch_rate": 0.0,
            "repaired_count": 0,
            "unrepaired_count": 0,
            "forced_override_count": 0,
            "by_field": {},
        },
        scenario_progression_action_repeat_summary={
            "ok": True,
            "repeat_warning_count": 1,
            "suppressed_action_count": 1,
            "by_action_id": {"ask_garran_to_join": 1},
        },
    )

    assert summary["turn_action_consistency_summary"]["checked_count"] == 100
    assert summary["scenario_progression_action_repeat_summary"]["repeat_warning_count"] == 1

    readiness = summary["hundred_turn_readiness_summary"]["gates"]
    assert readiness["turn_action_consistency_ok"]["ok"] is True
    assert readiness["scenario_progression_repeats_bounded"]["ok"] is True