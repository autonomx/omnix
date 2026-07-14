"""Podcast settings profile model."""
from pydantic import BaseModel, ConfigDict, Field


class PodcastSettingsProfile(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    provider_id: str = Field("", alias="providerId")
    model_id: str = Field("", alias="modelId")
    format: str = "interview"
    duration_minutes: int = Field(5, alias="durationMinutes")
    tone: str = "Professional"
    language: str = "English (US)"
    generation_style: str = Field("automatic", alias="generationStyle")
    autoplay: bool = False
    playback_rate: float = Field(1.0, alias="playbackRate")
    stability: float = 0.72
    similarity: float = 0.78
    effects: list[str] = Field(default_factory=list)
