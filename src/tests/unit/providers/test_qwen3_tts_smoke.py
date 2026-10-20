from __future__ import annotations

import base64
import traceback

import numpy as np
import pytest
import soundfile as sf


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


def test_faster_qwen3_effective_generation_parameters_include_configured_defaults() -> None:
    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    first = FasterQwen3TTSProvider(config={
        "device": "cpu", "temperature": 0.71, "parity_mode": False,
    })
    second = FasterQwen3TTSProvider(config={
        "device": "cpu", "temperature": 0.93, "parity_mode": False,
    })
    first_settings = first.resolve_generation_parameters({})
    second_settings = second.resolve_generation_parameters({})

    assert first_settings["temperature"] == 0.71
    assert second_settings["temperature"] == 0.93
    assert first_settings["parity_mode"] is False
    assert first_settings["_generation_strategy_revision"] == first.generation_strategy_revision
    assert first_settings != second_settings
    assert first.resolve_generation_parameters({"temperature": 0.5})["temperature"] == 0.5


@pytest.mark.smoke
def test_qwen3_generate_minimal_call(monkeypatch, tmp_path):
    """
    Optional but VERY useful:
    verifies generation path wiring without heavy compute.

    We monkeypatch the model to avoid real inference cost.
    """

    from app.providers import faster_qwen3_tts_provider as provider_module
    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    provider = FasterQwen3TTSProvider(config={"device": "cpu"})

    sample_rate = 12000
    samples = np.linspace(-0.1, 0.1, sample_rate // 4, dtype=np.float32)
    sf.write(tmp_path / "test.wav", samples, sample_rate)
    monkeypatch.setattr(provider_module, "VOICE_CLONES_DIR", str(tmp_path))

    class DummyModel:
        def generate_voice_clone(self, **kwargs):
            return [samples], sample_rate

    monkeypatch.setattr(provider, "_get_model", lambda: DummyModel())

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

    assert out["success"] is True
    assert base64.b64decode(out["audio_base64"])[:4] == b"RIFF"


@pytest.mark.smoke
def test_generate_audio_marks_reference_fallback_as_failure_when_model_unavailable(monkeypatch, tmp_path):
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

    assert out["success"] is False
    assert out["is_fallback"] is True
    assert "model unavailable" in out["error"]
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


def test_generate_audio_can_disable_cuda_graphs_before_generation(monkeypatch, tmp_path):
    from app.providers import faster_qwen3_tts_provider as provider_module
    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    sample_rate = 12000
    preview_audio = np.sin(np.linspace(0, 20, sample_rate, dtype=np.float32)) * 0.1
    sf.write(tmp_path / "Studio.wav", preview_audio, sample_rate)
    monkeypatch.setattr(provider_module, "VOICE_CLONES_DIR", str(tmp_path))

    class GraphRecordingModel:
        _cuda_graphs_enabled = True

        def __init__(self):
            self.calls = []

        def generate_voice_clone(self, **kwargs):
            self.calls.append(kwargs)
            return [preview_audio], sample_rate

    model = GraphRecordingModel()
    provider = FasterQwen3TTSProvider(config={"device": "cpu"})
    monkeypatch.setattr(provider, "_get_model", lambda: model)

    out = provider.generate_audio(
        text="stable studio generation",
        speaker="Studio",
        language="en",
        use_cuda_graphs=False,
    )

    assert out["success"] is True
    # The request decodes without graphs (parity mode); the shared model keeps its graphs
    # for later requests, which would otherwise replay a graph that was never captured.
    assert model.calls and all(call.get("parity_mode") is True for call in model.calls)
    assert model._cuda_graphs_enabled is True


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


def test_a_blend_survives_the_streaming_fallback(monkeypatch, tmp_path):
    """A blended voice keeps its blend when a CUDA-graph failure falls back to streaming."""
    import ast
    from pathlib import Path

    from app.providers import faster_qwen3_tts_provider as provider_module
    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    sample_rate = 12000
    audio = np.sin(np.linspace(0, 20, sample_rate, dtype=np.float32)) * 0.1
    for name in ("Maya", "Nate"):
        sf.write(tmp_path / f"{name}.wav", audio, sample_rate)
    monkeypatch.setattr(provider_module, "VOICE_CLONES_DIR", str(tmp_path))

    class Broken:
        def generate_voice_clone(self, **kwargs):
            raise RuntimeError("The size of tensor a (39) must match the size of tensor b (20) at non-singleton dimension 3")

    class Streaming(Broken):
        def __init__(self) -> None:
            self.stream_calls: list[dict[str, object]] = []

        def generate_voice_clone_streaming(self, **kwargs):
            self.stream_calls.append(dict(kwargs))
            yield audio[:256], sample_rate, {"chunk": 0}

    references = {f"voice-cloning:{name}": (str(tmp_path / f"{name}.wav"), "") for name in ("Maya", "Nate")}
    monkeypatch.setattr(provider_module, "_clone_reference", lambda speaker: references.get(speaker, (None, "")))
    streaming = Streaming()
    models = [Broken(), Broken(), Broken(), streaming]
    provider = FasterQwen3TTSProvider(config={"device": "cpu"})
    monkeypatch.setattr(provider, "_get_model", lambda: models.pop(0))
    monkeypatch.setattr(provider_module, "reset_tts_model_cache", lambda: None)
    out = provider.generate_audio(text="hello", speaker="voice-cloning:Maya", language="en",
                                  speaker_blend=[{"speaker": "voice-cloning:Maya", "weight": 0.5},
                                                 {"speaker": "voice-cloning:Nate", "weight": 0.5}])
    assert out["success"] is True
    blend = streaming.stream_calls[0]["speaker_blend"]
    assert [Path(path).stem for path, _weight in blend] == ["Maya", "Nate"] and streaming.stream_calls[0]["xvec_only"] is True
    # The real streaming method takes it too (checked in source: importing the model needs torch).
    source = Path(provider_module.__file__).parent / "vendor" / "faster_qwen3_tts" / "model.py"
    method = next(node for node in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
                  if isinstance(node, ast.FunctionDef) and node.name == "generate_voice_clone_streaming")
    assert "speaker_blend" in [arg.arg for arg in method.args.args + method.args.kwonlyargs]
