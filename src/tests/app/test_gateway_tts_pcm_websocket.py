from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app
from app.gateway.tts_streaming import TtsStreamRequest, estimate_chat_stream_max_new_tokens


class FakeTtsProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate_audio_stream(self, **kwargs: Any):
        self.calls.append(kwargs)
        yield [0.25, -0.25] * 1_200, 24_000, {"chunk_index": 0}


class EmptyJobStore:
    def list_events(self, after_id: int, limit: int):
        return []


def test_chat_stream_policy_uses_fast_mode_and_text_relative_token_budget() -> None:
    captured_text = (
        "Hello again! It's going great, thanks for asking! I feel very positive and ready to chat "
        "with you.  How is everything looking on your side right now?"
    )
    request = TtsStreamRequest.model_validate(
        {
            "text": captured_text,
            "parity_mode": True,
            "diagnostics_stream_id": "chat-captured-example",
        }
    )

    assert len(captured_text) == 149
    assert estimate_chat_stream_max_new_tokens(captured_text) == 235
    assert request.max_new_tokens == 235
    assert request.parity_mode is False


def test_non_chat_stream_preserves_explicit_runtime_settings() -> None:
    request = TtsStreamRequest.model_validate(
        {
            "text": "Diagnostic parity request",
            "max_new_tokens": 333,
            "parity_mode": True,
            "diagnostics_stream_id": "manual-diagnostic",
        }
    )

    assert request.max_new_tokens == 333
    assert request.parity_mode is True


def test_tts_pcm_websocket_emits_correlated_binary_frames_and_diagnostics(monkeypatch) -> None:
    from app.gateway import tts_pcm_websocket

    provider = FakeTtsProvider()
    logged_events: list[tuple[str, str, str, dict[str, Any]]] = []
    monkeypatch.setattr(tts_pcm_websocket, "get_tts_provider", lambda: provider)
    monkeypatch.setattr(tts_pcm_websocket, "diagnostics_log_path", lambda: "/tmp/tts-streaming.log")
    monkeypatch.setattr(
        tts_pcm_websocket,
        "stream_log",
        lambda stream_id, source, event, **details: logged_events.append(
            (stream_id, source, event, details)
        ),
    )
    monkeypatch.setattr(tts_pcm_websocket, "begin_stream", lambda stream_id, **details: 1)
    monkeypatch.setattr(tts_pcm_websocket, "end_stream", lambda stream_id, **details: 0)
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
                "diagnostics_stream_id": "chat-test-stream-1",
            }
        )

        start = websocket.receive_json()
        frame = websocket.receive_bytes()
        done = websocket.receive_json()
        websocket.send_json(
            {
                "type": "diagnostic",
                "stream_id": "chat-test-stream-1",
                "event": "playback_finished",
                "details": {"underruns": 1, "network_frames": 1},
            }
        )

    assert start == {
        "type": "start",
        "stream_id": "chat-test-stream-1",
        "sample_rate": 24_000,
        "sample_format": "pcm_s16le",
        "channels": 1,
        "frame_samples": 2_400,
        "diagnostics_log": "/tmp/tts-streaming.log",
    }
    assert len(frame) == 4_800
    assert done == {"type": "done", "stream_id": "chat-test-stream-1", "partial": False}
    assert len(provider.calls) == 1
    assert provider.calls[0]["text"] == "Hello from the websocket"
    assert provider.calls[0]["speaker"] == "Alex"
    assert provider.calls[0]["chunk_size"] == 8
    assert provider.calls[0]["non_streaming_mode"] is False
    assert provider.calls[0]["parity_mode"] is False
    assert provider.calls[0]["max_new_tokens"] == 192

    event_names = [event for _stream_id, _source, event, _details in logged_events]
    assert "request_received" in event_names
    assert "provider_resolved" in event_names
    assert "raw_chunk_received" in event_names
    assert "network_frame_queued" in event_names
    assert "network_frame_sent" in event_names
    assert "done_control_sent" in event_names
    assert "playback_finished" in event_names
    assert "route_cleanup" in event_names
