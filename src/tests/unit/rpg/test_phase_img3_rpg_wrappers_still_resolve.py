from app.rpg.visual.providers.flux_klein_provider import FluxKleinImageProvider
from app.rpg.visual.runtime_status import validate_flux_klein_runtime


def test_legacy_rpg_flux_provider_wrapper_imports():
    assert FluxKleinImageProvider is not None


def test_legacy_rpg_runtime_wrapper_callable():
    assert callable(validate_flux_klein_runtime)
