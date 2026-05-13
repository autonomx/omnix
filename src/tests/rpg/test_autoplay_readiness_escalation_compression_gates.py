from tests.rpg.autoplay_llm_campaign import _build_100_turn_readiness_summary


def test_readiness_uses_escalation_and_compression_summaries():
    summary = {
        "escalation_arc_progression_summary": {
            "ok": True,
            "progressed_count": 2,
            "progressed_arc_ids": [
                "arc:sable_chain_handler",
                "arc:voss_backer_pressure",
            ],
        },
        "world_state_compression_summary": {
            "ok": True,
            "compression_event_count": 4,
            "compressed_state_preview": {
                "story_arc_count": 6,
                "world_signal_count": 24,
            },
            "latest_state_budget": {
                "ok": True,
                "sections": {},
            },
        },
    }

    readiness = _build_100_turn_readiness_summary(
        summary=summary,
        transcript=[],
        requested_turns=100,
        escalation_arc_progression_summary=summary["escalation_arc_progression_summary"],
        world_state_compression_summary=summary["world_state_compression_summary"],
    )

    assert readiness["gates"]["escalation_arc_progression_present"]["ok"] is True
    assert readiness["gates"]["world_state_compression_active"]["ok"] is True
    assert "escalation_arc_progression_present" not in readiness["failed_gates"]
    assert "world_state_compression_active" not in readiness["failed_gates"]

# If your readiness builder requires additional args, copy default args from the nearest existing readiness test and add the two new summary params.