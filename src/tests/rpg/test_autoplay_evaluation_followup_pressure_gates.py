from tests.rpg.autoplay_llm_campaign import _build_100_turn_evaluation_summary


def test_evaluation_followup_and_faction_pressure_gates_use_passed_summaries():
    evaluation = _build_100_turn_evaluation_summary(
        turns_executed=100,
        requested_turns=100,
        runtime_errors=[],
        warnings=[],
        transcript=[{"turn_index": i + 1} for i in range(100)],
        performance_summary={
            "ok": True,
            "avg_turn_seconds": 1.0,
            "p95_turn_seconds": 2.0,
            "max_turn_seconds": 3.0,
        },
        narration_grounding_summary={
            "ok": True,
            "checked_count": 100,
            "violation_count": 0,
        },
        progress_quality_summary={
            "ok": True,
            "meaningful_progress_rate": 1.0,
            "no_change_turn_count": 0,
            "max_no_change_streak": 0,
        },
        checkpoint_summary={
            "ok": True,
            "checkpoint_count": 4,
            "validated_count": 4,
        },
        loop_detection_summary={
            "ok": True,
            "max_loop_streak": 0,
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
            "completed_count": 2,
            "failed_count": 0,
            "active_count": 2,
            "status_counts": {"completed": 2, "active": 2},
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
            "factions": [
                {"faction_id": "faction:test", "history_count": 1}
            ],
        },
        followup_arc_progression_summary={
            "progressed_count": 2,
            "progressed_arc_ids": ["arc:a", "arc:b"],
            "world_signal_count": 2,
        },
        faction_pressure_summary={
            "pressure_event_count": 2,
            "world_signal_count": 2,
            "by_faction": {"faction:test": 2},
        },
    )

    assert evaluation["gates"]["followup_arc_progression_present"]["ok"] is True
    assert evaluation["gates"]["faction_pressure_present"]["ok"] is True
    assert "followup_arc_progression_present" not in evaluation["failed_gates"]
    assert "faction_pressure_present" not in evaluation["failed_gates"]