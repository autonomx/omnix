from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest


def test_load_tts_model_classifies_none_metadata_failure(monkeypatch):
    from app.providers.vendor.qwen3_tts import loader as loader_module

    monkeypatch.setattr(loader_module, "ensure_vendored_qwen3_tts_available", lambda: {})
    monkeypatch.setattr(loader_module, "validate_qwen3_tts_runtime", lambda: {"ready": True, "error": ""})
    monkeypatch.setattr(loader_module, "_resolve_model_source", lambda model_name: model_name)
    monkeypatch.setattr(loader_module, "_looks_like_local_model_path", lambda model_name: False)

    class _BoomModel:
        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            raise AttributeError("'NoneType' object has no attribute 'get'")

    fake_module = types.ModuleType("app.providers.vendor.faster_qwen3_tts.model")
    fake_module.FasterQwen3TTS = _BoomModel
    monkeypatch.setitem(sys.modules, "app.providers.vendor.faster_qwen3_tts.model", fake_module)

    with pytest.raises(RuntimeError) as exc_info:
        loader_module.load_tts_model("Qwen/Qwen3-TTS-12Hz-0.6B-Base", "cpu")

    assert "safetensors_metadata_missing_or_incompatible" in str(exc_info.value)


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


def test_load_tts_model_uses_validated_local_snapshot_path(monkeypatch, tmp_path):
    from app.providers.vendor.qwen3_tts import loader as loader_module

    local_snapshot = tmp_path / "qwen3-snapshot"
    local_snapshot.mkdir()
    (local_snapshot / "config.json").write_text("{}", encoding="utf-8")
    (local_snapshot / "preprocessor_config.json").write_text("{}", encoding="utf-8")
    (local_snapshot / "model-00001-of-00001.safetensors").write_bytes(b"placeholder")

    monkeypatch.setattr(loader_module, "ensure_vendored_qwen3_tts_available", lambda: {})
    monkeypatch.setattr(loader_module, "validate_qwen3_tts_runtime", lambda: {"ready": True, "error": ""})
    monkeypatch.setattr(loader_module, "_resolve_model_source", lambda model_name: str(local_snapshot))

    def _fake_validate(model_dir):
        return {
            "model_dir": str(model_dir),
            "required_files_ok": True,
            "num_safetensors_shards": 1,
            "shards": [],
        }

    monkeypatch.setattr(loader_module, "_validate_local_model_dir", _fake_validate)

    captured = {}

    class _GoodModel:
        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return object()

    fake_module = types.ModuleType("app.providers.vendor.faster_qwen3_tts.model")
    fake_module.FasterQwen3TTS = _GoodModel
    monkeypatch.setitem(sys.modules, "app.providers.vendor.faster_qwen3_tts.model", fake_module)

    model = loader_module.load_tts_model("Qwen/Qwen3-TTS-12Hz-0.6B-Base", "cpu", dtype="float32")
    assert model is not None
    assert captured["kwargs"]["model_name"] == str(local_snapshot)
    assert captured["kwargs"]["device"] == "cpu"
    assert captured["kwargs"]["dtype"] == "float32"


def test_load_tts_model_fails_fast_on_incomplete_local_dir(monkeypatch, tmp_path):
    from app.providers.vendor.qwen3_tts import loader as loader_module

    incomplete_dir = tmp_path / "incomplete-qwen3"
    incomplete_dir.mkdir()
    (incomplete_dir / "config.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(loader_module, "ensure_vendored_qwen3_tts_available", lambda: {})
    monkeypatch.setattr(loader_module, "validate_qwen3_tts_runtime", lambda: {"ready": True, "error": ""})
    monkeypatch.setattr(loader_module, "_resolve_model_source", lambda model_name: str(incomplete_dir))

    class _ShouldNotRun:
        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            raise AssertionError("from_pretrained should not be reached for incomplete local model dirs")

    fake_module = types.ModuleType("app.providers.vendor.faster_qwen3_tts.model")
    fake_module.FasterQwen3TTS = _ShouldNotRun
    monkeypatch.setitem(sys.modules, "app.providers.vendor.faster_qwen3_tts.model", fake_module)

    with pytest.raises(RuntimeError) as exc_info:
        loader_module.load_tts_model("Qwen/Qwen3-TTS-12Hz-0.6B-Base", "cpu")

    text = str(exc_info.value)
    assert "model_dir_missing_required_files:" in text
    assert "preprocessor_config.json" in text


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
