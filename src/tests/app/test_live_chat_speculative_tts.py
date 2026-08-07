from __future__ import annotations

import threading
from typing import Any

from app.gateway.live_chat_speculative_tts import (
    _PROVIDER_GENERATION_LOCK,
    _accept_entry,
    _cancel_entry,
    _PrefetchingProviderProxy,
    _start_prefetch,
    _stream_kwargs,
    clear_speculative_tts_cache,
    speculative_tts_cache_snapshot,
)
from app.gateway.tts_stream_contract import TtsStreamRequest


class BlockingTwoChunkProvider:
    provider_name = "test_qwen"

    def __init__(self) -> None:
        self.calls = 0
        self.texts: list[str] = []
        self.generation_started = threading.Event()
        self.first_chunk_ready = threading.Event()
        self.allow_finish = threading.Event()

    def generate_audio_stream(self, **kwargs: Any):
        self.calls += 1
        self.texts.append(str(kwargs.get("text") or ""))
        self.generation_started.set()
        yield b"\x01\x00" * 7_680, 24_000, {"chunk": 0}
        self.first_chunk_ready.set()
        self.allow_finish.wait(timeout=2.0)
        yield b"\x02\x00" * 7_680, 24_000, {"chunk": 1}


def live_request(text: str, diagnostics_stream_id: str) -> TtsStreamRequest:
    return TtsStreamRequest.model_validate(
        {
            "text": text,
            "speaker": "Sofia",
            "language": "English",
            "chunk_size": 8,
            "temperature": 0.6,
            "top_k": 20,
            "top_p": 0.85,
            "repetition_penalty": 1.0,
            "append_silence": False,
            "parity_mode": True,
            "diagnostics_stream_id": diagnostics_stream_id,
        }
    )


def test_accepted_prefetch_replays_buffered_pcm_before_generation_finishes() -> None:
    clear_speculative_tts_cache()
    provider = BlockingTwoChunkProvider()
    request = live_request(
        "That starts much faster.",
        "chat-speculative-tts-test",
    )

    try:
        _start_prefetch("spec-test", request, provider)
        assert provider.first_chunk_ready.wait(timeout=1.0)
        _accept_entry("spec-test")

        proxy = _PrefetchingProviderProxy(provider)
        replay_kwargs = _stream_kwargs(request, provider)
        replay_kwargs["ignored_emotion_control"] = "warm"
        replay = proxy.generate_audio_stream(
            text=request.text,
            speaker=request.speaker,
            language=request.language or "en",
            **replay_kwargs,
        )

        first_pcm, first_rate, first_timing = next(replay)
        assert first_pcm == b"\x01\x00" * 7_680
        assert first_rate == 24_000
        assert first_timing["speculative_tts_cache"] is True
        assert provider.calls == 1

        provider.allow_finish.set()
        remaining = list(replay)
        assert remaining[0][0] == b"\x02\x00" * 7_680
        assert provider.calls == 1
        assert speculative_tts_cache_snapshot()[0]["claimed"] is True
    finally:
        provider.allow_finish.set()
        clear_speculative_tts_cache()


def test_cached_first_clause_can_prefix_a_larger_normal_phrase() -> None:
    clear_speculative_tts_cache()
    provider = BlockingTwoChunkProvider()
    request = live_request(
        "That starts much faster",
        "chat-speculative-tts-prefix",
    )

    try:
        _start_prefetch("spec-prefix", request, provider)
        assert provider.first_chunk_ready.wait(timeout=1.0)
        _accept_entry("spec-prefix")

        proxy = _PrefetchingProviderProxy(provider)
        replay = proxy.generate_audio_stream(
            text="That starts much faster, and keeps the voice natural.",
            speaker=request.speaker,
            language=request.language or "en",
            **_stream_kwargs(request, provider),
        )

        first_pcm, _, first_timing = next(replay)
        assert first_pcm == b"\x01\x00" * 7_680
        assert first_timing["speculative_tts_cache"] is True
        assert provider.calls == 1

        provider.allow_finish.set()
        remaining = list(replay)
        assert remaining
        assert provider.calls == 2
        assert provider.texts == [
            "That starts much faster",
            "and keeps the voice natural.",
        ]
    finally:
        provider.allow_finish.set()
        clear_speculative_tts_cache()


def test_cancelled_prefetch_does_not_start_after_waiting_for_qwen_lock() -> None:
    clear_speculative_tts_cache()
    provider = BlockingTwoChunkProvider()
    request = live_request(
        "This hypothesis was superseded.",
        "chat-speculative-tts-cancel-before-lock",
    )

    _PROVIDER_GENERATION_LOCK.acquire()
    try:
        _start_prefetch("spec-cancel-before-lock", request, provider)
        assert _cancel_entry("spec-cancel-before-lock") is True
    finally:
        _PROVIDER_GENERATION_LOCK.release()

    try:
        assert not provider.generation_started.wait(timeout=0.25)
        assert provider.calls == 0
    finally:
        provider.allow_finish.set()
        clear_speculative_tts_cache()


def test_aborted_cache_replay_cancels_background_generation() -> None:
    clear_speculative_tts_cache()
    provider = BlockingTwoChunkProvider()
    request = live_request(
        "Stop this interrupted response.",
        "chat-speculative-tts-replay-cancel",
    )

    try:
        _start_prefetch("spec-replay-cancel", request, provider)
        assert provider.first_chunk_ready.wait(timeout=1.0)
        _accept_entry("spec-replay-cancel")
        replay = _PrefetchingProviderProxy(provider).generate_audio_stream(
            text=request.text,
            speaker=request.speaker,
            language=request.language or "en",
            **_stream_kwargs(request, provider),
        )

        assert next(replay)[2]["speculative_tts_cache"] is True
        replay.close()

        snapshot = speculative_tts_cache_snapshot()
        assert snapshot[0]["cancelled"] is True
    finally:
        provider.allow_finish.set()
        clear_speculative_tts_cache()


def test_unaccepted_prefetch_is_never_visible_to_normal_tts() -> None:
    clear_speculative_tts_cache()
    provider = BlockingTwoChunkProvider()
    request = live_request(
        "Do not release this hypothesis.",
        "chat-speculative-tts-unaccepted",
    )

    try:
        _start_prefetch("spec-unaccepted", request, provider)
        assert provider.first_chunk_ready.wait(timeout=1.0)
        provider.allow_finish.set()

        proxy = _PrefetchingProviderProxy(provider)
        generated = list(
            proxy.generate_audio_stream(
                text=request.text,
                speaker=request.speaker,
                language=request.language or "en",
                **_stream_kwargs(request, provider),
            )
        )

        assert generated
        assert all(not timing.get("speculative_tts_cache") for _, _, timing in generated)
        assert provider.calls == 2
    finally:
        provider.allow_finish.set()
        clear_speculative_tts_cache()
