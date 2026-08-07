from __future__ import annotations

import threading
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.live_voice_execution_lane import (
    reset_live_voice_execution_lane_for_tests,
)
from app.gateway.live_voice_speculative_tts import (
    _accept_entry,
    _LiveLaneProviderProxy,
    _start_prefetch,
    _stream_kwargs,
    clear_speculative_tts_cache,
    register_live_voice_execution_lane_routes,
    speculative_tts_cache_snapshot,
)
from app.gateway.tts_stream_contract import TtsStreamRequest


class _BlockingProvider:
    provider_name = "test-live-tts"

    def __init__(self) -> None:
        self.calls = 0
        self.first_chunk_ready = threading.Event()
        self.allow_finish = threading.Event()

    def generate_audio_stream(self, **_kwargs: Any):
        self.calls += 1
        yield b"\x01\x00" * 4_800, 24_000, {"chunk": 0}
        self.first_chunk_ready.set()
        self.allow_finish.wait(timeout=2)
        yield b"\x02\x00" * 4_800, 24_000, {"chunk": 1}


def _request(text: str) -> TtsStreamRequest:
    return TtsStreamRequest.model_validate(
        {
            "text": text,
            "speaker": "Sofia",
            "language": "English",
            "chunk_size": 4,
            "temperature": 0.6,
            "top_k": 20,
            "top_p": 0.85,
            "repetition_penalty": 1.05,
            "append_silence": False,
            "parity_mode": False,
            "diagnostics_stream_id": "chat-live-lane-test",
        }
    )


def _reset() -> None:
    clear_speculative_tts_cache()
    reset_live_voice_execution_lane_for_tests()


def test_accepted_prefetch_is_promoted_and_replayed_without_second_generation() -> None:
    _reset()
    provider = _BlockingProvider()
    request = _request("This is already being synthesized.")

    try:
        _start_prefetch("spec-live-lane", request, provider, "shared")
        assert provider.first_chunk_ready.wait(timeout=1)
        entry = _accept_entry("spec-live-lane")
        assert entry.promotion_event.is_set()

        replay = _LiveLaneProviderProxy(provider, "shared").generate_audio_stream(
            text=request.text,
            speaker=request.speaker,
            language=request.language or "en",
            **_stream_kwargs(request, provider),
        )
        first_pcm, first_rate, timing = next(replay)
        assert first_pcm == b"\x01\x00" * 4_800
        assert first_rate == 24_000
        assert timing["speculative_tts_cache"] is True
        assert timing["live_execution_lane"] == "shared"
        assert provider.calls == 1

        provider.allow_finish.set()
        assert next(replay)[0] == b"\x02\x00" * 4_800
        assert provider.calls == 1
        assert speculative_tts_cache_snapshot()[0]["claimed"] is True
    finally:
        provider.allow_finish.set()
        _reset()


def test_execution_lane_status_reports_dedicated_configuration(monkeypatch) -> None:
    _reset()
    monkeypatch.setenv("OMNIX_LIVE_VOICE_EXECUTION_MODE", "dedicated")
    monkeypatch.setenv("OMNIX_LIVE_VOICE_PROVIDER_ID", "lmstudio")
    monkeypatch.setenv("OMNIX_LIVE_VOICE_MODEL_ID", "qwen-live-fast")
    monkeypatch.setenv("OMNIX_LIVE_TTS_DEDICATED", "true")
    monkeypatch.setenv("OMNIX_LIVE_TTS_PROVIDER_NAME", "faster-qwen3-tts")
    app = FastAPI()
    register_live_voice_execution_lane_routes(app)

    response = TestClient(app).get("/api/live/voice/execution-lane")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "mode": "dedicated",
        "provider_id": "lmstudio",
        "model_id": "qwen-live-fast",
        "dedicated_chat_enabled": True,
        "dedicated_tts": True,
        "tts_provider_name": "faster-qwen3-tts",
        "scheduler": {
            "active_priority": None,
            "active_cancelled": False,
            "waiting": [],
        },
    }
