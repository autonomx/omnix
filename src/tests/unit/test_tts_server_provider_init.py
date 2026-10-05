from __future__ import annotations

from unittest.mock import patch


def test_load_qwen3_provider_passes_settings_config():
    import tts_server

    captured = {}

    class FakeProvider:
        def __init__(self, config):
            captured["config"] = dict(config)
            self.provider_name = "faster-qwen3-tts"
            self.device = config.get("device", "")
            self._model_config = dict(config)

    fake_settings = {
        "faster-qwen3-tts": {
            "model_name": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
            "device": "cuda",
            "dtype": "bfloat16",
            "max_seq_len": 2048,
        }
    }

    with patch("app.providers.service.load_settings", return_value=fake_settings):
        with patch("app.providers.faster_qwen3_tts_provider.FasterQwen3TTSProvider", FakeProvider):
            provider = tts_server._load_qwen3_provider()

    assert provider is not None
    assert captured["config"]["model_name"] == "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
    assert captured["config"]["device"] == "cuda"


def test_initialize_tts_provider_returns_error_payload_when_provider_init_fails():
    import tts_server

    with patch("tts_server._load_qwen3_provider", side_effect=TypeError("missing config")):
        result = tts_server.initialize_tts_provider()

    assert result["ok"] is False
    assert result["provider"] == "qwen3_tts"
    assert "missing config" in result["error"]
    assert isinstance(result.get("details"), dict)


def test_health_reports_not_ready_when_provider_is_not_initialized():
    import tts_server

    tts_server._TTS_PROVIDER = None
    tts_server._TTS_PROVIDER_ERROR = "provider_not_initialized"

    result = tts_server.get_tts_service_status()

    assert result["ok"] is False
    assert result["provider"] == "qwen3_tts"
    assert "provider_not_initialized" in result["error"]


def test_model_owner_loss_stops_provider_and_marks_server_not_ready():
    import tts_server

    class FakeProvider:
        stopped = False

        def stop(self):
            self.stopped = True

    provider = FakeProvider()
    guard = object()
    previous = (
        tts_server._TTS_PROVIDER,
        tts_server._TTS_PROVIDER_ERROR,
        tts_server._TTS_MODEL_OWNER_GUARD,
    )
    try:
        tts_server._TTS_PROVIDER = provider
        tts_server._TTS_PROVIDER_ERROR = ""
        tts_server._TTS_MODEL_OWNER_GUARD = guard
        tts_server._handle_tts_model_owner_loss(provider, guard)

        assert provider.stopped
        assert tts_server.get_tts_service_status()["ok"] is False
        assert "lease was lost" in tts_server.get_tts_service_status()["error"]
        assert tts_server._TTS_MODEL_OWNER_GUARD is None
    finally:
        (
            tts_server._TTS_PROVIDER,
            tts_server._TTS_PROVIDER_ERROR,
            tts_server._TTS_MODEL_OWNER_GUARD,
        ) = previous


def test_one_request_synthesizes_a_bounded_amount_of_text():
    import pydantic
    import pytest
    import tts_server

    limit = tts_server.MAX_TTS_TEXT_CHARS
    for model in (tts_server.TtsGenerateRequest, tts_server.TtsGenerateStreamRequest):
        assert model(text="x" * limit).text == "x" * limit
        with pytest.raises(pydantic.ValidationError):
            model(text="x" * (limit + 1))
