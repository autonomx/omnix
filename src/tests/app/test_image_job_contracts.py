from app.jobs.image_contracts import ImageGenerateInput, normalize_image_provider_id


def test_image_provider_normalization():
    request = ImageGenerateInput(prompt="test", provider_id="image:flux_klein")
    assert request.provider_key() == "flux_klein"
    assert normalize_image_provider_id("mock") == "mock"
