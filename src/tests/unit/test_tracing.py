"""Optional OpenTelemetry tracing (WP-10.4)."""
from __future__ import annotations

import io
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytest.importorskip("opentelemetry.sdk")
import httpcore  # noqa: E402
import httpx  # noqa: E402
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402

from app.platform.live_speech.metrics import LiveSpeechMetrics  # noqa: E402
from app.observability import tracing  # noqa: E402
from app.observability.logging import RequestContextMiddleware, configure_logging  # noqa: E402
from app.apps.rpg.foundation.performance_trace import rpg_pipeline_span, rpg_pipeline_trace  # noqa: E402

logger = logging.getLogger("omnix.tests.tracing")


class _ModelServicePool:
    """Stands in for the connection pool under httpx's real transport (which the instrumentation wraps)."""

    def __init__(self) -> None:
        self.requests: list[httpcore.Request] = []

    def handle_request(self, request: httpcore.Request) -> httpcore.Response:
        self.requests.append(request)
        return httpcore.Response(200, headers=[(b"content-type", b"application/json")], content=b"{}")

    def close(self) -> None:
        pass

    def __enter__(self) -> _ModelServicePool:
        return self

    def __exit__(self, *exc_info: object) -> None:
        pass


@pytest.fixture
def exporter():
    spans = InMemorySpanExporter()
    assert tracing.configure_tracing(service_name="omnix-test", exporter=spans)
    try:
        yield spans
    finally:
        tracing.shutdown_tracing()


@pytest.fixture
def log_lines():
    stream = io.StringIO()
    handler = configure_logging(log_format="json", level="INFO", stream=stream)
    try:
        yield lambda: [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    finally:
        logging.getLogger().removeHandler(handler)


def _turn_app(pool: _ModelServicePool) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.post("/turn")
    def turn() -> dict:
        with rpg_pipeline_trace("turn.pipeline", session_id="session-1"):
            with rpg_pipeline_span("turn.provider_call") as stage:
                transport = httpx.HTTPTransport()
                transport._pool = pool  # type: ignore[assignment]
                with httpx.Client(transport=transport) as client:
                    client.post("http://model-service.test/v1/chat", json={})
                stage["response_bytes"] = 2
                stage["prompt"] = {"nested": "left out"}
            with tracing.span("job.execute", job_type="chat_generation"):
                logger.info("turn finished")
        return {"ok": True}

    tracing.instrument_app(app)
    return app


def _tree(spans) -> dict[str, str | None]:
    by_id = {span.context.span_id: span for span in spans}
    return {
        span.name: (by_id[span.parent.span_id].name if span.parent and span.parent.span_id in by_id else None)
        for span in spans
    }


def test_one_request_produces_the_expected_span_tree(exporter, log_lines):
    pool = _ModelServicePool()
    with TestClient(_turn_app(pool)) as client:
        response = client.post("/turn", headers={"X-Request-ID": "trace-test-request-0001"})
    assert response.status_code == 200

    spans = exporter.get_finished_spans()
    tree = _tree(spans)
    assert tree["POST /turn"] is None
    assert tree["rpg.turn.pipeline"] == "POST /turn"
    assert tree["rpg.turn.provider_call"] == "rpg.turn.pipeline"
    assert tree["POST"] == "rpg.turn.provider_call"  # the httpx client span
    assert tree["job.execute"] == "rpg.turn.pipeline"
    assert len({span.context.trace_id for span in spans}) == 1

    by_name = {span.name: span for span in spans}
    assert by_name["POST /turn"].attributes["omnix.request_id"] == "trace-test-request-0001"
    stage = by_name["rpg.turn.provider_call"].attributes
    assert stage["omnix.response_bytes"] == 2
    assert "omnix.prompt" not in stage
    assert by_name["rpg.turn.pipeline"].attributes["omnix.session_id"] == "session-1"

    # The outbound call carries the trace to the model service.
    trace_id = format(by_name["POST /turn"].context.trace_id, "032x")
    traceparent = dict(pool.requests[0].headers)[b"traceparent"].decode()
    assert traceparent.split("-")[1] == trace_id

    # Log lines inside the request name the trace.
    line = next(item for item in log_lines() if item["message"] == "turn finished")
    assert line["trace_id"] == trace_id
    assert line["request_id"] == "trace-test-request-0001"


def test_psycopg_is_instrumented_while_tracing_is_on(exporter):
    assert PsycopgInstrumentor().is_instrumented_by_opentelemetry
    tracing.shutdown_tracing()
    assert not PsycopgInstrumentor().is_instrumented_by_opentelemetry


def test_live_speech_stages_become_spans(exporter):
    metrics = LiveSpeechMetrics()
    metrics.speech_started_ms = 1_000
    metrics.mark("speech_stopped")
    metrics.speech_stopped_ms = 2_000
    metrics.mark("final_transcript")
    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert "live_speech.utterance" in spans
    transcript = spans["live_speech.transcript"]
    assert transcript.start_time == 2_000 * 1_000_000
    assert transcript.end_time >= transcript.start_time


def test_gateway_middleware_installs_server_spans(exporter):
    from app.composition.gateway.app_factory import _install_request_middleware

    gateway = FastAPI()

    @gateway.get("/api/ping")
    def ping() -> dict:
        return {"ok": True}

    _install_request_middleware(gateway, None)
    with TestClient(gateway, base_url="http://127.0.0.1") as client:
        response = client.get("/api/ping")
    server = [span for span in exporter.get_finished_spans() if span.name == "GET /api/ping"]
    assert len(server) == 1
    assert server[0].attributes["omnix.request_id"] == response.headers["x-request-id"]


def test_tracing_is_off_by_default(monkeypatch):
    monkeypatch.delenv("OMNIX_OTEL_ENABLED", raising=False)
    assert not tracing.configure_tracing(service_name="omnix-test")
    assert not tracing.tracing_active()
    with tracing.span("job.execute") as current:
        assert current is None
    assert tracing.current_trace_id() is None
    tracing.record_span("live_speech.transcript", start_ms=1, end_ms=2)
    tracing.set_span_attributes(agent_run_id="run-1")
