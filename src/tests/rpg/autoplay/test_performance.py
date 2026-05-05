from tests.rpg.autoplay.performance import summarize_performance


def test_summarize_performance_basic_stats():
    transcript = [
        {
            "turn_index": 1,
            "player_action": "I ask Bran.",
            "performance": {
                "turn_total_ms": 100.0,
                "player_agent_ms": 20.0,
                "manual_turn_ms": 50.0,
                "story_hooks_ms": 5.0,
            },
        },
        {
            "turn_index": 2,
            "player_action": "I inspect the tavern.",
            "performance": {
                "turn_total_ms": 200.0,
                "player_agent_ms": 30.0,
                "manual_turn_ms": 100.0,
                "story_hooks_ms": 10.0,
            },
        },
    ]

    metrics = summarize_performance(
        transcript=transcript,
        campaign_wall_ms=400.0,
        artifact_write_ms=25.0,
    )

    assert metrics["turn_count"] == 2
    assert metrics["avg_turn_ms"] == 150.0
    assert metrics["max_turn_ms"] == 200.0
    assert metrics["turns_per_second"] == 5.0
    assert metrics["artifact_write_ms"] == 25.0
    assert metrics["stage_summary"]["manual_turn_ms"]["total_ms"] == 150.0
    assert metrics["slowest_turns"][0]["turn_index"] == 2