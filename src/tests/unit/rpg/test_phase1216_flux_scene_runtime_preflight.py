import app.rpg.visual.providers as providers
from app.rpg.visual.flux_pipeline_compat import validate_flux_pipeline_import
from app.rpg.visual.runtime_status import validate_flux_klein_runtime


def test_flux_klein_runtime_preflight_is_ready_for_real_environment():
    """
    This is the real guardrail for the exact failure:
    flux_klein_missing_runtime:diffusers_import_failed:ModuleNotFoundError(...)

    If this test passes, the Python environment running pytest can import the
    FLUX runtime stack required by scene and portrait generation.
    """
    payload = validate_flux_klein_runtime()
    assert payload.get("ready") is True, payload

    compat = validate_flux_pipeline_import()
    assert compat["ok"] is True, compat
    assert compat["details"].get("pipeline_class") in {
        "FluxPipeline",
        "Flux2KleinPipeline",
    }
    assert compat["details"].get("pipeline_resolved_from")


def test_flux_klein_provider_selection_returns_real_provider_when_runtime_is_ready(monkeypatch):
    payload = validate_flux_klein_runtime()
    assert payload.get("ready") is True, payload

    monkeypatch.setattr(
        providers,
        "_visual_settings",
        lambda: {
            "enabled": True,
            "provider": "flux_klein",
            "flux_klein": {},
        },
    )

    providers.unload_image_provider_cache()
    provider = providers.get_image_provider()
    try:
        assert provider.provider_name == "flux_klein"
        assert provider.__class__.__name__ == "FluxKleinImageProvider"
    finally:
        providers.unload_image_provider_cache()