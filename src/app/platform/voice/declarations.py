"""What the kernel reads about the voice module without loading it (ADR-0016, PA-2.1)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.persistence.declarations import SettingsSection

# Stable effect ids (``effects.EFFECT_IDS``), spelled here so the kernel can read
# settings without loading numpy.
_EFFECT_IDS = ("eq", "deesser", "compressor", "reverb")


class VoiceSettingsProfile(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    language: str = "English"
    stability: float = 0.75
    similarity: float = 0.8
    style: float = 0.35
    speed: float = 1.0
    pitch: float = 0.0
    volume: float = 0.0
    effects: list[str] = Field(default_factory=list)
    streaming: bool = True
    cloning_language: str = Field("English", alias="cloningLanguage")
    cloning_quality: str = Field("High", alias="cloningQuality")

    @field_validator("effects", mode="before")
    @classmethod
    def _effect_ids_only(cls, value: Any) -> list[str]:
        # Display labels were saved while effects did nothing; they load as off.
        if not isinstance(value, (list, tuple)):
            return []
        return [effect for effect in _EFFECT_IDS if effect in {str(item).strip() for item in value}]


SETTINGS = (SettingsSection("voice", VoiceSettingsProfile, order=10),)
