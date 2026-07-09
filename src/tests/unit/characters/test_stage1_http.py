from __future__ import annotations

import json
from typing import Any

import pytest

from app.characters.stage1_http import HttpStage1Gateway, TTS_PCM_WEBSOCKET_PATH
from app.characters.stage1_preflight import Stage1PrepareConfig


class FakeWebsocket:
    def __init__(self, messages: list[str | bytes]) -> None:
        self.messages = list(messages)
        self.sent: list[str] = []

    def __enter__(self) -> "FakeWebsocket":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def send(self, message: str) -> None:
        self.sent.append(message)

    def recv(self, timeout: float | None = None) -> str | bytes:
        assert timeout == 12
        if not self.messages:
            raise AssertionError("test websocket exhausted")
        return self.messages.pop(0)


def test_stage1_defaults_to_launcher_gateway() -> None:
    assert Stage1PrepareConfig().base_url == "http://127.0.0.1:8000"


def test_websocket_url_uses_gateway_origin_and_scheme() -> None:
    assert (
        HttpStage1Gateway("http://127.0.0.1:8000")._websocket_url(TTS_PCM_WEBSOCKET_PATH)
        == "ws://127.0.0.1:8000/api/tts/stream/websocket"
    )
    assert (
        HttpStage1Gateway("https://example.test/omnix")._websocket_url(TTS_PCM_WEBSOCKET_PATH)
        == "wss://example.test/omnix/api/tts/stream/websocket"
    )


def test_stream_tts_measures_first_pcm_websocket_frame(monkeypatch) -> None:
    gateway = HttpStage1Gateway("http://127.0.0.1:8000", timeout_seconds=12)
    websocket = FakeWebsocket(
        [
            json.dumps(
                {
                    "type": "start",
                    "stream_id": "chat-stage1-test",
                    "sample_rate": 24_000,
                    "sample_format": "pcm_s16le",
                    "channels": 1,
                    "frame_samples": 2_400,
                }
            ),
            b"\x01\x02\x03\x04",
        ]
    )
    opened: list[str] = []

    def open_websocket(path: str) -> FakeWebsocket:
        opened.append(path)
        return websocket

    monkeypatch.setattr(gateway, "_open_websocket", open_websocket)
    elapsed_ms, frame_bytes = gateway.stream_tts(
        {
            "text": "Hello",
            "diagnostics_stream_id": "chat-stage1-test",
        }
    )

    assert opened == [TTS_PCM_WEBSOCKET_PATH]
    assert elapsed_ms >= 0
    assert frame_bytes == 4
    assert json.loads(websocket.sent[0]) == {
        "text": "Hello",
        "diagnostics_stream_id": "chat-stage1-test",
    }
    diagnostic = json.loads(websocket.sent[1])
    assert diagnostic["type"] == "diagnostic"
    assert diagnostic["stream_id"] == "chat-stage1-test"
    assert diagnostic["event"] == "playback_stopped"


def test_stream_tts_surfaces_websocket_error(monkeypatch) -> None:
    gateway = HttpStage1Gateway("http://127.0.0.1:8000", timeout_seconds=12)
    websocket = FakeWebsocket([json.dumps({"type": "error", "message": "tts_provider_unavailable"})])
    monkeypatch.setattr(gateway, "_open_websocket", lambda _path: websocket)

    with pytest.raises(RuntimeError, match="tts_provider_unavailable"):
        gateway.stream_tts({"text": "Hello"})
