from __future__ import annotations

from app.rpg.session.fast_turn_latency import (
    FAST_TURN_LATENCY_VERSION,
    attach_turn_latency,
    latency_from_manual_timing,
    merge_latency_records,
)


def test_latency_from_manual_timing_maps_stage_names() -> None:
    latency = latency_from_manual_timing(
        {
            "manual_turn_ms": 100.0,
            "pre_runtime_intent_llm_ms": 20.0,
            "deterministic_runtime_apply_ms": 10.0,
            "state_snapshot_ms": 5.0,
            "grounding_validation_ms": 7.0,
            "repair_ms": 3.0,
            "deferred_enqueue_ms": 2.0,
        },
        mode="fast",
        model_name="model-a",
    )

    assert latency["format_version"] == FAST_TURN_LATENCY_VERSION
    assert latency["mode"] == "fast"
    assert latency["model_name"] == "model-a"
    assert latency["parse_ms"] == 20.0
    assert latency["sim_ms"] == 10.0
    assert latency["context_ms"] == 5.0
    assert latency["postprocess_ms"] == 10.0
    assert latency["background_ms"] == 2.0
    assert latency["llm_total_ms"] == 53.0


def test_merge_latency_records_keeps_token_counts() -> None:
    latency = merge_latency_records(
        {"mode": "dialogue_fast", "parse_ms": 1.25, "input_tokens": 50},
        {"sim_ms": 2.75, "input_tokens": 25, "output_tokens": 12},
    )

    assert latency["mode"] == "dialogue_fast"
    assert latency["parse_ms"] == 1.25
    assert latency["sim_ms"] == 2.75
    assert latency["context_ms"] == 0.0
    assert latency["input_tokens"] == 75
    assert latency["output_tokens"] == 12


def test_attach_turn_latency_copies_to_nested_result() -> None:
    result = {"ok": True, "result": {"summary": "done"}}
    attached = attach_turn_latency(result, {"mode": "service_fast", "sim_ms": 4.0})

    assert attached["fast_turn_latency"]["sim_ms"] == 4.0
    assert attached["result"]["fast_turn_latency"]["sim_ms"] == 4.0
