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

    with patch("app.shared.load_settings", return_value=fake_settings):
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