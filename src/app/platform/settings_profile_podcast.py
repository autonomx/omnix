"""Podcast settings profile model."""
from pydantic import BaseModel, Field


class PodcastSettingsProfile(BaseModel):
    provider_id: str = ""
    model_id: str = ""
    format: str = "interview"
    duration_minutes: int = 5
    tone: str = "Professional"
    language: str = "English (US)"
    generation_style: str = "automatic"
    autoplay: bool = False
    playback_rate: float = 1.0
    stability: float = 0.72
    similarity: float = 0.78
    effects: list[str] = Field(default_factory=list)
