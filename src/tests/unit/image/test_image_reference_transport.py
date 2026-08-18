from __future__ import annotations

import app.image.reference_transport as reference_transport
import app.image.service as image_service
import app.image_http_client as image_http_client
import pytest
from app.image.providers.base import ImageGenerationResult

Image = pytest.importorskip("PIL.Image")


def test_reference_transport_round_trips_normalized_images(monkeypatch) -> None:
    source = Image.new("RGB", (320, 240), "blue")
    monkeypatch.setattr(reference_transport, "load_image_reference_assets", lambda _ids: [source])
    monkeypatch.setattr(reference_transport, "close_image_references", lambda _images: None)

    payloads = reference_transport.encode_reference_assets(["image:portrait"])
    decoded = reference_transport.decode_reference_payloads(payloads)
    try:
        assert len(payloads) == 1
        assert len(decoded) == 1
        assert decoded[0].mode == "RGB"
        assert decoded[0].size == (320, 240)
    finally:
        for image in decoded:
            image.close()
        source.close()


def test_http_client_embeds_reference_images_before_service_request(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(image_http_client, "is_image_generation_enabled", lambda: True)
    monkeypatch.setattr(reference_transport, "encode_reference_assets", lambda _ids: ["encoded-reference"])

    def post(path: str, payload: dict, timeout: float) -> dict:
        captured.update({"path": path, "payload": payload, "timeout": timeout})
        return {"ok": True}

    monkeypatch.setattr(image_http_client, "post_image_service", post)

    result = image_http_client.generate_image_via_service(
        {
            "prompt": "preserve the portrait",
            "reference_asset_ids": ["image:portrait"],
        }
    )

    assert result == {"ok": True}
    assert captured["path"] == "/generate"
    assert captured["timeout"] == 900.0
    assert captured["payload"][reference_transport.REFERENCE_IMAGES_PAYLOAD_KEY] == ["encoded-reference"]


def test_image_service_prefers_transported_references_over_local_manifest(monkeypatch) -> None:
    source = Image.new("RGB", (256, 256), "green")
    monkeypatch.setattr(reference_transport, "load_image_reference_assets", lambda _ids: [source])
    monkeypatch.setattr(reference_transport, "close_image_references", lambda _images: None)
    payloads = reference_transport.encode_reference_assets(["image:portrait"])
    source.close()

    captured: dict[str, object] = {}

    class FakeProvider:
        def generate(self, payload):
            captured["reference_size"] = payload["image"].size
            captured["reference_asset_ids"] = payload["reference_asset_ids"]
            return ImageGenerationResult(
                ok=True,
                status="completed",
                mime_type="image/png",
                file_path="generated.png",
                revised_prompt=payload["prompt"],
            )

    monkeypatch.setattr(image_service, "get_active_image_provider_name", lambda: "flux_klein")
    monkeypatch.setattr(image_service, "get_provider_config", lambda _name: {})
    monkeypatch.setattr(image_service, "is_image_provider_loaded", lambda _name: True)
    monkeypatch.setattr(image_service, "get_or_create_image_provider", lambda _name: FakeProvider())

    def fail_manifest_lookup(_ids):
        raise AssertionError("standalone service must not re-resolve backend asset IDs")

    monkeypatch.setattr(image_service, "load_image_reference_assets", fail_manifest_lookup)

    result = image_service.generate_image_local(
        {
            "provider": "flux_klein",
            "prompt": "keep identity and change only the mouth",
            "reference_asset_ids": ["image:portrait"],
            reference_transport.REFERENCE_IMAGES_PAYLOAD_KEY: payloads,
        }
    )

    assert result.ok is True
    assert captured["reference_size"] == (256, 256)
    assert captured["reference_asset_ids"] == ["image:portrait"]
    assert result.metadata["image_to_image"] is True
