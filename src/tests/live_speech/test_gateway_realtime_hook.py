from __future__ import annotations

from fastapi.testclient import TestClient

from app.config.runtime import RuntimeConfig
from app.composition.gateway.main import create_gateway_app


def _client(*features: str) -> TestClient:
    config = RuntimeConfig(enabled_features=features) if features else None
    return TestClient(
        create_gateway_app(runtime_config=config),
        base_url="http://127.0.0.1",
        headers={
            "Host": "127.0.0.1",
            "Origin": "http://127.0.0.1:5173",
            "X-Omnix-Client": "test",
        },
    )


def test_default_gateway_leaves_the_realtime_stub_out() -> None:
    client = _client()

    assert client.get("/api/live-speech/status").status_code == 404
    assert not any(getattr(route, "path", "") == "/v1/realtime" for route in client.app.routes)


def test_opted_in_gateway_exposes_live_speech_status_route() -> None:
    client = _client("all", "live-speech")

    response = client.get("/api/live-speech/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["socket_path"] == "/v1/realtime"
    assert payload["providers"]["stt"]


def test_opted_in_gateway_exposes_live_speech_protocol_route() -> None:
    client = _client("all", "live-speech")

    response = client.get("/api/live-speech/protocol")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["preferred_socket_path"] == "/v1/realtime"
