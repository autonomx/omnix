from __future__ import annotations

import pytest

from app.platform.live_speech.tts import DeterministicSpeechSynthesizer
from app.platform.live_speech.tts_adapters import (
    QwenServiceSpeechSynthesizer,
    SpeechServiceUnavailable,
    create_synthesizer_from_env,
)


def test_service_adapter_reports_an_unavailable_endpoint_instead_of_fake_audio() -> None:
    adapter = QwenServiceSpeechSynthesizer(base_url="http://127.0.0.1:1", timeout_seconds=0.01)

    with pytest.raises(SpeechServiceUnavailable):
        adapter.synthesize("hello", voice="default")


def test_factory_defaults_to_deterministic_provider(monkeypatch) -> None:
    monkeypatch.delenv("LIVE_SPEECH_TTS_PROVIDER", raising=False)

    assert isinstance(create_synthesizer_from_env(), DeterministicSpeechSynthesizer)


def test_factory_selects_service_provider(monkeypatch) -> None:
    monkeypatch.setenv("LIVE_SPEECH_TTS_PROVIDER", "real")
    monkeypatch.setenv("LIVE_SPEECH_TTS_URL", "http://example.test")

    adapter = create_synthesizer_from_env()

    assert isinstance(adapter, QwenServiceSpeechSynthesizer)
    assert adapter.base_url == "http://example.test"
