from __future__ import annotations

import pytest


def test_load_tts_model_classifies_none_metadata_failure(monkeypatch):
    from app.providers.vendor.qwen3_tts import loader as loader_module

    monkeypatch.setattr(loader_module, "ensure_vendored_qwen3_tts_available", lambda: {})

    class _BoomModel:
        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            raise AttributeError("'NoneType' object has no attribute 'get'")

    monkeypatch.setattr(
        loader_module,
        "load_tts_model",
        loader_module.load_tts_model,
    )

    import sys
    import types

    fake_module = types.ModuleType("app.providers.vendor.faster_qwen3_tts.model")
    fake_module.FasterQwen3TTS = _BoomModel
    monkeypatch.setitem(sys.modules, "app.providers.vendor.faster_qwen3_tts.model", fake_module)

    with pytest.raises(RuntimeError) as exc_info:
        loader_module.load_tts_model("Qwen/Qwen3-TTS-12Hz-0.6B-Base", "cpu")

    assert "safetensors_metadata_missing_or_incompatible" in str(exc_info.value)