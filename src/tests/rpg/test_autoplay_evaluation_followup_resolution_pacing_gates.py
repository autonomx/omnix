from tests.rpg.autoplay_llm_campaign import _build_100_turn_evaluation_summary


def test_evaluation_uses_followup_resolution_pressure_and_world_signal_summaries():
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
        narration_grounding_summary={
            "checked_count": 100,
            "selected_output_invalid_count": 0,
            "provider_json_parse_failed_count": 0,
            "provider_invalid_count": 0,
            "deterministic_fallback_rate": 0.0,
        },
        progress_quality_summary={
            "meaningful_progress_rate": 1.0,
            "no_change_turn_count": 0,
            "max_no_change_streak": 0,
        },
        checkpoint_summary={
            "checkpoint_validation_failures": 0,
            "checkpoint_count": 4,
            "validated_count": 4,
        },
        loop_detection_summary={
            "repeated_action_window_count": 0,
            "loop_warning_count": 0,
        },
        mechanics_coverage_summary={
            "required_ok": True,
            "real_required_ok": True,
            "coverage_rate": 1.0,
            "real_coverage_rate": 1.0,
            "missing_required": [],
            "missing_real_required": [],
        },
        story_arc_lifecycle_summary={
            "completed_count": 4,
            "failed_count": 0,
            "active_count": 2,
            "status_counts": {"completed": 4, "active": 2},
        },
        story_arc_aftermath_summary={
            "aftermath_event_count": 2,
            "world_signal_count": 2,
            "npc_memory_event_count": 2,
            "followup_hook_count": 2,
            "seeded_followup_arc_count": 2,
        },
        faction_reputation_summary={
            "faction_count": 2,
            "factions": [{"faction_id": "faction:test", "history_count": 1}],
        },
        followup_arc_progression_summary={
            "progressed_count": 2,
            "progressed_arc_ids": ["arc:a", "arc:b"],
            "world_signal_count": 2,
        },
        faction_pressure_summary={
            "pressure_event_count": 16,
            "world_signal_count": 10,
            "by_faction": {"faction:test": 16},
        },
        followup_arc_resolution_summary={
            "resolved_count": 2,
            "resolved_arc_ids": ["arc:a", "arc:b"],
            "escalation_seed_count": 2,
            "escalation_arcs": [{"arc_id": "arc:next"}],
        },
        pressure_pacing_summary={
            "accepted_pressure_event_count": 16,
            "rejected_pressure_event_count": 167,
            "rejected_by_reason": {"min_gap_turns": 159},
        },
        world_signal_summary={
            "world_signal_count": 22,
            "by_kind": {"faction_pressure": 10},
            "by_faction": {"faction:test": 10},
        },
    )

    assert evaluation["gates"]["followup_arc_resolution_present"]["ok"] is True
    assert evaluation["gates"]["escalation_branch_seeded"]["ok"] is True
    assert evaluation["gates"]["pressure_pacing_active"]["ok"] is True
    assert evaluation["gates"]["world_signal_summary_present"]["ok"] is True

    assert "followup_arc_resolution_present" not in evaluation["failed_gates"]
    assert "pressure_pacing_active" not in evaluation["failed_gates"]