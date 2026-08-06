from __future__ import annotations

import threading
from typing import Any

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app
from app.gateway.tts_live_call_startup_frame_policy import (
    TTS_LIVE_CALL_INITIAL_SILENCE_THRESHOLD,
    TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES,
    install_tts_live_call_startup_frame_policy,
)
from app.gateway.tts_stream_contract import STREAM_INITIAL_FALLBACK_THRESHOLD


class BlockingAfterInitialQwenChunkProvider:
    def __init__(self) -> None:
        self.allow_finish = threading.Event()
        self.finished = threading.Event()

    def generate_audio_stream(self, **_kwargs: Any):
        # Four Qwen codec steps currently materialize 7,680 samples. This quiet
        # speech amplitude is below the transport-neutral 1% startup threshold
        # but above the established fallback threshold. The live-call policy
        # must hand off its first frame before generation resumes.
        yield [0.006] * 7_680, 24_000, {"chunk_index": 0}
        self.allow_finish.wait(timeout=1.0)
        self.finished.set()


class EmptyJobStore:
    def list_events(self, after_id: int, limit: int):
        return []


def test_gateway_import_installs_startup_frame_policy() -> None:
    from app.gateway import tts_live_call_websocket

    assert tts_live_call_websocket.TTS_PCM_FRAME_SAMPLES == 4_800
    assert TTS_LIVE_CALL_INITIAL_SILENCE_THRESHOLD == STREAM_INITIAL_FALLBACK_THRESHOLD


def test_startup_policy_hands_off_quiet_200ms_frame_before_provider_resumes(monkeypatch) -> None:
    from app.gateway import tts_live_call_websocket

    provider = BlockingAfterInitialQwenChunkProvider()
    monkeypatch.setattr(tts_live_call_websocket, "get_tts_provider", lambda: provider)
    monkeypatch.setattr(
        tts_live_call_websocket,
        "diagnostics_log_path",
        lambda: "/tmp/tts-streaming.log",
    )
    monkeypatch.setattr(tts_live_call_websocket, "stream_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(tts_live_call_websocket, "begin_stream", lambda stream_id, **details: 1)
    monkeypatch.setattr(tts_live_call_websocket, "end_stream", lambda stream_id, **details: 0)
    monkeypatch.setattr(tts_live_call_websocket, "TTS_PCM_FRAME_SAMPLES", 2_400)

    previous = install_tts_live_call_startup_frame_policy()
    assert previous == 2_400
    assert tts_live_call_websocket.TTS_PCM_FRAME_SAMPLES == TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES

    app = create_gateway_app(job_store_factory=lambda: EmptyJobStore())
    client = TestClient(app)
    stream_id = "chat-live-startup-frame-p0"

    with client.websocket_connect("/api/tts/live-call/websocket") as websocket:
        websocket.send_json(
            {
                "type": "synthesize",
                "request_id": stream_id,
                "phrase_index": 0,
                "text": "Startup frame latency probe.",
                "speaker": "Sofia",
                "language": "English",
                "chunk_size": 4,
                "temperature": 0.6,
                "top_k": 20,
                "top_p": 0.85,
                "repetition_penalty": 1.05,
                "append_silence": False,
                "non_streaming_mode": False,
                "parity_mode": False,
                "diagnostics_stream_id": stream_id,
            }
        )

        start = websocket.receive_json()
        assert start["type"] == "start"
        assert start["frame_samples"] == 4_800
        assert len(websocket.receive_bytes()) == 9_600
        assert not provider.finished.is_set()

        provider.allow_finish.set()
        assert len(websocket.receive_bytes()) == 9_600
        assert websocket.receive_json()["type"] == "done"
        websocket.send_json({"type": "close", "reason": "finished"})
