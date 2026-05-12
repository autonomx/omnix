from tests.rpg.autoplay_llm_campaign import _build_100_turn_readiness_summary


def test_readiness_story_arc_gate_uses_lifecycle_summary():
    summary = {
        "behavioral_autoplay_eval_summary": {},
        "campaign_progression_summary": {},
        "progress_timeline_summary": {
            "turns": 100,
            "meaningful_progress_turns": 100,
            "meaningful_progress_rate": 1.0,
        },
        "story_arc_lifecycle_summary": {
            "ok": True,
            "completed_count": 2,
            "failed_count": 0,
            "active_count": 0,
            "status_counts": {"completed": 2},
        },
    }

    readiness = _build_100_turn_readiness_summary(
        summary=summary,
        transcript=[{"turn_index": i + 1} for i in range(100)],
        requested_turns=100,
        story_arc_lifecycle_summary=summary["story_arc_lifecycle_summary"],
    )

    gate = readiness["gates"]["story_arc_resolution_present"]

    assert gate["ok"] is True
    assert "story_arc_resolution_present" not in readiness["failed_gates"]