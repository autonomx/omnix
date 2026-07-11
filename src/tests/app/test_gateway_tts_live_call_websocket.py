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


def _request(text: str, phrase_index: int) -> dict[str, Any]:
    stream_id = f"chat-live-test-p{phrase_index}"
    return {
        "type": "synthesize",
        "request_id": stream_id,
        "phrase_index": phrase_index,
        "text": text,
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
        "diagnostics_stream_id": stream_id,
    }


def test_live_call_websocket_reuses_one_connection_for_multiple_phrases(monkeypatch) -> None:
    from app.gateway import tts_live_call_websocket

    provider = FakeTtsProvider()
    logged_events: list[tuple[str, str, str, dict[str, Any]]] = []
    monkeypatch.setattr(tts_live_call_websocket, "get_tts_provider", lambda: provider)
    monkeypatch.setattr(tts_live_call_websocket, "diagnostics_log_path", lambda: "/tmp/tts-streaming.log")
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

    with client.websocket_connect("/api/tts/live-call/websocket") as websocket:
        websocket.send_json(_request("First persistent phrase.", 0))
        first_start = websocket.receive_json()
        first_frame = websocket.receive_bytes()
        first_done = websocket.receive_json()
        websocket.send_json(
            {
                "type": "diagnostic",
                "stream_id": "chat-live-test-p0",
                "event": "playback_finished",
                "details": {"phrase_index": 0, "frames": 1},
            }
        )

        websocket.send_json(_request("Second persistent phrase.", 1))
        second_start = websocket.receive_json()
        second_frame = websocket.receive_bytes()
        second_done = websocket.receive_json()
        websocket.send_json({"type": "close", "reason": "finished"})

    assert first_start == {
        "type": "start",
        "stream_id": "chat-live-test-p0",
        "phrase_index": 0,
        "sample_rate": 24_000,
        "sample_format": "pcm_s16le",
        "channels": 1,
        "frame_samples": 2_400,
        "diagnostics_log": "/tmp/tts-streaming.log",
    }
    assert second_start == {
        "type": "start",
        "stream_id": "chat-live-test-p1",
        "phrase_index": 1,
        "sample_rate": 24_000,
        "sample_format": "pcm_s16le",
        "channels": 1,
        "frame_samples": 2_400,
        "diagnostics_log": "/tmp/tts-streaming.log",
    }
    assert len(first_frame) == 4_800
    assert len(second_frame) == 4_800
    assert first_done == {
        "type": "done",
        "stream_id": "chat-live-test-p0",
        "phrase_index": 0,
        "partial": False,
    }
    assert second_done == {
        "type": "done",
        "stream_id": "chat-live-test-p1",
        "phrase_index": 1,
        "partial": False,
    }

    assert [call["text"] for call in provider.calls] == [
        "First persistent phrase.",
        "Second persistent phrase.",
    ]
    assert all(call["parity_mode"] is False for call in provider.calls)
    assert all(call["repetition_penalty"] == 1.05 for call in provider.calls)
    assert all(call["max_new_tokens"] == 96 for call in provider.calls)

    request_events = [
        (stream_id, details.get("phrase_index"))
        for stream_id, _source, event, details in logged_events
        if event == "request_received"
    ]
    assert request_events == [("chat-live-test-p0", 0), ("chat-live-test-p1", 1)]
    event_names = [event for _stream_id, _source, event, _details in logged_events]
    assert event_names.count("done_control_sent") == 2
    assert event_names.count("phrase_route_cleanup") == 2
    assert "playback_finished" in event_names
