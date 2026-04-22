from app.image.providers.mock_provider import MockImageProvider


def test_mock_provider_generates_image_result():
    provider = MockImageProvider({})
    result = provider.generate({
        "prompt": "test mock provider",
        "width": 256,
        "height": 256,
        "kind": "image",
    })
    assert result.ok is True
    assert result.image_bytes is not None
    assert result.file_path
    assert result.mime_type == "image/png"
