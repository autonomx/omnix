from __future__ import annotations

from app.jobs.image_contracts import ImageGenerateInput


def test_image_job_contract_carries_reference_assets_and_disables_cache() -> None:
    request = ImageGenerateInput(
        prompt="keep the face and change the outfit",
        provider_id="image:flux_klein",
        width=768,
        height=768,
        reference_asset_ids=["image:one", "image:two"],
    )

    payload = request.provider_payload()

    assert payload["provider"] == "flux_klein"
    assert payload["reference_asset_ids"] == ["image:one", "image:two"]
    assert payload["no_cache"] is True
