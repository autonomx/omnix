from __future__ import annotations

import base64
import traceback

import numpy as np
import pytest
import soundfile as sf


@pytest.mark.smoke
def test_qwen3_import_chain():
    """
    FAIL FAST if any vendored Qwen3 import chain is broken.

    This catches:
    - missing transformers symbols (e.g. MimiConfig)
    - missing deps (sox, onnxruntime, etc)
    - bad vendor packaging
    """

    try:
        from app.providers.vendor.qwen_tts import Qwen3TTSModel  # noqa
    except Exception as e:
        pytest.fail(
            "Qwen3 import chain failed:\n"
            f"{type(e).__name__}: {e}\n\n"
            f"{traceback.format_exc(limit=10)}"
        )


@pytest.mark.smoke
def test_faster_qwen3_provider_init():
    """
    Ensures provider can be constructed with config.

    This catches:
    - constructor mismatches
    - config schema issues
    """

    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    provider = FasterQwen3TTSProvider(config={})
    assert provider is not None


@pytest.mark.smoke
def test_qwen3_model_load_cpu_path():
    """
    Critical smoke test:
    - calls _get_model()
    - forces full vendored model load path
    - MUST fail here instead of inside the app

    This is the test that replaces "click Speak and hope".
    """

    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    provider = FasterQwen3TTSProvider(
        config={
            "device": "cpu",   # force CPU-safe path
        }
    )

    try:
        model = provider._get_model()
    except Exception as e:
        pytest.fail(
            "Qwen3 model load failed:\n"
            f"{type(e).__name__}: {e}\n\n"
            f"{traceback.format_exc(limit=10)}"
        )

    assert model is not None


@pytest.mark.smoke
def test_qwen3_generate_minimal_call(monkeypatch):
    """
    Optional but VERY useful:
    verifies generation path wiring without heavy compute.

    We monkeypatch the model to avoid real inference cost.
    """

    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    provider = FasterQwen3TTSProvider(config={"device": "cpu"})

    # Replace heavy model with stub AFTER load succeeds
    provider._get_model()

    class DummyModel:
        def generate(self, *args, **kwargs):
            return b"\x00\x00"  # fake audio bytes

    provider._model_loader.model = DummyModel()

    try:
        out = provider.generate_audio(
            text="hello",
            speaker="test",
            language="en"
        )
    except Exception as e:
        pytest.fail(
            "Qwen3 generate_audio path failed:\n"
            f"{type(e).__name__}: {e}\n\n"
            f"{traceback.format_exc(limit=10)}"
        )

    assert out is not None


