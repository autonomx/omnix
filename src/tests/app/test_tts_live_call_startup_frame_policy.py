from __future__ import annotations

import threading
from typing import Any

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app
from app.gateway.tts_live_call_startup_frame_policy import (
    TTS_LIVE_CALL_FIRST_CHUNK_MAX_INITIAL_SILENCE_MS,
    TTS_LIVE_CALL_INITIAL_SILENCE_THRESHOLD,
    TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES,
    install_tts_live_call_startup_frame_policy,
    live_call_max_initial_silence_ms_for_first_chunk,
)
from app.gateway.tts_stream_contract import (
    STREAM_INITIAL_FALLBACK_THRESHOLD,
    STREAM_MAX_INITIAL_SILENCE_MS,
)


class BlockingAfterInitialQwenChunkProvider:
    def __init__(self) -> None:
        self.allow_finish = threading.Event()
        self.finished = threading.Event()

    def generate_audio_stream(self, **_kwargs: Any):
        # Four Qwen codec steps materialize two 3,840-sample transport frames.
        yield [0.006] * 7_680, 24_000, {"chunk_index": 0}
        self.allow_finish.wait(timeout=1.0)
        self.finished.set()


class BlockingAfterTwoStepQwenChunkProvider:
    def __init__(self) -> None:
        self.allow_finish = threading.Event()
        self.finished = threading.Event()

    def generate_audio_stream(self, **_kwargs: Any):
        # Two Qwen codec steps fill one 3,840-sample transport frame.
        yield [0.006] * 3_840, 24_000, {"chunk_index": 0}
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

    assert tts_live_call_websocket.TTS_PCM_FRAME_SAMPLES == 3_840
    assert TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES == 3_840
    assert TTS_LIVE_CALL_FIRST_CHUNK_MAX_INITIAL_SILENCE_MS == 160.0
    assert TTS_LIVE_CALL_INITIAL_SILENCE_THRESHOLD == STREAM_INITIAL_FALLBACK_THRESHOLD


def test_two_step_chunk_gets_first_chunk_onset_window() -> None:
    pcm = b"\x01\x00" * 3_840

    assert live_call_max_initial_silence_ms_for_first_chunk(pcm, 24_000) == 160.0
    assert live_call_max_initial_silence_ms_for_first_chunk(pcm, 22_050) == (
        STREAM_MAX_INITIAL_SILENCE_MS
    )


def test_gateway_composition_binds_warmed_live_tts_provider() -> None:
    from app.gateway import tts_live_call_websocket
    from app.gateway.live_voice_runtime_offload import get_cached_live_tts_provider

    assert tts_live_call_websocket.get_tts_provider is get_cached_live_tts_provider


def test_four_step_qwen_chunk_hands_off_two_160ms_frames_before_provider_resumes(monkeypatch) -> None:
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
        assert start["frame_samples"] == 3_840
        assert len(websocket.receive_bytes()) == 7_680
        assert len(websocket.receive_bytes()) == 7_680
        assert not provider.finished.is_set()

        provider.allow_finish.set()
        assert websocket.receive_json()["type"] == "done"
        websocket.send_json({"type": "close", "reason": "finished"})


def test_two_step_qwen_chunk_hands_off_first_160ms_frame_before_provider_resumes(monkeypatch) -> None:
    provider = BlockingAfterTwoStepQwenChunkProvider()
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
                "text": "Two-step startup latency probe.",
                "speaker": "Sofia",
                "language": "English",
                "chunk_size": 2,
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
        assert start["frame_samples"] == 3_840
        assert len(websocket.receive_bytes()) == 7_680
        assert not provider.finished.is_set()

        provider.allow_finish.set()
        assert websocket.receive_json()["type"] == "done"
        websocket.send_json({"type": "close", "reason": "finished"})
