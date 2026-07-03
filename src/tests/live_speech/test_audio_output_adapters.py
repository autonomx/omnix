from __future__ import annotations

from app.live_speech.tts import DeterministicSpeechSynthesizer
from app.live_speech.tts_adapters import QwenServiceSpeechSynthesizer, create_synthesizer_from_env


def test_service_adapter_returns_audio_when_endpoint_is_unavailable() -> None:
    adapter = QwenServiceSpeechSynthesizer(base_url="http://127.0.0.1:1", timeout_seconds=0.01)

    chunks = adapter.synthesize("hello", voice="default")

    assert chunks
    assert chunks[0].pcm
    assert chunks[0].sample_rate == 24000


def test_factory_defaults_to_deterministic_provider(monkeypatch) -> None:
    monkeypatch.delenv("LIVE_SPEECH_TTS_PROVIDER", raising=False)

    assert isinstance(create_synthesizer_from_env(), DeterministicSpeechSynthesizer)


def test_factory_selects_service_provider(monkeypatch) -> None:
    monkeypatch.setenv("LIVE_SPEECH_TTS_PROVIDER", "real")
    monkeypatch.setenv("LIVE_SPEECH_TTS_URL", "http://example.test")

    adapter = create_synthesizer_from_env()

    assert isinstance(adapter, QwenServiceSpeechSynthesizer)
    assert adapter.base_url == "http://example.test"
