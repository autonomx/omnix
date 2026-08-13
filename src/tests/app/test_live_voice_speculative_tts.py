from __future__ import annotations

import threading
import time
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway import live_voice_speculative_tts as speculative_tts
from app.gateway.live_voice_execution_lane import (
    reset_live_voice_execution_lane_for_tests,
)
from app.gateway.live_voice_speculative_tts import (
    _accept_entry,
    _claim_entry,
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
    # Match Faster Qwen3 TTS: speculation must still run through the serialized
    # priority lane even though the provider cannot generate concurrently.
    supports_concurrent_generation = False

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


class _ColdStartProvider:
    provider_name = "test-live-tts"
    supports_concurrent_generation = False

    def __init__(self) -> None:
        self.calls = 0
        self.first_call_started = threading.Event()
        self.allow_first_call_yield = threading.Event()
        self.chunk_sizes: list[int | None] = []

    def generate_audio_stream(self, **kwargs: Any):
        self.calls += 1
        call_number = self.calls
        self.chunk_sizes.append(kwargs.get("chunk_size"))
        if call_number == 1:
            self.first_call_started.set()
            self.allow_first_call_yield.wait(timeout=2)
        yield b"\x03\x00" * 4_800, 24_000, {"chunk": 0, "call": call_number}


class _ThreeChunkProvider:
    provider_name = "test-live-tts"
    supports_concurrent_generation = False

    def __init__(self) -> None:
        self.calls = 0
        self.first_chunk_ready = threading.Event()
        self.allow_second_chunk = threading.Event()
        self.allow_third_chunk = threading.Event()

    def generate_audio_stream(self, **_kwargs: Any):
        self.calls += 1
        yield b"\x01\x00" * 3_840, 24_000, {"chunk": 0}
        self.first_chunk_ready.set()
        self.allow_second_chunk.wait(timeout=2)
        yield b"\x02\x00" * 3_840, 24_000, {"chunk": 1}
        self.allow_third_chunk.wait(timeout=2)
        yield b"\x03\x00" * 3_840, 24_000, {"chunk": 2}


class _ShortChunkProvider:
    provider_name = "test-live-tts"
    supports_concurrent_generation = False

    def __init__(self) -> None:
        self.calls = 0
        self.first_chunk_ready = threading.Event()
        self.allow_second_chunk = threading.Event()

    def generate_audio_stream(self, **_kwargs: Any):
        self.calls += 1
        yield b"\x01\x00" * 1_920, 24_000, {"chunk": 0}
        self.first_chunk_ready.set()
        self.allow_second_chunk.wait(timeout=2)
        yield b"\x02\x00" * 1_920, 24_000, {"chunk": 1}


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

        # Hidden speculation may use a different provider chunk cadence than the
        # accepted first phrase. That transport choice must not invalidate PCM
        # reuse or trigger a duplicate authoritative provider generation.
        accepted_kwargs = _stream_kwargs(request, provider)
        accepted_kwargs["chunk_size"] = 2
        replay = _LiveLaneProviderProxy(provider, "shared").generate_audio_stream(
            text=request.text,
            speaker=request.speaker,
            language=request.language or "en",
            **accepted_kwargs,
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


def test_accepted_prefetch_without_pcm_restarts_authoritative_stream(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_LIVE_TTS_SPECULATIVE_CHUNK_STEPS", raising=False)
    monkeypatch.setattr(speculative_tts, "_COLD_CLAIM_WAIT_SECONDS", 0.01)
    _reset()
    provider = _ColdStartProvider()
    request = _request("Cold speculation must not become audible.")

    try:
        entry = _start_prefetch("spec-cold", request, provider, "shared")
        assert provider.first_call_started.wait(timeout=1)
        _accept_entry("spec-cold")

        accepted_kwargs = _stream_kwargs(request, provider)
        accepted_kwargs["chunk_size"] = 2
        claim = _claim_entry(
            request.text,
            request.speaker,
            request.language or "en",
            accepted_kwargs,
        )

        assert claim is None
        with entry.condition:
            assert entry.cancelled is True
            assert entry.chunks == []
        assert speculative_tts_cache_snapshot() == []

        # Let the hidden one-step decoder reach its next cancellation boundary,
        # then verify the authoritative request starts fresh at its two-step
        # cadence rather than inheriting the cold speculative stream.
        provider.allow_first_call_yield.set()
        with entry.condition:
            deadline = time.monotonic() + 1.0
            while not entry.completed and time.monotonic() < deadline:
                entry.condition.wait(timeout=0.025)
            assert entry.completed

        replay = _LiveLaneProviderProxy(provider, "shared").generate_audio_stream(
            text=request.text,
            speaker=request.speaker,
            language=request.language or "en",
            **accepted_kwargs,
        )
        first_pcm, first_rate, timing = next(replay)

        assert first_pcm == b"\x03\x00" * 4_800
        assert first_rate == 24_000
        assert "speculative_tts_cache" not in timing
        assert provider.calls == 2
        assert provider.chunk_sizes == [1, 2]
    finally:
        provider.allow_first_call_yield.set()
        _reset()


def test_accepted_cold_prefetch_waits_for_imminent_pcm_instead_of_restarting() -> None:
    _reset()
    provider = _ColdStartProvider()
    request = _request("Imminent speculative audio should be promoted.")

    try:
        entry = _start_prefetch("spec-cold-promoted", request, provider, "shared")
        assert provider.first_call_started.wait(timeout=1)
        _accept_entry("spec-cold-promoted")
        threading.Timer(0.02, provider.allow_first_call_yield.set).start()

        accepted_kwargs = _stream_kwargs(request, provider)
        accepted_kwargs["chunk_size"] = 2
        claim = _claim_entry(
            request.text,
            request.speaker,
            request.language or "en",
            accepted_kwargs,
        )

        assert claim is not None
        assert claim.entry is entry
        assert claim.remainder_text == ""
        with entry.condition:
            assert entry.cancelled is False
            assert entry.chunks
        assert provider.calls == 1
        assert provider.chunk_sizes == [1]
    finally:
        provider.allow_first_call_yield.set()
        _reset()


def test_accepted_prefetch_with_short_first_chunk_waits_for_160ms_runway() -> None:
    _reset()
    provider = _ShortChunkProvider()
    request = _request("An 80 ms chunk is not enough playback runway.")

    try:
        entry = _start_prefetch("spec-short-chunk", request, provider, "shared")
        assert provider.first_chunk_ready.wait(timeout=1)
        _accept_entry("spec-short-chunk")
        threading.Timer(0.02, provider.allow_second_chunk.set).start()

        accepted_kwargs = _stream_kwargs(request, provider)
        accepted_kwargs["chunk_size"] = 2
        claim = _claim_entry(
            request.text,
            request.speaker,
            request.language or "en",
            accepted_kwargs,
        )

        assert claim is not None
        assert claim.entry is entry
        with entry.condition:
            assert len(entry.chunks) == 2
        assert provider.calls == 1
    finally:
        provider.allow_second_chunk.set()
        _reset()


def test_accepted_prefetch_promotes_one_complete_160ms_startup_frame() -> None:
    _reset()
    provider = _ThreeChunkProvider()
    request = _request("One complete startup frame is ready to play.")

    try:
        entry = _start_prefetch("spec-three-chunks", request, provider, "shared")
        assert provider.first_chunk_ready.wait(timeout=1)
        _accept_entry("spec-three-chunks")

        accepted_kwargs = _stream_kwargs(request, provider)
        accepted_kwargs["chunk_size"] = 2
        claim = _claim_entry(
            request.text,
            request.speaker,
            request.language or "en",
            accepted_kwargs,
        )

        assert claim is not None
        assert claim.entry is entry
        with entry.condition:
            assert len(entry.chunks) == 1
        assert provider.allow_second_chunk.is_set() is False
        assert provider.calls == 1
    finally:
        provider.allow_second_chunk.set()
        provider.allow_third_chunk.set()
        _reset()


def test_stale_accepted_prefetch_cannot_be_claimed_by_a_later_turn() -> None:
    _reset()
    provider = _BlockingProvider()
    request = _request("A phrase that might appear again.")

    try:
        _start_prefetch("spec-stale", request, provider, "shared")
        assert provider.first_chunk_ready.wait(timeout=1)
        entry = _accept_entry("spec-stale")
        provider.allow_finish.set()
        with entry.condition:
            deadline = time.monotonic() + 1.0
            while not entry.completed and time.monotonic() < deadline:
                entry.condition.wait(timeout=0.025)
            assert entry.completed
            assert entry.accepted_at is not None
            entry.accepted_at -= speculative_tts._ACCEPTED_UNCLAIMED_TTL_SECONDS + 0.1

        replay = _LiveLaneProviderProxy(provider, "shared").generate_audio_stream(
            text=request.text,
            speaker=request.speaker,
            language=request.language or "en",
            **_stream_kwargs(request, provider),
        )
        first_pcm, first_rate, timing = next(replay)

        assert first_pcm == b"\x01\x00" * 4_800
        assert first_rate == 24_000
        assert "speculative_tts_cache" not in timing
        assert provider.calls == 2
        assert speculative_tts_cache_snapshot() == []
    finally:
        provider.allow_finish.set()
        _reset()


def test_prefetch_route_uses_warmed_provider_and_reports_hot_path_timing(monkeypatch) -> None:
    _reset()
    provider = _BlockingProvider()
    lookup_calls = 0
    logs: list[tuple[str, dict[str, Any]]] = []

    def cached_provider() -> _BlockingProvider:
        nonlocal lookup_calls
        lookup_calls += 1
        return provider

    monkeypatch.setattr(speculative_tts, "get_cached_live_tts_provider", cached_provider)
    monkeypatch.setattr(
        speculative_tts,
        "stream_log",
        lambda _stream_id, _source, event, **fields: logs.append((event, fields)),
    )
    app = FastAPI()
    register_live_voice_execution_lane_routes(app)

    try:
        response = TestClient(app).post(
            "/api/live/speculation/tts-prefetch",
            json={
                "generation_id": "spec-route-hot-path",
                "request": _request("Prefetch this immediately.").model_dump(mode="json"),
            },
        )

        assert response.status_code == 200
        assert response.json()["execution_lane"] == "shared"
        assert lookup_calls == 1
        started = next(
            fields
            for event, fields in logs
            if event == "speculative_tts_prefetch_started"
        )
        assert started["cached_provider_lookup_ms"] >= 0
        assert started["lane_provider_resolution_ms"] >= 0
        assert started["route_to_prefetch_thread_ms"] >= 0
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
