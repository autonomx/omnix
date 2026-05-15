from tests.rpg.autoplay_llm_campaign import _build_100_turn_evaluation_summary


def test_evaluation_gates_accept_direct_graph_bridge_summaries():
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
        turn_action_consistency_summary={"checked_count": 100, "unrepaired_count": 0},
        scenario_progression_action_repeat_summary={"repeat_warning_count": 0},
        story_arc_aftermath_summary={
            "ok": True,
            "aftermath_event_count": 9,
            "direct_graph_aftermath_count": 9,
        },
        faction_reputation_summary={
            "ok": True,
            "history_count": 4,
            "direct_graph_reputation_event_count": 4,
        },
        faction_pressure_summary={
            "ok": True,
            "pressure_event_count": 6,
            "direct_graph_pressure_count": 6,
        },
        pressure_pacing_summary={
            "ok": True,
            "accepted_pressure_count": 6,
            "direct_graph_pressure_count": 6,
            "accepted_pressure_event_count": 6,
            "rejected_pressure_event_count": 2,
        },
        followup_arc_progression_summary={
            "ok": True,
            "progression_event_count": 6,
            "active_followup_arc_count": 1,
        },
        followup_arc_resolution_summary={
            "ok": True,
            "resolved_or_escalated_count": 1,
            "resolution_event_count": 1,
        },
        escalation_arc_progression_summary={
            "ok": True,
            "progression_event_count": 7,
            "active_escalation_arc_count": 1,
        },
        escalation_branch_summary={
            "ok": True,
            "seeded_count": 1,
        },
        npc_agency_summary={
            "ok": True,
            "event_count": 3,
            "memory_event_count": 3,
        },
    )

    for gate_name in (
        "story_arc_aftermath_present",
        "faction_reputation_changed",
        "faction_pressure_present",
        "pressure_pacing_active",
        "followup_arc_progression_present",
        "followup_arc_resolution_present",
        "escalation_branch_seeded",
        "escalation_arc_progression_present",
        "npc_agency_present",
    ):
        assert evaluation["gates"][gate_name]["ok"] is True