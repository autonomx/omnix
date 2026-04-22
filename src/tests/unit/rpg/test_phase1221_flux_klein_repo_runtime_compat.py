import json

from app.rpg.visual.flux_pipeline_compat import validate_flux_repo_runtime


def test_validate_flux_repo_runtime_reports_missing_new_diffusers_classes(tmp_path, monkeypatch):
    model_index = {
        "_class_name": "Flux2KleinPipeline",
        "_diffusers_version": "0.37.0.dev0",
        "scheduler": ["diffusers", "FlowMatchEulerDiscreteScheduler"],
        "text_encoder": ["transformers", "Qwen3ForCausalLM"],
        "tokenizer": ["transformers", "Qwen2TokenizerFast"],
        "transformer": ["diffusers", "Flux2Transformer2DModel"],
        "vae": ["diffusers", "AutoencoderKLFlux2"],
    }
    (tmp_path / "model_index.json").write_text(json.dumps(model_index), encoding="utf-8")

    class FakeDiffusers:
        __version__ = "0.35.2"
        FluxPipeline = object
        FlowMatchEulerDiscreteScheduler = object
        # deliberately missing:
        # Flux2Transformer2DModel
        # AutoencoderKLFlux2

    class FakeTransformers:
        __version__ = "4.57.3"
        Qwen3ForCausalLM = object
        Qwen2TokenizerFast = object

    import builtins
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "diffusers":
            return FakeDiffusers
        if name == "transformers":
            return FakeTransformers
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    payload = validate_flux_repo_runtime(str(tmp_path))
    assert payload["ok"] is False
    assert payload["error"].startswith("repo_component_classes_missing:")
    assert "diffusers.Flux2Transformer2DModel" in payload["error"]
    assert "diffusers.AutoencoderKLFlux2" in payload["error"]


def test_validate_flux_repo_runtime_accepts_supported_repo(tmp_path, monkeypatch):
    model_index = {
        "_class_name": "Flux2KleinPipeline",
        "_diffusers_version": "0.37.0.dev0",
        "scheduler": ["diffusers", "FlowMatchEulerDiscreteScheduler"],
        "text_encoder": ["transformers", "Qwen3ForCausalLM"],
        "tokenizer": ["transformers", "Qwen2TokenizerFast"],
        "transformer": ["diffusers", "Flux2Transformer2DModel"],
        "vae": ["diffusers", "AutoencoderKLFlux2"],
    }
    (tmp_path / "model_index.json").write_text(json.dumps(model_index), encoding="utf-8")

    class FakeDiffusers:
        __version__ = "0.37.0"
        Flux2KleinPipeline = object
        FlowMatchEulerDiscreteScheduler = object
        Flux2Transformer2DModel = object
        AutoencoderKLFlux2 = object

    class FakeTransformers:
        __version__ = "4.57.3"
        Qwen3ForCausalLM = object
        Qwen2TokenizerFast = object

    import builtins
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "diffusers":
            return FakeDiffusers
        if name == "transformers":
            return FakeTransformers
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    payload = validate_flux_repo_runtime(str(tmp_path))
    assert payload["ok"] is True, payload
