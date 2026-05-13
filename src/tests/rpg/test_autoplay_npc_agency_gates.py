from tests.rpg.autoplay_llm_campaign import (
    _build_100_turn_evaluation_summary,
    _build_100_turn_readiness_summary,
)


def test_evaluation_npc_agency_gate_passes():
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
        npc_agency_summary={
            "ok": True,
            "npc_count": 3,
            "schedule_event_count": 5,
            "agency_event_count": 2,
            "memory_event_count": 2,
        },
    )

    assert evaluation["gates"]["npc_agency_present"]["ok"] is True


def test_readiness_npc_agency_gate_passes():
    readiness = _build_100_turn_readiness_summary(
        summary={
            "npc_agency_summary": {
                "ok": True,
                "npc_count": 3,
                "schedule_event_count": 5,
                "agency_event_count": 2,
                "memory_event_count": 2,
            }
        },
        transcript=[],
        requested_turns=100,
        turns_executed=100,
        runtime_errors=[],
        warnings=[],
    )

    assert readiness["gates"]["npc_agency_present"]["ok"] is True