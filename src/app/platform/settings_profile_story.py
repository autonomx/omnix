"""Storyteller settings profile model."""
from pydantic import BaseModel, Field


class StorytellerSettingsProfile(BaseModel):
    provider_id: str = ""
    model_id: str = ""
    tone: str = "Cozy"
    writing_style: str = "Lyrical & Descriptive"
    read_speed: float = 1.0
    pause_paragraph_ms: int = 500
    pause_chapter_ms: int = 1200
    read_chapter_titles: bool = True
    read_style_preset: str = "Dramatic audiobook"
    pronunciation: dict[str, str] = Field(default_factory=dict)
