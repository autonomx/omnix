from app.image.providers.registry import (
    is_supported_image_provider,
    list_image_providers,
)


def test_list_image_providers_contains_flux_and_mock():
    providers = list_image_providers()
    keys = {item["key"] for item in providers}
    assert "flux_klein" in keys
    assert "mock" in keys


def test_is_supported_image_provider():
    assert is_supported_image_provider("flux_klein") is True
    assert is_supported_image_provider("mock") is True
    assert is_supported_image_provider("nope") is False
