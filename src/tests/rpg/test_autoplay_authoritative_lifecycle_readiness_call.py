from argparse import Namespace

from tests.rpg.autoplay_llm_campaign import _build_authoritative_final_lifecycle_summary


def test_authoritative_lifecycle_rebuild_passes_required_readiness_args():
    summary = {
        "ok": True,
        "requested_turns": 100,
        "turns_executed": 100,
        "runtime_errors": [],
        "warnings": [],
        "hundred_turn_evaluation": {"ok": True, "gates": {}},
        "hundred_turn_readiness_summary": {"ok": True, "gates": {}},
        "story_arc_lifecycle_summary": {"completed_count": 4, "failed_count": 0},
        "escalation_arc_progression_summary": {
            "ok": True,
            "progressed_count": 2,
            "progressed_arc_ids": ["arc:sable_chain_handler", "arc:voss_backer_pressure"],
        },
        "world_state_compression_summary": {
            "ok": True,
            "compression_event_count": 4,
            "latest_state_budget": {"ok": True},
            "compressed_state_preview": {"story_arc_count": 6},
        },
    }

    rebuilt = _build_authoritative_final_lifecycle_summary(
        args=Namespace(turns=100),
        summary=summary,
        runtime_state={},
        transcript=[{"turn_index": i + 1} for i in range(100)],
        background_drain_events=[],
        pre_turn_advisory_promotion_slow_events=[],
        pre_turn_advisory_promotion_auto_disabled=False,
        pre_turn_advisory_promotion_disable_reason="",
        story_arc_lifecycle_summary=summary["story_arc_lifecycle_summary"],
        escalation_arc_progression_summary=summary["escalation_arc_progression_summary"],
        world_state_compression_summary=summary["world_state_compression_summary"],
    )

    assert "hundred_turn_readiness_summary" in rebuilt
    assert rebuilt["hundred_turn_readiness_summary"]["gates"]["escalation_arc_progression_present"]["ok"] is True
    assert rebuilt["hundred_turn_readiness_summary"]["gates"]["world_state_compression_active"]["ok"] is True