from __future__ import annotations

from app.live_voice_hardware_policy import (
    _DEFERRED_TTS_ERROR,
    _deferred_speculative_entry,
    should_defer_speculative_tts,
    stateful_live_responses_enabled,
)


class _SerialTtsProvider:
    provider_name = "faster-qwen3-tts"
    tts_capabilities = {
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
    tts_capabilities = {
        **_SerialTtsProvider.tts_capabilities,
        "provider": "concurrent-fixture",
        "supports_concurrent_generation": True,
    }


def test_stateful_live_responses_defaults_on_but_preserves_explicit_opt_out() -> None:
    assert stateful_live_responses_enabled(None) is True
    assert stateful_live_responses_enabled("true") is True
    assert stateful_live_responses_enabled("false") is False


def test_serial_tts_is_deferred_unless_explicitly_allowed() -> None:
    provider = _SerialTtsProvider()

    assert should_defer_speculative_tts(provider) is True
    assert should_defer_speculative_tts(provider, "false") is True
    assert should_defer_speculative_tts(provider, "true") is False


def test_concurrent_tts_keeps_hidden_prefetch_enabled() -> None:
    assert should_defer_speculative_tts(_ConcurrentTtsProvider()) is False


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
