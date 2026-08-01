from __future__ import annotations

from PIL import Image

from app.image.output_normalization import normalize_generated_image


def test_transparent_provider_output_becomes_visible_rgb_image():
    source = Image.new("RGBA", (4, 4), (218, 45, 63, 0))

    normalized, metadata = normalize_generated_image(source)

    assert normalized.mode == "RGB"
    assert normalized.getpixel((0, 0)) == (218, 45, 63)
    assert metadata["source_mode"] == "RGBA"
    assert metadata["alpha_removed"] is True
    assert metadata["resized_for_browser"] is False


def test_oversized_provider_output_is_bounded_without_changing_aspect_ratio():
    source = Image.new("RGB", (1000, 100), (12, 34, 56))

    normalized, metadata = normalize_generated_image(
        source,
        max_edge=100,
        max_pixels=10_000,
    )

    assert normalized.size == (100, 10)
    assert metadata["source_width"] == 1000
    assert metadata["source_height"] == 100
    assert metadata["normalized_width"] == 100
    assert metadata["normalized_height"] == 10
    assert metadata["resized_for_browser"] is True
