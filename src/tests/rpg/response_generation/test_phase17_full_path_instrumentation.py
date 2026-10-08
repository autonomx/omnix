from __future__ import annotations

import json
from pathlib import Path

from app.apps.rpg.foundation.performance_trace import (
    attach_rpg_result_timing,
    build_traced_json_response,
    rpg_pipeline_span,
    rpg_pipeline_trace,
)
from app.apps.rpg.foundation.response_trace_headers import finalize_rpg_trace_headers

_REPO_ROOT = Path(__file__).resolve().parents[4]


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


def test_response_headers_expose_trace_id_and_response_bytes() -> None:
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
            response = build_traced_json_response(payload)
        response = finalize_rpg_trace_headers(response, trace)

    body = json.loads(response.body)
    assert body["interaction_id"] == "interaction:1"
    assert response.headers["x-omnix-rpg-trace-id"] == "trace:headers"
    assert int(response.headers["x-omnix-rpg-response-bytes"]) == len(response.body)
    assert "rpg_" in response.headers["server-timing"]
