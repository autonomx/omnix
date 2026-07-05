"""Voice settings profile model."""
from pydantic import BaseModel, Field


class VoiceSettingsProfile(BaseModel):
    language: str = "English"
    stability: float = 0.75
    similarity: float = 0.8
    style: float = 0.35
    speed: float = 1.0
    pitch: float = 0.0
    volume: float = 0.0
    effects: list[str] = Field(default_factory=list)
    streaming: bool = True
    cloning_language: str = "English"
    cloning_quality: str = "High"
