from __future__ import annotations

import json
import time
from pathlib import Path

from app.rpg.performance_trace import (
    attach_rpg_result_timing,
    build_traced_json_response,
    rpg_pipeline_span,
    rpg_pipeline_trace,
)
from app.rpg.response_trace_headers import finalize_rpg_trace_headers

_REPO_ROOT = Path(__file__).resolve().parents[4]


def test_nested_spans_use_exclusive_top_level_attribution() -> None:
    with rpg_pipeline_trace("turn.pipeline", session_id="session:test", trace_id="trace:test") as trace:
        with rpg_pipeline_span("turn.apply"):
            time.sleep(0.02)
            with rpg_pipeline_span("turn.runtime_resolution"):
                time.sleep(0.02)
        summary = trace.summary()

    spans = {span["name"]: span for span in summary["spans"]}
    assert spans["turn.apply"]["depth"] == 0
    assert spans["turn.runtime_resolution"]["depth"] == 1
    assert summary["measured_span_duration_ms"] >= summary["child_duration_ms"]
    assert summary["child_duration_ms"] <= summary["total_ms"]
    assert summary["attribution_percent"] >= 95.0
    assert summary["attribution_target_met"] is True
    assert summary["cpu_ms"] >= 0


def test_reported_provider_and_runtime_stages_are_named_without_llm_execution() -> None:
    result = {
        "ok": True,
        "interaction_id": "interaction:1",
        "turn_id": "turn:1",
        "llm_called": True,
        "manual_turn_stage_timing": {
            "manual_turn_ms": 125.0,
            "prompt_build_ms": 7.5,
            "provider_queue_ms": 3.0,
            "provider_ms": 80.0,
            "provider_decode_ms": 4.0,
            "deterministic_runtime_apply_ms": 20.0,
            "grounding_validation_ms": 5.0,
            "repair_ms": 2.0,
        },
    }

    with rpg_pipeline_trace("turn.pipeline", trace_id="trace:reported") as trace:
        with rpg_pipeline_span("turn.apply"):
            attach_rpg_result_timing(result)
        summary = trace.summary()

    reported = summary["reported_stage_ms"]
    assert reported["turn.manual_total"] == 125.0
    assert reported["provider.prompt_build"] == 7.5
    assert reported["provider.queue"] == 3.0
    assert reported["provider.request"] == 80.0
    assert reported["provider.decode"] == 4.0
    assert reported["turn.runtime_resolution"] == 20.0
    assert reported["dialogue.grounding_validation"] == 5.0
    assert reported["dialogue.quality_repair"] == 2.0
    assert summary["provider_called"] is True
    assert summary["interaction_id"] == "interaction:1"


def test_response_headers_expose_trace_bytes_and_completed_attribution() -> None:
    payload = {
        "ok": True,
        "contract_version": "rpg_turn_response_v2",
        "session_id": "session:test",
        "interaction_id": "interaction:1",
        "visible_response": {"plain_text": "Bran answers."},
        "response": "Bran answers.",
        "content": "Bran answers.",
    }

    with rpg_pipeline_trace("turn.pipeline", trace_id="trace:headers") as trace:
        with rpg_pipeline_span("turn.response_send_prepare"):
            time.sleep(0.05)
            response = build_traced_json_response(payload)
        response = finalize_rpg_trace_headers(response, trace)

    body = json.loads(response.body)
    assert body["interaction_id"] == "interaction:1"
    assert response.headers["x-omnix-rpg-trace-id"] == "trace:headers"
    assert int(response.headers["x-omnix-rpg-response-bytes"]) == len(response.body)
    assert float(response.headers["x-omnix-rpg-attribution-pct"]) >= 95.0
    assert "rpg_" in response.headers["server-timing"]


def test_required_full_path_stage_names_are_wired() -> None:
    pipeline = (_REPO_ROOT / "src" / "app" / "gateway" / "rpg_turn_pipeline.py").read_text(encoding="utf-8")
    mirror = (_REPO_ROOT / "src" / "app" / "gateway" / "rpg_turn_job_mirror.py").read_text(encoding="utf-8")
    interaction = (_REPO_ROOT / "src" / "app" / "rpg" / "session" / "interaction_timeline_hook.py").read_text(encoding="utf-8")

    for stage in (
        "turn.request_received",
        "turn.apply",
        "turn.session_persist",
        "turn.response_contract_build",
        "turn.response_send_prepare",
    ):
        assert stage in pipeline
    for stage in (
        "turn.submission_lock_wait",
        "turn.idempotency_claim",
        "turn.idempotency_job_lookup",
        "turn.foreground_record_create",
        "turn.foreground_record_finalize",
    ):
        assert stage in mirror
    for stage in (
        "turn.session_lock_wait",
        "turn.runtime_resolution",
        "turn.interaction_append",
        "turn.interaction_event_write",
        "turn.session_snapshot_write",
        "turn.interaction_log_compaction",
    ):
        assert stage in interaction
