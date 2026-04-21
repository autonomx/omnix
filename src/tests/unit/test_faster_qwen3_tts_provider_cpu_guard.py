from __future__ import annotations


def reset_model_loader():
    """Reset global model loader singleton between tests"""
    from app.providers.faster_qwen3_tts_provider import _model_loader
    _model_loader.model = None
    _model_loader.initialized = False


def test_get_model_does_not_forward_use_cuda_graphs(monkeypatch):
    """
    Regression test: Verify that use_cuda_graphs parameter is never forwarded
    to the underlying model loader, as this parameter has been removed.

    This test prevents the exact regression where removed parameters were still
    being passed downstream causing type errors and API mismatches.
    """
    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    captured = {}

    class FakeModel:
        pass

    def fake_get_or_create_tts_model(model_name, device, dtype, max_seq_len, **kwargs):
        captured["kwargs"] = dict(kwargs)
        return FakeModel()

    monkeypatch.setattr(
        "app.providers.faster_qwen3_tts_provider.get_or_create_tts_model",
        fake_get_or_create_tts_model,
        raising=False,
    )

    reset_model_loader()
    provider = FasterQwen3TTSProvider(
        config={
            "model_name": "Qwen/Qwen3-TTS-0.6B",
            "device": "cpu",
            "use_cuda_graphs": True,
        }
    )

    provider._get_model()

    # Critical assertion: use_cuda_graphs must NOT be present in forwarded kwargs
    assert "use_cuda_graphs" not in captured["kwargs"]


def test_get_model_accepts_explicit_parameter_removal(monkeypatch):
    """Verify that model loader is called with exactly the expected parameters only"""
    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    captured = {}

    class FakeModel:
        pass

    def fake_get_or_create_tts_model(**kwargs):
        captured["received_args"] = set(kwargs.keys())
        return FakeModel()

    monkeypatch.setattr(
        "app.providers.faster_qwen3_tts_provider.get_or_create_tts_model",
        fake_get_or_create_tts_model,
        raising=False,
    )

    reset_model_loader()
    provider = FasterQwen3TTSProvider(
        config={
            "model_name": "Qwen/Qwen3-TTS-0.6B",
            "device": "cuda",
            "use_cuda_graphs": True,
        }
    )

    provider._get_model()

    # Only allowed parameters should be passed
    assert captured["received_args"] == {"model_name", "device", "dtype", "max_seq_len"}