from __future__ import annotations

import threading
from typing import Any

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app


class BlockingAfterFirstChunkTtsProvider:
    def __init__(self) -> None:
        self.allow_finish = threading.Event()
        self.finished = threading.Event()

    def generate_audio_stream(self, **_kwargs: Any):
        yield [0.25] * 2_400, 24_000, {"chunk_index": 0}
        self.allow_finish.wait(timeout=1.0)
        self.finished.set()


class EmptyJobStore:
    def list_events(self, after_id: int, limit: int):
        return []


def test_first_pcm_frame_is_sent_before_provider_finishes(monkeypatch) -> None:
    from app.gateway import tts_live_call_websocket

    provider = BlockingAfterFirstChunkTtsProvider()
    logged_events: list[tuple[str, str, str, dict[str, Any]]] = []
    monkeypatch.setattr(tts_live_call_websocket, "get_tts_provider", lambda: provider)
    monkeypatch.setattr(
        tts_live_call_websocket,
        "diagnostics_log_path",
        lambda: "/tmp/tts-streaming.log",
    )
    monkeypatch.setattr(
        tts_live_call_websocket,
        "stream_log",
        lambda stream_id, source, event, **details: logged_events.append(
            (stream_id, source, event, details)
        ),
    )
    monkeypatch.setattr(tts_live_call_websocket, "begin_stream", lambda stream_id, **details: 1)
    monkeypatch.setattr(tts_live_call_websocket, "end_stream", lambda stream_id, **details: 0)

    app = create_gateway_app(job_store_factory=lambda: EmptyJobStore())
    client = TestClient(app)
    stream_id = "chat-live-latency-p0"

    with client.websocket_connect("/api/tts/live-call/websocket") as websocket:
        websocket.send_json(
            {
                "type": "synthesize",
                "request_id": stream_id,
                "phrase_index": 0,
                "text": "Latency probe.",
                "speaker": "Maya",
                "language": "English",
                "chunk_size": 8,
                "temperature": 0.6,
                "top_k": 20,
                "top_p": 0.85,
                "repetition_penalty": 1.0,
                "append_silence": False,
                "non_streaming_mode": False,
                "parity_mode": True,
                "diagnostics_stream_id": stream_id,
            }
        )

        assert websocket.receive_json()["type"] == "start"
        assert len(websocket.receive_bytes()) == 4_800
        assert not provider.finished.is_set()

        provider.allow_finish.set()
        assert websocket.receive_json()["type"] == "done"
        websocket.send_json({"type": "close", "reason": "finished"})

    event_names = [event for _stream_id, _source, event, _details in logged_events]
    assert "first_raw_chunk_ready" in event_names
    assert "first_start_control_sent" in event_names
    assert "first_pcm_frame_sent" in event_names
    assert "first_frame_handoff_completed" in event_names

    handoff = next(
        details
        for _stream_id, _source, event, details in logged_events
        if event == "first_frame_handoff_completed"
    )
    assert handoff["acknowledged"] is True
    assert handoff["wait_ms"] >= 0

    first_frame = next(
        details
        for _stream_id, _source, event, details in logged_events
        if event == "first_pcm_frame_sent"
    )
    assert first_frame["frame_queue_wait_ms"] is not None
    assert first_frame["frame_queue_wait_ms"] >= 0
