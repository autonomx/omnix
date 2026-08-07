from __future__ import annotations

import threading
from typing import Any

from app.gateway.live_chat_speculative_tts import (
    _PrefetchingProviderProxy,
    _accept_entry,
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
        self.first_chunk_ready = threading.Event()
        self.allow_finish = threading.Event()

    def generate_audio_stream(self, **_kwargs: Any):
        self.calls += 1
        yield b"\x01\x00" * 7_680, 24_000, {"chunk": 0}
        self.first_chunk_ready.set()
        self.allow_finish.wait(timeout=2.0)
        yield b"\x02\x00" * 7_680, 24_000, {"chunk": 1}


def test_accepted_prefetch_replays_buffered_pcm_before_generation_finishes() -> None:
    clear_speculative_tts_cache()
    provider = BlockingTwoChunkProvider()
    request = TtsStreamRequest.model_validate(
        {
            "text": "That starts much faster.",
            "speaker": "Sofia",
            "language": "English",
            "chunk_size": 8,
            "temperature": 0.6,
            "top_k": 20,
            "top_p": 0.85,
            "repetition_penalty": 1.0,
            "append_silence": False,
            "parity_mode": True,
            "diagnostics_stream_id": "chat-speculative-tts-test",
        }
    )

    try:
        _start_prefetch("spec-test", request, provider)
        assert provider.first_chunk_ready.wait(timeout=1.0)
        _accept_entry("spec-test")

        proxy = _PrefetchingProviderProxy(provider)
        replay = proxy.generate_audio_stream(
            text=request.text,
            speaker=request.speaker,
            language=request.language or "en",
            **_stream_kwargs(request, provider),
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


def test_unaccepted_prefetch_is_never_visible_to_normal_tts() -> None:
    clear_speculative_tts_cache()
    provider = BlockingTwoChunkProvider()
    request = TtsStreamRequest.model_validate(
        {
            "text": "Do not release this hypothesis.",
            "speaker": "Sofia",
            "language": "English",
            "diagnostics_stream_id": "chat-speculative-tts-unaccepted",
        }
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
