from tests.rpg.autoplay_llm_campaign import _build_100_turn_evaluation_summary


def test_evaluation_uses_faction_consequence_and_npc_reaction_summaries():
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
        faction_consequence_summary={
            "ok": True,
            "event_count": 10,
            "world_signal_count": 10,
            "by_faction": {
                "faction:rusty_flagon_locals": 3,
                "faction:sable_chain": 4,
                "faction:voss_backers": 3,
            },
            "by_kind": {
                "backer_pressure_after_name_spread": 3,
                "locals_rally_after_combat": 3,
                "retaliation_after_combat": 4,
            },
        },
        npc_reaction_summary={
            "ok": True,
            "event_count": 10,
            "memory_event_count": 10,
            "world_signal_count": 10,
            "by_npc": {
                "npc:bran": 4,
                "npc:garran": 3,
                "npc:sera": 3,
            },
            "by_kind": {
                "arms_locals": 3,
                "tracks_voss_pressure": 3,
                "warns_about_retaliation": 4,
            },
        },
    )

    faction_gate = evaluation["gates"]["faction_consequence_present"]
    npc_gate = evaluation["gates"]["npc_reaction_present"]

    assert faction_gate["ok"] is True
    assert faction_gate["value"]["event_count"] == 10
    assert npc_gate["ok"] is True
    assert npc_gate["value"]["event_count"] == 10
    assert "faction_consequence_present" not in evaluation["failed_gates"]
    assert "npc_reaction_present" not in evaluation["failed_gates"]