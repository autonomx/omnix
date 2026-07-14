"""Voice settings profile model."""
from pydantic import BaseModel, ConfigDict, Field


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
