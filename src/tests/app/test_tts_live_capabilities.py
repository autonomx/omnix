from app.gateway import tts_live_capabilities


class _PhraseProvider:
    provider_name = "phrase-provider"

    def generate_audio_stream(self):
        raise NotImplementedError


class _IncrementalProvider(_PhraseProvider):
    provider_name = "incremental-provider"

    def create_incremental_tts_session(self):
        raise NotImplementedError


def test_phrase_provider_uses_persistent_fallback(monkeypatch) -> None:
    monkeypatch.setattr(tts_live_capabilities, "get_tts_provider", lambda: _PhraseProvider())
    payload = tts_live_capabilities.live_tts_capabilities_payload()
    assert payload["persistent_websocket"] is True
    assert payload["stateful_text_append"] is False
    assert payload["prosody_continuous_decoder"] is False
    assert payload["cancellation_generations"] is True
    assert payload["adaptive_playback_buffer"] is True
    assert payload["fallback_mode"] == "persistent_phrase_stream"


def test_native_incremental_provider_enables_text_append(monkeypatch) -> None:
    monkeypatch.setattr(tts_live_capabilities, "get_tts_provider", lambda: _IncrementalProvider())
    payload = tts_live_capabilities.live_tts_capabilities_payload()
    assert payload["stateful_text_append"] is True
    assert payload["prosody_continuous_decoder"] is True
