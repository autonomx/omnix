import sys

from app.rpg.autoplay_performance_artifacts import build_autoplay_performance_summary
from app.rpg.session import interactive_first_call_runtime as runtime


def test_phase13_12_recursion_budget_is_raised(monkeypatch):
    original = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(1000)
        assert runtime._ensure_runtime_recursion_budget() >= 10000
    finally:
        sys.setrecursionlimit(original)


def test_phase13_12_manual_stage_timing_attaches_to_result_and_nested_result():
    result = {"ok": True, "result": {"ok": True}}
    timing = {
        "manual_turn_ms": 10.0,
        "pre_runtime_intent_llm_ms": 1.0,
        "deterministic_runtime_apply_ms": 2.0,
        "grounding_validation_ms": 3.0,
        "repair_ms": 4.0,
        "state_snapshot_ms": 5.0,
        "deferred_enqueue_ms": 6.0,
    }

    attached = runtime._attach_manual_stage_timing(result, timing)

    assert attached["manual_turn_stage_timing"] == timing
    assert attached["result"]["manual_turn_stage_timing"] == timing


def test_phase13_12_performance_summary_reads_manual_turn_stage_timing():
    rows = [
        {
            "turn_index": 1,
            "turn_result": {
                "manual_turn_stage_timing": {
                    "manual_turn_ms": 100.0,
                    "pre_runtime_intent_llm_ms": 10.0,
                    "deterministic_runtime_apply_ms": 20.0,
                    "grounding_validation_ms": 30.0,
                    "repair_ms": 40.0,
                    "state_snapshot_ms": 50.0,
                    "deferred_enqueue_ms": 1.0,
                }
            },
        },
        {
            "turn_index": 2,
            "manual_turn_stage_timing": {
                "manual_turn_ms": 200.0,
                "pre_runtime_intent_llm_ms": 20.0,
                "deterministic_runtime_apply_ms": 40.0,
                "grounding_validation_ms": 60.0,
                "repair_ms": 80.0,
                "state_snapshot_ms": 100.0,
                "deferred_enqueue_ms": 3.0,
            },
        },
    ]

    summary = build_autoplay_performance_summary(rows)
    breakdown = summary["manual_turn_breakdown"]["summary"]

    assert breakdown["manual_turn_ms"]["avg_ms"] == 150.0
    assert breakdown["pre_runtime_intent_llm_ms"]["avg_ms"] == 15.0
    assert breakdown["deterministic_runtime_apply_ms"]["avg_ms"] == 30.0
    assert breakdown["grounding_validation_ms"]["avg_ms"] == 45.0
    assert breakdown["repair_ms"]["avg_ms"] == 60.0
    assert breakdown["state_snapshot_ms"]["avg_ms"] == 75.0
    assert breakdown["deferred_enqueue_ms"]["avg_ms"] == 2.0


def test_phase13_12_safe_deferred_enqueue_ms_reads_nested_alias():
    assert runtime._safe_deferred_enqueue_ms({"result": {"background_enqueue_ms": 7}}) == 7.0
    assert runtime._safe_deferred_enqueue_ms({}) == 0.0
