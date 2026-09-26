from __future__ import annotations

from app.providers import faster_qwen3_tts_provider as module


def test_loaded_model_is_replaced_when_local_artifacts_change(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_TTS_MODEL_DIR", raising=False)
    monkeypatch.delenv("OMNIX_QWEN3_TTS_MODEL_DIR", raising=False)
    model_file = tmp_path / "model.safetensors"
    model_file.write_bytes(b"first weights")
    monkeypatch.setattr(module, "_model_loader", module.ModelLoader())
    monkeypatch.setattr(module, "ensure_vendored_qwen3_tts_available", lambda: None)
    loaded = []
    resets = []

    def load(**_kwargs):
        result = object()
        loaded.append(result)
        return result

    monkeypatch.setattr(module, "get_or_create_tts_model", load)
    monkeypatch.setattr(module, "reset_tts_model_cache", lambda: resets.append(True))
    provider = module.FasterQwen3TTSProvider({"model_dir": str(tmp_path), "device": "cpu"})
    first = provider._get_model()
    assert provider._get_model() is first
    model_file.write_bytes(b"second weights with a new length")
    second = provider._get_model()
    assert second is not first
    assert loaded == [first, second]
    assert resets == [True]
