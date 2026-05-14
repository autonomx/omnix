from tests.rpg.autoplay_llm_campaign import (
    _build_100_turn_evaluation_summary,
    _build_100_turn_readiness_summary,
)


def test_evaluation_combat_lifecycle_gate_passes():
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
        combat_lifecycle_summary={
            "ok": True,
            "encounter_count": 2,
            "event_count": 2,
            "injury_count": 1,
            "consequence_event_count": 1,
            "economy_hint_count": 1,
            "by_outcome": {"victory": 2},
        },
    )

    assert evaluation["gates"]["combat_lifecycle_present"]["ok"] is True


def test_readiness_combat_lifecycle_gate_passes():
    readiness = _build_100_turn_readiness_summary(
        summary={
            "combat_lifecycle_summary": {
                "ok": True,
                "encounter_count": 2,
                "event_count": 2,
                "injury_count": 1,
                "consequence_event_count": 1,
                "economy_hint_count": 1,
                "by_outcome": {"victory": 2},
            }
        },
        transcript=[],
        requested_turns=100,
        turns_executed=100,
        runtime_errors=[],
        warnings=[],
    )

    assert readiness["gates"]["combat_lifecycle_present"]["ok"] is True