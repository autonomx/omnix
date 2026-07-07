from __future__ import annotations

from PIL import Image

from app.image.providers.base import ImageGenerationResult
import app.image.service as image_service


def test_image_service_resolves_reference_assets_before_provider_call(monkeypatch) -> None:
    reference = Image.new("RGB", (256, 256), "blue")
    captured = {}

    class FakeProvider:
        def generate(self, payload):
            captured.update(payload)
            return ImageGenerationResult(
                ok=True,
                status="completed",
                mime_type="image/png",
                file_path="generated.png",
                revised_prompt=payload["prompt"],
                metadata={"reference_count": 1},
            )

    monkeypatch.setattr(image_service, "get_active_image_provider_name", lambda: "flux_klein")
    monkeypatch.setattr(image_service, "get_provider_config", lambda _name: {})
    monkeypatch.setattr(image_service, "get_or_create_image_provider", lambda _name: FakeProvider())
    monkeypatch.setattr(image_service, "load_image_reference_assets", lambda ids: [reference])
    monkeypatch.setattr(image_service, "close_image_references", lambda images: None)

    result = image_service.generate_image_local(
        {
            "provider": "flux_klein",
            "prompt": "keep the person and change the coat",
            "width": 768,
            "height": 768,
            "reference_asset_ids": ["image:person"],
        }
    )

    assert result.ok is True
    assert captured["image"] is reference
    assert captured["reference_asset_ids"] == ["image:person"]
    assert result.metadata["image_to_image"] is True
    assert result.metadata["reference_asset_ids"] == ["image:person"]
    assert result.metadata["cache_key"] == ""
