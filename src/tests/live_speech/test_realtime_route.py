from __future__ import annotations

import base64

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.live_speech.api_stub import create_live_speech_router


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(create_live_speech_router())
    return app


def test_protocol_metadata_route_exposes_realtime_contract() -> None:
    client = TestClient(_app())

    response = client.get("/api/live-speech/protocol")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["preferred_socket_path"] == "/v1/realtime"


def test_realtime_socket_accepts_text_and_creates_response() -> None:
    client = TestClient(_app())

    with client.websocket_connect("/v1/realtime") as channel:
        created = channel.receive_json()
        assert created["type"] == "session.created"

        channel.send_json({"type": "conversation.item.create", "item": {"type": "input_text", "text": "hello"}})
        assert channel.receive_json()["type"] == "conversation.item.created"

        channel.send_json({"type": "response.create"})
        seen = [channel.receive_json()["type"] for _ in range(5)]
        assert "response.created" in seen
        assert "response.output_audio.delta" in seen
        assert "response.done" in seen


def test_realtime_socket_emits_transcript_delta_for_audio_append() -> None:
    client = TestClient(_app())
    sample = (2000).to_bytes(2, byteorder="little", signed=True) * 3200
    audio = base64.b64encode(sample).decode("ascii")

    with client.websocket_connect("/v1/realtime") as channel:
        assert channel.receive_json()["type"] == "session.created"
        channel.send_json({"type": "input_audio_buffer.append", "audio": audio})
        seen = [channel.receive_json()["type"] for _ in range(2)]
        assert "input_audio_buffer.speech_started" in seen
        assert "conversation.item.input_audio_transcription.delta" in seen
