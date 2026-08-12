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
        # Four Qwen codec steps materialize 7,680 samples. This quiet speech
        # amplitude is below the transport-neutral 1% startup threshold but
        # above the established fallback threshold. The 1,920-sample live frame
        # should hand off four 80 ms frames before generation resumes.
        yield [0.006] * 7_680, 24_000, {"chunk_index": 0}
        self.allow_finish.wait(timeout=1.0)
        self.finished.set()


class BlockingAfterOneStepQwenChunkProvider:
    def __init__(self) -> None:
        self.allow_finish = threading.Event()
        self.finished = threading.Event()

    def generate_audio_stream(self, **_kwargs: Any):
        # One Qwen codec step materializes exactly one 1,920-sample live frame.
        yield [0.006] * 1_920, 24_000, {"chunk_index": 0}
        self.allow_finish.wait(timeout=1.0)
        self.finished.set()


class EmptyJobStore:
    def list_events(self, after_id: int, limit: int):
        return []


def _patch_live_tts_test_runtime(monkeypatch, provider: Any) -> None:
    from app.gateway import tts_live_call_websocket

    monkeypatch.setattr(tts_live_call_websocket, "get_tts_provider", lambda: provider)
    monkeypatch.setattr(
        tts_live_call_websocket,
        "diagnostics_log_path",
        lambda: "/tmp/tts-streaming.log",
    )
    monkeypatch.setattr(tts_live_call_websocket, "stream_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(tts_live_call_websocket, "begin_stream", lambda stream_id, **details: 1)
    monkeypatch.setattr(tts_live_call_websocket, "end_stream", lambda stream_id, **details: 0)


def test_gateway_import_installs_startup_frame_policy() -> None:
    from app.gateway import tts_live_call_websocket

    assert tts_live_call_websocket.TTS_PCM_FRAME_SAMPLES == 1_920
    assert TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES == 1_920
    assert TTS_LIVE_CALL_INITIAL_SILENCE_THRESHOLD == STREAM_INITIAL_FALLBACK_THRESHOLD


def test_gateway_composition_binds_warmed_live_tts_provider() -> None:
    from app.gateway import tts_live_call_websocket
    from app.gateway.live_voice_runtime_offload import get_cached_live_tts_provider

    assert tts_live_call_websocket.get_tts_provider is get_cached_live_tts_provider


def test_four_step_qwen_chunk_hands_off_four_80ms_frames_before_provider_resumes(monkeypatch) -> None:
    from app.gateway import tts_live_call_websocket

    provider = BlockingAfterInitialQwenChunkProvider()
    _patch_live_tts_test_runtime(monkeypatch, provider)
    monkeypatch.setattr(tts_live_call_websocket, "TTS_PCM_FRAME_SAMPLES", 2_400)

    previous = install_tts_live_call_startup_frame_policy()
    assert previous == 2_400
    assert tts_live_call_websocket.TTS_PCM_FRAME_SAMPLES == TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES

    app = create_gateway_app(job_store_factory=lambda: EmptyJobStore())
    client = TestClient(app)
    stream_id = "chat-live-startup-frame-p1"

    with client.websocket_connect("/api/tts/live-call/websocket") as websocket:
        websocket.send_json(
            {
                "type": "synthesize",
                "request_id": stream_id,
                "phrase_index": 1,
                "text": "Steady frame latency probe.",
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
        assert start["frame_samples"] == 1_920
        for _ in range(4):
            assert len(websocket.receive_bytes()) == 3_840
        assert not provider.finished.is_set()

        provider.allow_finish.set()
        assert websocket.receive_json()["type"] == "done"
        websocket.send_json({"type": "close", "reason": "finished"})


def test_one_step_qwen_chunk_hands_off_first_80ms_frame_without_waiting_for_second_chunk(monkeypatch) -> None:
    provider = BlockingAfterOneStepQwenChunkProvider()
    _patch_live_tts_test_runtime(monkeypatch, provider)

    app = create_gateway_app(job_store_factory=lambda: EmptyJobStore())
    client = TestClient(app)
    stream_id = "chat-live-one-step-startup-p0"

    with client.websocket_connect("/api/tts/live-call/websocket") as websocket:
        websocket.send_json(
            {
                "type": "synthesize",
                "request_id": stream_id,
                "output_id": "conversation-chat-test-g7-p0",
                "generation_epoch": 7,
                "phrase_index": 0,
                "text": "One-step startup latency probe.",
                "speaker": "Sofia",
                "language": "English",
                "chunk_size": 1,
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
        assert start["frame_samples"] == 1_920
        assert len(websocket.receive_bytes()) == 3_840
        assert not provider.finished.is_set()

        provider.allow_finish.set()
        assert websocket.receive_json()["type"] == "done"
        websocket.send_json({"type": "close", "reason": "finished"})
