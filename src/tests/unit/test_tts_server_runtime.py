from __future__ import annotations

import io
import wave
from typing import Any, Dict, Iterable, Tuple

from fastapi.testclient import TestClient


def test_initialize_tts_provider_passes_config(monkeypatch):
    import tts_server

    captured: Dict[str, Any] = {}

    class FakeProvider:
        def __init__(self, config):
            captured["config"] = dict(config)
            self.provider_name = "qwen3_tts"
            self.device = config.get("device", "cpu")
            self._model_config = dict(config)

    fake_settings = {
        "faster-qwen3-tts": {
            "model_name": "Qwen/Qwen3-TTS-0.6B",
            "device": "cuda",
        }
    }

    def fake_load_settings():
        return fake_settings

    monkeypatch.setattr("app.shared.load_settings", fake_load_settings, raising=False)
    monkeypatch.setattr(
        "app.providers.faster_qwen3_tts_provider.FasterQwen3TTSProvider",
        FakeProvider,
        raising=False,
    )

    provider = tts_server._load_qwen3_provider()

    assert provider is not None
    assert captured["config"]["model_name"] == "Qwen/Qwen3-TTS-0.6B"
    assert captured["config"]["device"] == "cuda"


def test_get_tts_service_status_returns_ready_details():
    import tts_server

    class FakeProvider:
        provider_name = "qwen3_tts"
        device = "cuda"
        _model_config = {"model_name": "Qwen/Qwen3-TTS-0.6B"}

    old_provider = tts_server._TTS_PROVIDER
    old_error = tts_server._TTS_PROVIDER_ERROR
    try:
        tts_server._TTS_PROVIDER = FakeProvider()
        tts_server._TTS_PROVIDER_ERROR = ""
        result = tts_server.get_tts_service_status()
    finally:
        tts_server._TTS_PROVIDER = old_provider
        tts_server._TTS_PROVIDER_ERROR = old_error

    assert result["ok"] is True
    assert result["provider"] == "qwen3_tts"
    assert result["details"]["provider_class"] == "FakeProvider"
    assert result["details"]["configured_model"] == "Qwen/Qwen3-TTS-0.6B"
    assert result["details"]["configured_device"] == "cuda"


def test_generate_stream_audio_returns_chunks_on_success():
    import tts_server

    class FakeProvider:
        def generate_audio_stream(
            self,
            *,
            text: str,
            speaker: str,
            language: str,
            **_: Any,
        ) -> Iterable[Tuple[bytes, int, Dict[str, Any]]]:
            assert text == "hello world"
            assert speaker == "default"
            assert language == "en"
            import numpy as np
            yield (np.array([0.0, 0.1, 0.2], dtype=np.float32), 24000, {"chunk_index": 0})

    old_provider = tts_server._TTS_PROVIDER
    old_error = tts_server._TTS_PROVIDER_ERROR
    try:
        tts_server._TTS_PROVIDER = FakeProvider()
        tts_server._TTS_PROVIDER_ERROR = ""
        client = TestClient(tts_server.app)

        response = client.post(
            "/api/tts/generate_stream_audio",
            json={
                "text": "hello world",
                "speaker": "default",
                "language": "en",
            },
        )
    finally:
        tts_server._TTS_PROVIDER = old_provider
        tts_server._TTS_PROVIDER_ERROR = old_error

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    with wave.open(io.BytesIO(response.content), "rb") as wav_file:
        assert wav_file.getframerate() == 24000
        assert wav_file.getnframes() == 3


def test_generate_stream_audio_falls_back_to_wav_response():
    import tts_server

    class FakeProvider:
        def generate_audio_stream(self, **_: Any):
            raise RuntimeError("offline")

        def generate_audio(self, **_: Any):
            return {
                "success": True,
                "audio_base64": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=",
                "format": "audio/wav",
            }

    old_provider = tts_server._TTS_PROVIDER
    old_error = tts_server._TTS_PROVIDER_ERROR
    try:
        tts_server._TTS_PROVIDER = FakeProvider()
        tts_server._TTS_PROVIDER_ERROR = ""
        client = TestClient(tts_server.app)

        response = client.post(
            "/api/tts/generate_stream_audio",
            json={
                "text": "hello world",
                "speaker": "default",
                "language": "en",
            },
        )
    finally:
        tts_server._TTS_PROVIDER = old_provider
        tts_server._TTS_PROVIDER_ERROR = old_error

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content[:4] == b"RIFF"


def test_generate_stream_audio_surfaces_missing_sox_error():
    import tts_server

    class FakeProvider:
        def generate_audio_stream(self, **_: Any):
            raise RuntimeError("Model loading failed: No module named 'sox'")

    old_provider = tts_server._TTS_PROVIDER
    old_error = tts_server._TTS_PROVIDER_ERROR
    try:
        tts_server._TTS_PROVIDER = FakeProvider()
        tts_server._TTS_PROVIDER_ERROR = ""
        client = TestClient(tts_server.app)

        response = client.post(
            "/api/tts/generate_stream_audio",
            json={
                "text": "hello world",
                "speaker": "default",
                "language": "en",
            },
        )
    finally:
        tts_server._TTS_PROVIDER = old_provider
        tts_server._TTS_PROVIDER_ERROR = old_error

    assert response.status_code == 500
    payload = response.json()
    assert payload["success"] is False
    assert payload["provider"] == "qwen3_tts"
    assert "No module named 'sox'" in payload["error"]
    assert "traceback" in payload


def test_generate_audio_surfaces_missing_sox_error():
    import tts_server

    class FakeProvider:
        def generate_audio(self, **_: Any):
            raise RuntimeError("Model loading failed: No module named 'sox'")

    old_provider = tts_server._TTS_PROVIDER
    old_error = tts_server._TTS_PROVIDER_ERROR
    try:
        tts_server._TTS_PROVIDER = FakeProvider()
        tts_server._TTS_PROVIDER_ERROR = ""
        client = TestClient(tts_server.app)

        response = client.post(
            "/api/tts/generate_audio",
            json={
                "text": "hello world",
                "speaker": "default",
                "language": "en",
            },
        )
    finally:
        tts_server._TTS_PROVIDER = old_provider
        tts_server._TTS_PROVIDER_ERROR = old_error

    assert response.status_code == 500
    payload = response.json()
    assert payload["success"] is False
    assert payload["provider"] == "qwen3_tts"
    assert "No module named 'sox'" in payload["error"]
