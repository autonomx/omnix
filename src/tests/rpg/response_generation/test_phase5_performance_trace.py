from __future__ import annotations

import json
from typing import Any

from app.rpg import performance_trace
from app.rpg.performance_trace import (
    build_traced_json_response,
    current_rpg_pipeline_trace,
    rpg_pipeline_span,
    rpg_pipeline_trace,
)


def test_pipeline_trace_records_child_spans_and_serialized_response(monkeypatch: Any) -> None:
    emitted: list[dict[str, Any]] = []

    def fake_log(event: str, **kwargs: Any) -> dict[str, Any]:
        emitted.append({"event": event, **kwargs})
        return emitted[-1]

    monkeypatch.setattr(performance_trace, "log_rpg_event", fake_log)
    monkeypatch.setenv("OMNIX_RPG_SLOW_SPAN_MS", "0")

    with rpg_pipeline_trace(
        "turn.pipeline",
        session_id="session:bran",
        trace_id="trace:one",
        fields={"command_chars": 12},
    ) as trace:
        assert current_rpg_pipeline_trace() is trace
        with rpg_pipeline_span("turn.request_received") as span:
            span["content_length"] = "42"
        with rpg_pipeline_span("turn.response_contract_build") as span:
            span["contract_version"] = "rpg_turn_response_v2"
        response = build_traced_json_response(
            {
                "ok": True,
                "contract_version": "rpg_turn_response_v2",
                "interaction_id": "interaction:1",
            }
        )

    assert current_rpg_pipeline_trace() is None
    assert response.media_type == "application/json"
    assert json.loads(response.body) == {
        "ok": True,
        "contract_version": "rpg_turn_response_v2",
        "interaction_id": "interaction:1",
    }
    assert int(response.headers["content-length"]) == len(response.body)
    assert [span["name"] for span in trace.spans] == [
        "turn.request_received",
        "turn.response_contract_build",
        "turn.response_json_encode",
    ]
    assert trace.fields["response_bytes"] == len(response.body)
    assert emitted[0]["event"] == "turn.pipeline.started"
    assert emitted[-1]["event"] == "turn.pipeline.completed"
    completed_spans = [event for event in emitted if event["event"].endswith(".completed")][:-1]
    assert completed_spans
    assert all(event["level"] == "warning" for event in completed_spans)


def test_pipeline_trace_records_failed_span(monkeypatch: Any) -> None:
    emitted: list[dict[str, Any]] = []

    def fake_log(event: str, **kwargs: Any) -> dict[str, Any]:
        emitted.append({"event": event, **kwargs})
        return emitted[-1]

    monkeypatch.setattr(performance_trace, "log_rpg_event", fake_log)

    try:
        with rpg_pipeline_trace("turn.pipeline", trace_id="trace:failure") as trace:
            with rpg_pipeline_span("turn.apply"):
                raise RuntimeError("boom")
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected the span exception to propagate")

    assert trace.spans[-1]["name"] == "turn.apply"
    assert trace.spans[-1]["failed"] is True
    assert any(event["event"] == "turn.apply.failed" for event in emitted)
    assert emitted[-1]["event"] == "turn.pipeline.failed"


def test_pipeline_summary_reports_unattributed_time(monkeypatch: Any) -> None:
    monkeypatch.setattr(performance_trace, "log_rpg_event", lambda *args, **kwargs: {})

    with rpg_pipeline_trace("turn.pipeline", trace_id="trace:summary") as trace:
        with rpg_pipeline_span("turn.apply"):
            pass
        summary = trace.summary()

    assert summary["span_count"] == 1
    assert summary["total_ms"] >= summary["child_duration_ms"]
    assert summary["unattributed_ms"] >= 0
