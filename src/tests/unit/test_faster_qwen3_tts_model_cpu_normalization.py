from __future__ import annotations

import types


def test_from_pretrained_cpu_does_not_build_cuda_graphs(monkeypatch):
    from app.providers.vendor.faster_qwen3_tts.model import FasterQwen3TTS

    captured = {}

    class FakeQwen3TTSModel:
        @classmethod
        def from_pretrained(cls, model_name, device_map=None, torch_dtype=None, attn_implementation=None):
            captured["model_name"] = model_name
            captured["device_map"] = device_map
            captured["torch_dtype"] = torch_dtype
            captured["attn_implementation"] = attn_implementation

            talker = types.SimpleNamespace(
                code_predictor=types.SimpleNamespace(model=types.SimpleNamespace(config=types.SimpleNamespace())),
                model=object(),
            )
            config = types.SimpleNamespace(talker_config=types.SimpleNamespace(hidden_size=128))
            return types.SimpleNamespace(model=types.SimpleNamespace(talker=talker, config=config))

    fake_qwen_tts_module = types.SimpleNamespace(Qwen3TTSModel=FakeQwen3TTSModel)

    monkeypatch.setattr(
        "app.providers.vendor.faster_qwen3_tts.model._ensure_transformers_qwen3_compat",
        lambda: None,
        raising=False,
    )
    monkeypatch.setattr(
        "torch.cuda.is_available",
        lambda: False,
        raising=False,
    )

    import sys
    sys.modules["app.providers.vendor.qwen_tts"] = fake_qwen_tts_module

    model = FasterQwen3TTS.from_pretrained(
        model_name="Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        device="cpu",
        dtype="float32",
        max_seq_len=1024,
    )

    assert model is not None
    assert model.device == "cpu"
    assert model.predictor_graph is None
    assert model.talker_graph is None
    assert model._cuda_graphs_enabled is False
    assert captured["device_map"] == "cpu"


def test_from_pretrained_cuda_path_keeps_graph_build(monkeypatch):
    from app.providers.vendor.faster_qwen3_tts.model import FasterQwen3TTS

    captured = {"predictor_graph_called": False, "talker_graph_called": False}

    class FakeQwen3TTSModel:
        @classmethod
        def from_pretrained(cls, model_name, device_map=None, torch_dtype=None, attn_implementation=None):
            talker = types.SimpleNamespace(
                code_predictor=types.SimpleNamespace(model=types.SimpleNamespace(config=types.SimpleNamespace())),
                model=object(),
            )
            config = types.SimpleNamespace(talker_config=types.SimpleNamespace(hidden_size=128))
            return types.SimpleNamespace(model=types.SimpleNamespace(talker=talker, config=config))

    class FakePredictorGraph:
        def __init__(self, *args, **kwargs):
            captured["predictor_graph_called"] = True

    class FakeTalkerGraph:
        def __init__(self, *args, **kwargs):
            captured["talker_graph_called"] = True

    fake_qwen_tts_module = types.SimpleNamespace(Qwen3TTSModel=FakeQwen3TTSModel)

    monkeypatch.setattr(
        "app.providers.vendor.faster_qwen3_tts.model._ensure_transformers_qwen3_compat",
        lambda: None,
        raising=False,
    )
    monkeypatch.setattr(
        "torch.cuda.is_available",
        lambda: True,
        raising=False,
    )

    import sys
    sys.modules["app.providers.vendor.qwen_tts"] = fake_qwen_tts_module
    sys.modules["app.providers.vendor.faster_qwen3_tts.predictor_graph"] = types.SimpleNamespace(PredictorGraph=FakePredictorGraph)
    sys.modules["app.providers.vendor.faster_qwen3_tts.talker_graph"] = types.SimpleNamespace(TalkerGraph=FakeTalkerGraph)

    model = FasterQwen3TTS.from_pretrained(
        model_name="Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        device="cuda",
        dtype="float32",
        max_seq_len=1024,
    )

    assert model is not None
    assert model.device == "cuda"
    assert model._cuda_graphs_enabled is True
    assert captured["predictor_graph_called"] is True
    assert captured["talker_graph_called"] is True