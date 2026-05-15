from tests.rpg.autoplay_llm_campaign import (
    _apply_direct_graph_lifecycle_bridges,
    _build_100_turn_evaluation_summary,
)


def test_direct_graph_bridge_populates_old_and_new_pressure_pacing_keys():
    summary = {
        "direct_graph_lifecycle_evidence": {
            "ok": True,
            "completed_action_count": 2,
            "faction_like_count": 1,
            "npc_like_count": 0,
            "combat_like_count": 1,
            "pressure_like_count": 2,
            "aftermath_like_count": 2,
            "escalation_like_count": 2,
        },
        "pressure_pacing_summary": {
            "accepted_pressure_event_count": 0,
            "accepted_pressure_count": 0,
            "rejected_pressure_event_count": 0,
        },
    }

    bridged = _apply_direct_graph_lifecycle_bridges(summary)
    pressure = bridged["pressure_pacing_summary"]

    assert pressure["direct_graph_pressure_count"] == 2
    assert pressure["accepted_pressure_count"] == 2
    assert pressure["accepted_pressure_event_count"] == 2
    assert pressure["direct_graph_pacing_bridge_active"] is True


def test_pressure_pacing_gate_accepts_direct_graph_pressure_without_rejections():
    evaluation = _build_100_turn_evaluation_summary(
        turns_executed=100,
        requested_turns=100,
        runtime_errors=[],
        warnings=[],
        transcript=[{"turn_index": i + 1} for i in range(100)],
        performance_summary={
            "avg_turn_seconds": 1,
            "p95_turn_seconds": 2,
            "max_turn_seconds": 3,
        },
        narration_grounding_summary={"checked_count": 100},
        progress_quality_summary={"meaningful_progress_rate": 1.0},
        checkpoint_summary={"checkpoint_validation_failures": 0},
        loop_detection_summary={"loop_warning_count": 0},
        mechanics_coverage_summary={"required_ok": True, "real_required_ok": True},
        pressure_pacing_summary={
            "accepted_pressure_count": 2,
            "accepted_pressure_event_count": 2,
            "direct_graph_pressure_count": 2,
            "direct_graph_pacing_bridge_active": True,
            "rejected_pressure_event_count": 0,
        },
    )

    gate = evaluation["gates"]["pressure_pacing_active"]

    assert gate["ok"] is True
    assert gate["value"]["direct_graph_pressure_count"] == 2
