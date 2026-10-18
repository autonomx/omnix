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

def test_a_request_without_cuda_graphs_does_not_disable_them_for_later_requests(monkeypatch):
    """A voice job asking for eager decode must not leave the shared model unable to run fast decodes.

    Regression: ``use_cuda_graphs=False`` used to clear ``_cuda_graphs_enabled`` on the shared model
    before its graphs were captured; every later fast request then replayed a missing graph.
    """
    import numpy as np

    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    class FakeModel:
        _cuda_graphs_enabled = True

        def __init__(self):
            self.parity = []

        def generate_voice_clone(self, **kwargs):
            self.parity.append(kwargs["parity_mode"])
            return [np.full(1200, 0.1, dtype=np.float32)], 12000

    model = FakeModel()
    monkeypatch.setattr("app.providers.faster_qwen3_tts_provider._clone_reference", lambda _speaker: ("ref.wav", "Ref."))
    monkeypatch.setattr("app.providers.faster_qwen3_tts_provider._clone_conditioning",
                        lambda _kwargs, _config, saved: (saved, False))
    provider = FasterQwen3TTSProvider(config={"model_name": "Qwen/Qwen3-TTS-0.6B", "device": "cpu"})
    monkeypatch.setattr(provider, "_get_model", lambda: model)
    monkeypatch.setattr(provider, "_numpy_to_wav_bytes", lambda audio, sample_rate=12000: b"RIFF")

    assert provider.generate_audio("Hello.", speaker="voice", use_cuda_graphs=False, parity_mode=False)["success"]
    assert model._cuda_graphs_enabled is True
    assert provider.generate_audio("Hello.", speaker="voice", parity_mode=False)["success"]
    assert model.parity == [True, False]

    # Graphs disabled after a real failure: fast requests decode in parity mode instead of crashing.
    model._cuda_graphs_enabled = False
    result = provider.generate_audio("Hello.", speaker="voice", parity_mode=False)
    assert model.parity[-1] is True and result["generation_parameters_used"]["parity_mode"] is True
