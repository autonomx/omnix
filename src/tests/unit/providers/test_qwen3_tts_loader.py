from __future__ import annotations

import sys
import types
from pathlib import Path



def test_resolve_model_source_prefers_env_override(monkeypatch, tmp_path):
    from app.providers.vendor.qwen3_tts import loader as loader_module

    override_dir = tmp_path / "local-qwen3"
    override_dir.mkdir()

    monkeypatch.setenv("OMNIX_TTS_MODEL_DIR", str(override_dir))
    monkeypatch.delenv("OMNIX_QWEN3_TTS_MODEL_DIR", raising=False)

    resolved = loader_module._resolve_model_source("Qwen/Qwen3-TTS-12Hz-0.6B-Base")
    assert Path(resolved) == override_dir.resolve()


def test_resolve_model_source_rewrites_legacy_broken_local_default(monkeypatch):
    from app.providers.vendor.qwen3_tts import loader as loader_module

    monkeypatch.delenv("OMNIX_TTS_MODEL_DIR", raising=False)
    monkeypatch.delenv("OMNIX_QWEN3_TTS_MODEL_DIR", raising=False)

    resolved = loader_module._resolve_model_source(r"F:\LLM\omnix\Qwen\Qwen3-TTS-12Hz-0.6B-Base")

    assert resolved == "Qwen/Qwen3-TTS-12Hz-0.6B-Base"


def test_validate_local_model_dir_accepts_none_metadata_by_inference(monkeypatch, tmp_path):
    from app.providers.vendor.qwen3_tts import loader as loader_module

    model_dir = tmp_path / "broken-qwen3"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "preprocessor_config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model-00001-of-00001.safetensors").write_bytes(b"not-real-but-open-is-mocked")

    class _Handle:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def metadata(self):
            return None

    fake_safetensors = types.ModuleType("safetensors")
    fake_safetensors.safe_open = lambda *args, **kwargs: _Handle()
    monkeypatch.setitem(sys.modules, "safetensors", fake_safetensors)

    result = loader_module._validate_local_model_dir(model_dir)
    assert result["required_files_ok"] is True
    assert result["num_safetensors_shards"] == 1
    assert result["shards"][0]["metadata_keys"] == ["_omnix_inferred", "format"]


def test_provider_rewrites_legacy_broken_local_default_before_loader_call():
    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    provider = FasterQwen3TTSProvider(
        {
            "model_name": r"F:\LLM\omnix\Qwen\Qwen3-TTS-12Hz-0.6B-Base",
            "device": "cpu",
        }
    )

    assert provider._model_config["model_name"] == "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
    runtime_status = provider.get_runtime_status()
    assert runtime_status["configured_model_source"] == "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
    assert "faster-qwen3-tts-main" in runtime_status["runtime_code_dir"]
