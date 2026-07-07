from __future__ import annotations

from app.image.models import ImageGenerationRequest
from app.image.service import _map_to_provider_payload
from app.image.style import apply_image_style, normalize_image_style


def test_anime_style_adds_explicit_non_photographic_directive() -> None:
    styled = apply_image_style("a warrior in a tavern", "anime")

    assert "Japanese anime illustration" in styled
    assert "not a photograph" in styled
    assert styled.endswith("Subject and scene: a warrior in a tavern")


def test_supported_styles_produce_distinct_provider_prompts() -> None:
    prompt = "a castle at dusk"

    anime = apply_image_style(prompt, "anime")
    photo = apply_image_style(prompt, "photorealistic")
    watercolor = apply_image_style(prompt, "watercolor")

    assert len({anime, photo, watercolor}) == 3
    assert "photorealistic photograph" in photo
    assert "traditional watercolor painting" in watercolor


def test_provider_payload_uses_selected_style_directive() -> None:
    request = ImageGenerationRequest(
        prompt="a city skyline",
        style="anime",
        width=768,
        height=768,
        steps=4,
    )

    payload = _map_to_provider_payload(request, {})

    assert payload["style"] == "anime"
    assert payload["prompt"] != request.prompt
    assert "Japanese anime illustration" in payload["prompt"]
    assert payload["prompt"].endswith("Subject and scene: a city skyline")


def test_style_aliases_are_normalized() -> None:
    assert normalize_image_style("Japanese-Anime") == "anime"
    assert normalize_image_style("digital_art") == "digital illustration"
