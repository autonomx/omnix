"""Storyteller settings profile model."""
from pydantic import BaseModel, ConfigDict, Field


class StorytellerSettingsProfile(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    provider_id: str = Field("", alias="providerId")
    model_id: str = Field("", alias="modelId")
    tone: str = "Cozy"
    writing_style: str = Field("Lyrical & Descriptive", alias="writingStyle")
    read_speed: float = Field(1.0, alias="readSpeed")
    pause_paragraph_ms: int = Field(500, alias="pauseParagraphMs")
    pause_chapter_ms: int = Field(1200, alias="pauseChapterMs")
    read_chapter_titles: bool = Field(True, alias="readChapterTitles")
    read_style_preset: str = Field("Dramatic audiobook", alias="readStylePreset")
    pronunciation: dict[str, str] = Field(default_factory=dict)
