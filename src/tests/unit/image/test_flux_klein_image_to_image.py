from __future__ import annotations

from types import SimpleNamespace

from PIL import Image

from app.image.providers import flux_klein_provider as flux_module
from app.image.providers.flux_klein_provider import FluxKleinImageProvider


def test_flux_provider_forwards_reference_image_to_pipeline(tmp_path, monkeypatch) -> None:
    captured = {}

    class FakePipeline:
        def __call__(
            self,
            *,
            image=None,
            prompt=None,
            width=None,
            height=None,
            num_inference_steps=None,
            guidance_scale=None,
            generator=None,
        ):
            captured.update(
                {
                    "image": image,
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    "num_inference_steps": num_inference_steps,
                    "guidance_scale": guidance_scale,
                    "generator": generator,
                }
            )
            return SimpleNamespace(images=[Image.new("RGB", (width, height), "purple")])

    provider = FluxKleinImageProvider({"device": "cpu"})
    provider._pipeline = FakePipeline()
    provider._memory_mode = "cpu"
    reference = Image.new("RGB", (512, 512), "blue")
    monkeypatch.setattr(flux_module, "generated_images_root", lambda: tmp_path)
    monkeypatch.setattr(flux_module, "_release_generation_memory", lambda: None)

    result = provider.generate(
        {
            "prompt": "keep the character and change the clothing",
            "width": 768,
            "height": 768,
            "num_inference_steps": 4,
            "guidance_scale": 1.0,
            "image": reference,
        }
    )

    assert result.ok is True
    assert captured["image"] is reference
    assert captured["prompt"] == "keep the character and change the clothing"
    assert result.metadata["image_to_image"] is True
    assert result.metadata["reference_count"] == 1
