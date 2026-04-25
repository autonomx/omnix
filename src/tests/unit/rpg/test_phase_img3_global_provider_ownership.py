from app.image.providers.flux_klein_provider import FluxKleinImageProvider
from app.image.service import _load_provider


def test_image_service_loads_global_flux_provider():
    provider = _load_provider("flux_klein", {})
    assert isinstance(provider, FluxKleinImageProvider)
