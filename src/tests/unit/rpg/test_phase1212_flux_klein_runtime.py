import importlib


def test_flux_klein_runtime_dependencies_are_importable():
    """
    Hard-fail smoke test.

    This should run in the same Python environment used to start the app.
    If this test fails, the portrait-generation runtime is not actually fixed.
    """
    diffusers = importlib.import_module("diffusers")
    torch = importlib.import_module("torch")
    transformers = importlib.import_module("transformers")
    accelerate = importlib.import_module("accelerate")
    safetensors = importlib.import_module("safetensors")

    assert diffusers is not None
    assert torch is not None
    assert transformers is not None
    assert accelerate is not None
    assert safetensors is not None

    from diffusers import Flux2KleinPipeline

    assert Flux2KleinPipeline is not None


from app.rpg.visual.providers.flux_klein_provider import FluxKleinImageProvider


def test_flux_klein_provider_surfaces_missing_runtime_error(monkeypatch):
    provider = FluxKleinImageProvider({})

    def _boom():
        raise RuntimeError("flux_klein_missing_runtime:No module named 'diffusers'")

    monkeypatch.setattr(provider, "_ensure_pipeline", _boom)

    result = provider.generate(
        prompt="guard captain portrait",
        seed=123,
        style="rpg-portrait",
        model="black-forest-labs/FLUX.2-klein-4B",
        kind="character_portrait",
        target_id="npc_guard_captain",
    )

    assert result.ok is False
    assert result.status == "failed"
    assert result.error.startswith("flux_klein_missing_runtime:")