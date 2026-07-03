from __future__ import annotations

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app


def test_default_gateway_exposes_live_speech_status_route() -> None:
    client = TestClient(create_gateway_app())

    response = client.get("/api/live-speech/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["socket_path"] == "/v1/realtime"
    assert payload["providers"]["stt"]


def test_default_gateway_exposes_live_speech_protocol_route() -> None:
    client = TestClient(create_gateway_app())

    response = client.get("/api/live-speech/protocol")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["preferred_socket_path"] == "/v1/realtime"
