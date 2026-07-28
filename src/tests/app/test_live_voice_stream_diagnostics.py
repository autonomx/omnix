from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app


class EmptyJobStore:
    def list_events(self, after_id: int, limit: int):
        return []


def test_live_voice_diagnostics_route_persists_correlated_batches(monkeypatch) -> None:
    from app.gateway import live_voice_diagnostics_routes

    records: list[tuple[str, str, str, dict[str, Any]]] = []
    monkeypatch.setattr(
        live_voice_diagnostics_routes,
        "live_voice_log",
        lambda trace_id, source, event, **details: records.append((trace_id, source, event, details)),
    )
    monkeypatch.setattr(
        live_voice_diagnostics_routes,
        "diagnostics_log_path",
        lambda: "/tmp/live-call-streaming.log",
    )
    app = create_gateway_app(job_store_factory=lambda: EmptyJobStore())
    client = TestClient(app)

    response = client.post(
        "/api/tts/live-call/diagnostics",
        json={
            "trace_id": "live-call:s1:test",
            "events": [
                {
                    "source": "controller",
                    "event": "phrase_queued",
                    "details": {"phrase_index": 0, "text": "Hello there."},
                },
                {
                    "source": "audio_worklet",
                    "event": "worklet_underrun",
                    "details": {
                        "buffered_samples": 0,
                        "underrun_count": 1,
                        "source": "nested_source",
                        "event": "nested_event",
                        "trace_id": "nested_trace",
                    },
                },
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "accepted": 2,
        "trace_id": "live-call:s1:test",
        "log_path": "/tmp/live-call-streaming.log",
    }
    assert records == [
        (
            "live-call:s1:test",
            "controller",
            "phrase_queued",
            {"phrase_index": 0, "text_chars": 12},
        ),
        (
            "live-call:s1:test",
            "audio_worklet",
            "worklet_underrun",
            {"buffered_samples": 0, "underrun_count": 1},
        ),
    ]


def test_live_voice_diagnostics_status_returns_log_path(monkeypatch) -> None:
    from app.gateway import live_voice_diagnostics_routes

    monkeypatch.setattr(
        live_voice_diagnostics_routes,
        "diagnostics_log_path",
        lambda: "/tmp/live-call-streaming.log",
    )
    app = create_gateway_app(job_store_factory=lambda: EmptyJobStore())
    client = TestClient(app)

    response = client.get("/api/tts/live-call/diagnostics/status")

    assert response.status_code == 200
    assert response.json() == {"ready": True, "log_path": "/tmp/live-call-streaming.log"}
