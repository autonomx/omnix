from tests.rpg.autoplay_llm_campaign import (
    _build_100_turn_evaluation_summary,
    _build_100_turn_readiness_summary,
)


def test_evaluation_faction_consequence_and_npc_reaction_gates_pass():
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
        faction_consequence_summary={
            "ok": True,
            "event_count": 2,
            "world_signal_count": 2,
            "by_faction": {"faction:sable_chain": 1, "faction:rusty_flagon_locals": 1},
            "by_kind": {"retaliation_after_combat": 1, "locals_rally_after_combat": 1},
        },
        npc_reaction_summary={
            "ok": True,
            "event_count": 2,
            "memory_event_count": 2,
            "world_signal_count": 2,
            "by_npc": {"npc:bran": 1, "npc:garran": 1},
            "by_kind": {"warns_about_retaliation": 1, "arms_locals": 1},
        },
    )

    assert evaluation["gates"]["faction_consequence_present"]["ok"] is True
    assert evaluation["gates"]["npc_reaction_present"]["ok"] is True


def test_readiness_faction_consequence_and_npc_reaction_gates_pass():
    readiness = _build_100_turn_readiness_summary(
        summary={
            "faction_consequence_summary": {
                "ok": True,
                "event_count": 2,
                "world_signal_count": 2,
                "by_faction": {"faction:sable_chain": 1},
                "by_kind": {"retaliation_after_combat": 1},
            },
            "npc_reaction_summary": {
                "ok": True,
                "event_count": 2,
                "memory_event_count": 2,
                "world_signal_count": 2,
                "by_npc": {"npc:bran": 1},
                "by_kind": {"warns_about_retaliation": 1},
            },
        },
        transcript=[],
        requested_turns=100,
        turns_executed=100,
        runtime_errors=[],
        warnings=[],
    )

    assert readiness["gates"]["faction_consequence_present"]["ok"] is True
    assert readiness["gates"]["npc_reaction_present"]["ok"] is True