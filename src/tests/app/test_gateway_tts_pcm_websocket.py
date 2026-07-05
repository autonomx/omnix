from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app


class FakeTtsProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate_audio_stream(self, **kwargs: Any):
        self.calls.append(kwargs)
        yield [0.25, -0.25] * 1_200, 24_000, {"chunk_index": 0}


class EmptyJobStore:
    def list_events(self, after_id: int, limit: int):
        return []


def test_tts_pcm_websocket_emits_binary_100ms_frames(monkeypatch) -> None:
    from app.gateway import tts_pcm_websocket

    provider = FakeTtsProvider()
    monkeypatch.setattr(tts_pcm_websocket, "get_tts_provider", lambda: provider)
    app = create_gateway_app(job_store_factory=lambda: EmptyJobStore())
    client = TestClient(app)

    with client.websocket_connect("/api/tts/stream/websocket") as websocket:
        websocket.send_json(
            {
                "text": "Hello from the websocket",
                "speaker": "Alex",
                "language": "English",
                "chunk_size": 8,
                "temperature": 0.6,
                "top_k": 20,
                "top_p": 0.85,
                "repetition_penalty": 1.0,
                "append_silence": False,
                "non_streaming_mode": False,
                "parity_mode": True,
            }
        )

        start = websocket.receive_json()
        frame = websocket.receive_bytes()
        done = websocket.receive_json()

    assert start == {
        "type": "start",
        "sample_rate": 24_000,
        "sample_format": "pcm_s16le",
        "channels": 1,
        "frame_samples": 2_400,
    }
    assert len(frame) == 4_800
    assert done == {"type": "done"}
    assert len(provider.calls) == 1
    assert provider.calls[0]["text"] == "Hello from the websocket"
    assert provider.calls[0]["speaker"] == "Alex"
    assert provider.calls[0]["chunk_size"] == 8
    assert provider.calls[0]["non_streaming_mode"] is False
    assert "max_new_tokens" not in provider.calls[0]
