from __future__ import annotations

import os

from app.live_speech.stt import BufferedStreamingTranscriber
from app.live_speech.stt_adapters import ParakeetServiceTranscriber, create_transcriber_from_env


def _pcm(samples: int = 3200) -> bytes:
    return (2000).to_bytes(2, byteorder="little", signed=True) * samples


def test_parakeet_adapter_emits_local_partial_before_final() -> None:
    adapter = ParakeetServiceTranscriber(base_url="http://127.0.0.1:1", partial_every_bytes=3200)

    updates = adapter.accept_audio(_pcm())

    assert updates
    assert updates[0].final is False
    assert updates[0].text.startswith("speech ")


def test_parakeet_adapter_falls_back_when_service_unavailable() -> None:
    adapter = ParakeetServiceTranscriber(base_url="http://127.0.0.1:1", partial_every_bytes=3200, timeout_seconds=0.01)
    adapter.accept_audio(_pcm())

    final = adapter.finalize()

    assert final.final is True
    assert final.text == "transcribed speech"
    assert final.duration_ms is not None


def test_create_transcriber_from_env_defaults_to_fake(monkeypatch) -> None:
    monkeypatch.delenv("LIVE_SPEECH_STT_PROVIDER", raising=False)

    assert isinstance(create_transcriber_from_env(), BufferedStreamingTranscriber)


def test_create_transcriber_from_env_selects_parakeet(monkeypatch) -> None:
    monkeypatch.setenv("LIVE_SPEECH_STT_PROVIDER", "parakeet")
    monkeypatch.setenv("LIVE_SPEECH_STT_URL", "http://example.test")

    adapter = create_transcriber_from_env()

    assert isinstance(adapter, ParakeetServiceTranscriber)
    assert adapter.base_url == "http://example.test"
