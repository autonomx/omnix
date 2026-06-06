from app.rpg.autoplay_performance_artifacts import build_autoplay_performance_summary


def test_phase13_11_manual_turn_breakdown_metrics_are_summarized():
    rows = [
        {
            "turn_index": 1,
            "timing": {
                "manual_turn_ms": 12000,
                "pre_runtime_intent_llm_ms": 4000,
                "deterministic_runtime_apply_ms": 3000,
                "grounding_validation_ms": 800,
                "repair_ms": 200,
                "state_snapshot_ms": 1000,
                "deferred_enqueue_ms": 5,
            },
        },
        {
            "turn_index": 2,
            "stage_timing": {
                "manual_turn_ms": 14000,
                "pre_runtime_intent_llm_ms": 5000,
                "deterministic_runtime_apply_ms": 3200,
                "grounding_validation_ms": 900,
                "repair_ms": 300,
                "state_snapshot_ms": 1100,
                "deferred_enqueue_ms": 7,
            },
        },
    ]

    summary = build_autoplay_performance_summary(rows)
    breakdown = summary["manual_turn_breakdown"]

    assert breakdown["turns_observed"] == 2
    assert breakdown["summary"]["manual_turn_ms"]["avg_ms"] == 13000
    assert breakdown["summary"]["pre_runtime_intent_llm_ms"]["avg_ms"] == 4500
    assert breakdown["summary"]["deterministic_runtime_apply_ms"]["avg_ms"] == 3100
    assert breakdown["summary"]["grounding_validation_ms"]["avg_ms"] == 850
    assert breakdown["summary"]["repair_ms"]["avg_ms"] == 250
    assert breakdown["summary"]["state_snapshot_ms"]["avg_ms"] == 1050
    assert breakdown["summary"]["deferred_enqueue_ms"]["avg_ms"] == 6


def test_phase13_11_manual_turn_breakdown_accepts_aliases():
    rows = [
        {
            "turn_index": 1,
            "metrics": {
                "first_call_llm_ms": 12,
                "runtime_apply_ms": 34,
                "background_enqueue_ms": 2,
            },
        }
    ]

    summary = build_autoplay_performance_summary(rows)
    row = summary["manual_turn_breakdown"]["turn_metrics"][0]
    assert row["pre_runtime_intent_llm_ms"] == 12
    assert row["deterministic_runtime_apply_ms"] == 34
    assert row["deferred_enqueue_ms"] == 2
