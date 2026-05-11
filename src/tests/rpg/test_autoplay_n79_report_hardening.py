from tests.rpg.autoplay_llm_campaign import (
    _build_selected_output_grounding_health,
    _build_performance_seconds_summary,
    _build_canonical_progress_quality_summary,
)


def test_selected_output_grounding_allows_bounded_deterministic_fallbacks():
    health = _build_selected_output_grounding_health(
        {
            "checked_count": 100,
            "invalid_count": 5,
            "fallback_used_count": 5,
            "fallback_source_counts": {"deterministic_fallback": 5, "none": 95},
            "provider_json_parse_failed_count": 0,
            "provider_invalid_count": 0,
        },
        requested_turns=100,
    )

    assert health["ok"] is True
    assert health["deterministic_fallback_rate"] == 0.05


def test_selected_output_grounding_fails_excessive_deterministic_fallbacks():
    health = _build_selected_output_grounding_health(
        {
            "checked_count": 100,
            "invalid_count": 20,
            "fallback_used_count": 20,
            "fallback_source_counts": {"deterministic_fallback": 20, "none": 80},
            "provider_json_parse_failed_count": 0,
            "provider_invalid_count": 0,
        },
        requested_turns=100,
    )

    assert health["ok"] is False


def test_performance_seconds_summary_uses_aggregate_ms_metrics():
    summary = _build_performance_seconds_summary(
        [{} for _ in range(100)],
        performance={
            "avg_turn_ms": 4082.111,
            "median_turn_ms": 3674.188,
            "p95_turn_ms": 5706.868,
            "max_turn_ms": 9116.627,
            "campaign_wall_seconds": 510.911,
        },
    )

    assert round(summary["avg_turn_seconds"], 3) == 4.082
    assert round(summary["p95_turn_seconds"], 3) == 5.707
    assert round(summary["max_turn_seconds"], 3) == 9.117


def test_canonical_progress_quality_prefers_health_metrics_over_keyword_scan():
    final_summary = {
        "health": {
            "metrics": {
                "fallback_player_action_rate": 0.0,
                "progress_quality": {
                    "turn_count": 100,
                    "meaningful_turns": 1,
                    "meaningful_progress_rate": 0.01,
                    "no_change_turns": 97,
                    "quality_counts": {
                        "meaningful_progress": 1,
                        "no_change": 97,
                    },
                },
            }
        }
    }

    summary = _build_canonical_progress_quality_summary(
        transcript=[{"debug": "quest combat service npc"} for _ in range(100)],
        existing_progress={},
        strict_progress={},
        final_summary=final_summary,
    )

    assert summary["source"] == "health.metrics.progress_quality"
    assert summary["meaningful_progress_rate"] == 0.01
    assert summary["no_change_turns"] == 97
    assert summary["ok"] is False