@pytest.mark.smoke
def test_generate_audio_returns_reference_fallback_when_model_unavailable(monkeypatch, tmp_path):
    from app.providers import faster_qwen3_tts_provider as provider_module
    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    sample_rate = 12000
    preview_audio = np.linspace(-0.2, 0.2, sample_rate // 2, dtype=np.float32)
    preview_path = tmp_path / "default_ref.wav"
    sf.write(preview_path, preview_audio, sample_rate)

    monkeypatch.setattr(provider_module, "VOICE_CLONES_DIR", str(tmp_path))

    provider = FasterQwen3TTSProvider(config={"device": "cpu"})

    def _raise_model_error():
        raise RuntimeError("model unavailable in offline test")

    monkeypatch.setattr(provider, "_get_model", _raise_model_error)

    out = provider.generate_audio(text="hello world", speaker="Maya", language="en")

    assert out["success"] is True
    assert out["fallback"] == "reference-preview"
    assert out["audio"] == out["audio_base64"]
    decoded = base64.b64decode(out["audio_base64"])
    assert decoded[:4] == b"RIFF"
    assert out["sample_rate"] == sample_rate


def test_generate_audio_retries_graph_capture_failure_in_parity_mode(monkeypatch, tmp_path):
    from app.providers import faster_qwen3_tts_provider as provider_module
    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    sample_rate = 12000
    preview_audio = np.sin(np.linspace(0, 20, sample_rate, dtype=np.float32)) * 0.1
    sf.write(tmp_path / "Jinx.wav", preview_audio, sample_rate)
    monkeypatch.setattr(provider_module, "VOICE_CLONES_DIR", str(tmp_path))

    class GraphFlakyModel:
        def __init__(self) -> None:
            self.calls: list[bool] = []

        def generate_voice_clone(self, **kwargs):
            self.calls.append(bool(kwargs.get("parity_mode")))
            if not kwargs.get("parity_mode"):
                raise RuntimeError("Offset increment outside graph capture encountered unexpectedly.")
            return [preview_audio], sample_rate

    model = GraphFlakyModel()
    provider = FasterQwen3TTSProvider(config={"device": "cpu", "parity_mode": False})
    monkeypatch.setattr(provider, "_get_model", lambda: model)

    out = provider.generate_audio(text="hello world", speaker="Jinx", language="en")

    assert out["success"] is True
    assert model.calls == [False, True]
    decoded = base64.b64decode(out["audio_base64"])
    assert decoded[:4] == b"RIFF"


def test_generate_audio_resets_model_when_graph_parity_retry_is_poisoned(monkeypatch, tmp_path):
    from app.providers import faster_qwen3_tts_provider as provider_module
    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    sample_rate = 12000
    preview_audio = np.sin(np.linspace(0, 20, sample_rate, dtype=np.float32)) * 0.1
    sf.write(tmp_path / "Maya.wav", preview_audio, sample_rate)
    monkeypatch.setattr(provider_module, "VOICE_CLONES_DIR", str(tmp_path))

    class PoisonedGraphModel:
        def __init__(self) -> None:
            self.calls: list[bool] = []

        def generate_voice_clone(self, **kwargs):
            self.calls.append(bool(kwargs.get("parity_mode")))
            raise RuntimeError("CUDA error: operation failed due to a previous error during capture")

    class FreshGraphModel:
        def __init__(self) -> None:
            self.calls: list[bool] = []

        def generate_voice_clone(self, **kwargs):
            self.calls.append(bool(kwargs.get("parity_mode")))
            return [preview_audio], sample_rate

    poisoned_model = PoisonedGraphModel()
    fresh_model = FreshGraphModel()
    models = [poisoned_model, fresh_model]
    reset_calls: list[bool] = []

    provider = FasterQwen3TTSProvider(config={"device": "cpu"})
    monkeypatch.setattr(provider, "_get_model", lambda: models.pop(0))
    monkeypatch.setattr(provider_module, "reset_tts_model_cache", lambda: reset_calls.append(True))

    out = provider.generate_audio(text="hello world", speaker="Maya", language="en")

    assert out["success"] is True
    assert poisoned_model.calls == [True]
    assert fresh_model.calls == [True]
    assert reset_calls == [True]
    decoded = base64.b64decode(out["audio_base64"])
    assert decoded[:4] == b"RIFF"


def test_generate_audio_defaults_to_parity_mode(monkeypatch, tmp_path):
    from app.providers import faster_qwen3_tts_provider as provider_module
    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    sample_rate = 12000
    preview_audio = np.sin(np.linspace(0, 20, sample_rate, dtype=np.float32)) * 0.1
    sf.write(tmp_path / "Maya.wav", preview_audio, sample_rate)
    monkeypatch.setattr(provider_module, "VOICE_CLONES_DIR", str(tmp_path))

    class ParityRecordingModel:
        def __init__(self) -> None:
            self.calls: list[bool] = []

        def generate_voice_clone(self, **kwargs):
            self.calls.append(bool(kwargs.get("parity_mode")))
            return [preview_audio], sample_rate

    model = ParityRecordingModel()
    provider = FasterQwen3TTSProvider(config={"device": "cpu"})
    monkeypatch.setattr(provider, "_get_model", lambda: model)

    out = provider.generate_audio(text="hello world", speaker="Maya", language="en")

    assert out["success"] is True
    assert model.calls == [True]


def test_generate_audio_retries_tensor_size_generation_failure(monkeypatch, tmp_path):
    from app.providers import faster_qwen3_tts_provider as provider_module
    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    sample_rate = 12000
    preview_audio = np.sin(np.linspace(0, 20, sample_rate, dtype=np.float32)) * 0.1
    sf.write(tmp_path / "Maya.wav", preview_audio, sample_rate)
    monkeypatch.setattr(provider_module, "VOICE_CLONES_DIR", str(tmp_path))

    class TensorMismatchModel:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def generate_voice_clone(self, **kwargs):
            self.calls.append(dict(kwargs))
            raise RuntimeError("The size of tensor a (431) must match the size of tensor b (216) at non-singleton dimension 3")

    class FreshModel:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def generate_voice_clone(self, **kwargs):
            self.calls.append(dict(kwargs))
            if kwargs.get("non_streaming_mode") is True:
                raise RuntimeError(
                    "The size of tensor a (143) must match the size of tensor b (72) at non-singleton dimension 3"
                )
            return [preview_audio], sample_rate

    broken_model = TensorMismatchModel()
    fresh_parity_model = FreshModel()
    fresh_streaming_layout_model = FreshModel()
    models = [broken_model, fresh_parity_model, fresh_streaming_layout_model]
    reset_calls: list[bool] = []

    provider = FasterQwen3TTSProvider(config={"device": "cpu"})
    monkeypatch.setattr(provider, "_get_model", lambda: models.pop(0))
    monkeypatch.setattr(provider_module, "reset_tts_model_cache", lambda: reset_calls.append(True))

    out = provider.generate_audio(text="hello world", speaker="Maya", language="en")

    assert out["success"] is True
    assert [call["non_streaming_mode"] for call in broken_model.calls] == [True]
    assert [call["non_streaming_mode"] for call in fresh_parity_model.calls] == [True]
    assert [call["non_streaming_mode"] for call in fresh_streaming_layout_model.calls] == [False]
    assert reset_calls == [True, True]


def test_generate_audio_stitches_streaming_fallback_after_tensor_size_failures(monkeypatch, tmp_path):
    from app.providers import faster_qwen3_tts_provider as provider_module
    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    sample_rate = 12000
    preview_audio = np.sin(np.linspace(0, 20, sample_rate, dtype=np.float32)) * 0.1
    chunk_a = preview_audio[:128]
    chunk_b = preview_audio[128:256]
    sf.write(tmp_path / "Maya.wav", preview_audio, sample_rate)
    monkeypatch.setattr(provider_module, "VOICE_CLONES_DIR", str(tmp_path))

    class TensorMismatchModel:
        def __init__(self) -> None:
            self.batch_calls: list[dict[str, object]] = []

        def generate_voice_clone(self, **kwargs):
            self.batch_calls.append(dict(kwargs))
            raise RuntimeError("The size of tensor a (39) must match the size of tensor b (20) at non-singleton dimension 3")

    class StreamingFallbackModel(TensorMismatchModel):
        def __init__(self) -> None:
            super().__init__()
            self.stream_calls: list[dict[str, object]] = []

        def generate_voice_clone_streaming(self, **kwargs):
            self.stream_calls.append(dict(kwargs))
            yield chunk_a, sample_rate, {"chunk": 0}
            yield chunk_b, sample_rate, {"chunk": 1}

    first_model = TensorMismatchModel()
    parity_model = TensorMismatchModel()
    layout_model = TensorMismatchModel()
    streaming_model = StreamingFallbackModel()
    models = [first_model, parity_model, layout_model, streaming_model]
    reset_calls: list[bool] = []

    provider = FasterQwen3TTSProvider(config={"device": "cpu"})
    monkeypatch.setattr(provider, "_get_model", lambda: models.pop(0))
    monkeypatch.setattr(provider_module, "reset_tts_model_cache", lambda: reset_calls.append(True))

    out = provider.generate_audio(text="hello world", speaker="Maya", language="en")

    assert out["success"] is True
    assert len(base64.b64decode(out["audio_base64"])) > 44
    assert [call["non_streaming_mode"] for call in first_model.batch_calls] == [True]
    assert [call["non_streaming_mode"] for call in parity_model.batch_calls] == [True]
    assert [call["non_streaming_mode"] for call in layout_model.batch_calls] == [False]
    assert [call["non_streaming_mode"] for call in streaming_model.stream_calls] == [False]
    assert [call["parity_mode"] for call in streaming_model.stream_calls] == [True]
    assert reset_calls == [True, True, True]


def test_generate_audio_stream_retries_graph_failure_before_first_chunk(monkeypatch, tmp_path):
    from app.providers import faster_qwen3_tts_provider as provider_module
    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    sample_rate = 12000
    preview_audio = np.sin(np.linspace(0, 2, 64, dtype=np.float32)) * 0.1
    sf.write(tmp_path / "Maya.wav", preview_audio, sample_rate)
    monkeypatch.setattr(provider_module, "VOICE_CLONES_DIR", str(tmp_path))

    class PoisonedGraphStreamModel:
        def __init__(self) -> None:
            self.calls: list[bool] = []

        def generate_voice_clone_streaming(self, **kwargs):
            self.calls.append(bool(kwargs.get("parity_mode")))
            raise RuntimeError("Offset increment outside graph capture encountered unexpectedly.")
            yield  # pragma: no cover

    class FreshGraphStreamModel:
        def __init__(self) -> None:
            self.calls: list[bool] = []
            self._cuda_graphs_enabled = True

        def generate_voice_clone_streaming(self, **kwargs):
            self.calls.append(bool(kwargs.get("parity_mode")))
            yield preview_audio, sample_rate, {"mode": "fresh"}

    poisoned_model = PoisonedGraphStreamModel()
    fresh_model = FreshGraphStreamModel()
    models = [poisoned_model, fresh_model]
    reset_calls: list[bool] = []

    provider = FasterQwen3TTSProvider(config={"device": "cpu", "parity_mode": False})
    monkeypatch.setattr(provider, "_get_model", lambda: models.pop(0))
    monkeypatch.setattr(provider_module, "reset_tts_model_cache", lambda: reset_calls.append(True))

    chunks = list(provider.generate_audio_stream(text="hello world", speaker="Maya", language="en"))

    assert len(chunks) == 1
    assert poisoned_model.calls == [False]
    assert fresh_model.calls == [True]
    assert fresh_model._cuda_graphs_enabled is False
    assert reset_calls == [True]
