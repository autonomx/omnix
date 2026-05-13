from tests.rpg.autoplay_llm_campaign import _build_100_turn_readiness_summary


def _call_readiness(**kwargs):
    base = {
        "summary": kwargs.pop("summary", {}),
        "transcript": kwargs.pop("transcript", []),
        "requested_turns": 100,
        "turns_executed": 100,
        "runtime_errors": [],
        "warnings": [],
    }
    base.update(kwargs)
    return _build_100_turn_readiness_summary(**base)


def test_readiness_uses_escalation_and_compression_summaries_from_args():
    readiness = _call_readiness(
        summary={},
        escalation_arc_progression_summary={
            "ok": True,
            "progressed_count": 2,
            "progressed_arc_ids": [
                "arc:sable_chain_handler",
                "arc:voss_backer_pressure",
            ],
        },
        world_state_compression_summary={
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
    )

    assert readiness["gates"]["escalation_arc_progression_present"]["ok"] is True
    assert readiness["gates"]["world_state_compression_active"]["ok"] is True
    assert "escalation_arc_progression_present" not in readiness["failed_gates"]
    assert "world_state_compression_active" not in readiness["failed_gates"]


def test_readiness_uses_escalation_and_compression_summaries_from_summary_fallback():
    readiness = _call_readiness(
        summary={
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
    )

    assert readiness["gates"]["escalation_arc_progression_present"]["ok"] is True
    assert readiness["gates"]["world_state_compression_active"]["ok"] is True
    assert "escalation_arc_progression_present" not in readiness["failed_gates"]
    assert "world_state_compression_active" not in readiness["failed_gates"]