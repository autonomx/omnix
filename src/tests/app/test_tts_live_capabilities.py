from app.gateway import tts_live_capabilities


class _PhraseProvider:
    provider_name = "phrase-provider"

    def generate_audio_stream(self):
        raise NotImplementedError


class _IncrementalProvider(_PhraseProvider):
    provider_name = "incremental-provider"

    def create_incremental_tts_session(self):
        raise NotImplementedError


def test_phrase_provider_uses_incremental_clause_stream(monkeypatch) -> None:
    monkeypatch.setattr(tts_live_capabilities, "get_tts_provider", lambda: _PhraseProvider())
    payload = tts_live_capabilities.live_tts_capabilities_payload()
    assert payload["persistent_websocket"] is True
    assert payload["incremental_text_ingest"] is True
    assert payload["text_commit_deadline_ms"] == 140
    assert payload["text_commit_minimum_characters"] == 12
    assert payload["streaming_audio_chunks"] is True
    assert payload["native_decoder_text_append"] is False
    assert payload["stateful_text_append"] is False
    assert payload["prosody_continuous_decoder"] is False
    assert payload["cancellation_generations"] is True
    assert payload["adaptive_playback_buffer"] is True
    assert payload["fallback_mode"] == "persistent_incremental_clause_stream"


def test_native_incremental_provider_enables_text_append(monkeypatch) -> None:
    monkeypatch.setattr(tts_live_capabilities, "get_tts_provider", lambda: _IncrementalProvider())
    payload = tts_live_capabilities.live_tts_capabilities_payload()
    assert payload["incremental_text_ingest"] is True
    assert payload["native_decoder_text_append"] is True
    assert payload["stateful_text_append"] is True
    assert payload["prosody_continuous_decoder"] is True
