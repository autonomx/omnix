from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.characters.avatar_generation_models import CreateCharacterAvatarGenerationRequest


def test_avatar_generation_defaults_to_flux_image_provider() -> None:
    request = CreateCharacterAvatarGenerationRequest()

    assert request.provider_id == "image:flux_klein"
    assert request.unload_after_generation is False


def test_avatar_generation_normalizes_legacy_flux_provider_key() -> None:
    request = CreateCharacterAvatarGenerationRequest(provider_id="FLUX_KLEIN")

    assert request.provider_id == "image:flux_klein"


@pytest.mark.parametrize("provider_id", ["image:z_image_turbo", "image:krea2_turbo"])
def test_avatar_generation_rejects_text_to_image_only_providers(provider_id: str) -> None:
    with pytest.raises(ValidationError, match="character_avatar_requires_flux_klein"):
        CreateCharacterAvatarGenerationRequest(provider_id=provider_id)
