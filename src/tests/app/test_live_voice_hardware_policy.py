from __future__ import annotations

import os
from typing import ClassVar

from app.live_voice_hardware_policy import (
    _DEFERRED_TTS_ERROR,
    _deferred_speculative_entry,
    apply_live_voice_process_defaults,
    should_defer_speculative_tts,
    stateful_live_responses_enabled,
)


class _SerialTtsProvider:
    provider_name = "faster-qwen3-tts"
    tts_capabilities: ClassVar[dict[str, object]] = {
        "provider": "faster-qwen3-tts",
        "supports_streaming": True,
        "supports_concurrent_generation": False,
        "supports_emotion": False,
        "supports_speaking_rate": False,
        "supports_word_emphasis": False,
        "supports_ssml": False,
        "supports_word_timestamps": False,
    }

    def generate_audio_stream(self, **kwargs):
        raise AssertionError("deferred speculative TTS must not reach the provider")


class _ConcurrentTtsProvider(_SerialTtsProvider):
    provider_name = "concurrent-fixture"
    tts_capabilities: ClassVar[dict[str, object]] = {
        **_SerialTtsProvider.tts_capabilities,
        "provider": "concurrent-fixture",
        "supports_concurrent_generation": True,
    }


def test_stateful_live_responses_defaults_on_but_preserves_explicit_opt_out() -> None:
    assert stateful_live_responses_enabled(None) is True
    assert stateful_live_responses_enabled("true") is True
    assert stateful_live_responses_enabled("false") is False


def test_process_defaults_make_live_responses_and_model_discovery_reusable(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_LIVE_LMSTUDIO_STATEFUL_RESPONSES", raising=False)
    monkeypatch.delenv("OMNIX_LMSTUDIO_MODEL_DISCOVERY_CACHE_SECONDS", raising=False)

    apply_live_voice_process_defaults()

    assert os.environ["OMNIX_LIVE_LMSTUDIO_STATEFUL_RESPONSES"] == "true"
    assert os.environ["OMNIX_LMSTUDIO_MODEL_DISCOVERY_CACHE_SECONDS"] == "15"


def test_process_defaults_preserve_explicit_operator_overrides(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_LIVE_LMSTUDIO_STATEFUL_RESPONSES", "false")
    monkeypatch.setenv("OMNIX_LMSTUDIO_MODEL_DISCOVERY_CACHE_SECONDS", "3")

    apply_live_voice_process_defaults()

    assert os.environ["OMNIX_LIVE_LMSTUDIO_STATEFUL_RESPONSES"] == "false"
    assert os.environ["OMNIX_LMSTUDIO_MODEL_DISCOVERY_CACHE_SECONDS"] == "3"


def test_serial_tts_uses_priority_scheduler_by_default_with_explicit_kill_switch() -> None:
    provider = _SerialTtsProvider()

    assert should_defer_speculative_tts(provider) is False
    assert should_defer_speculative_tts(provider, "true") is False
    assert should_defer_speculative_tts(provider, "false") is True


def test_concurrent_tts_keeps_hidden_prefetch_enabled_even_with_serial_kill_switch() -> None:
    assert should_defer_speculative_tts(_ConcurrentTtsProvider(), "false") is False


def test_deferred_entry_cannot_be_claimed_by_authoritative_tts() -> None:
    from app.gateway import live_voice_speculative_tts as runtime
    from app.gateway.tts_stream_contract import TtsStreamRequest

    provider = _SerialTtsProvider()
    request = TtsStreamRequest(
        text="Hello there.",
        speaker="Sofia",
        language="English",
        chunk_size=4,
        diagnostics_stream_id="chat-speculative-policy-test",
        append_silence=False,
    )
    runtime.clear_speculative_tts_cache()
    try:
        entry = _deferred_speculative_entry(
            runtime,
            "spec-policy-test",
            request,
            provider,
            "shared",
        )
        assert entry.completed is True
        assert entry.error == _DEFERRED_TTS_ERROR
        runtime._accept_entry(entry.generation_id)
        kwargs = runtime._stream_kwargs(request, provider)
        assert runtime._claim_entry(
            request.text,
            request.speaker,
            request.language or "en",
            kwargs,
        ) is None
    finally:
        runtime.clear_speculative_tts_cache()
