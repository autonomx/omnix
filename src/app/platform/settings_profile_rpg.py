"""RPG settings profile model."""
from typing import Any

from pydantic import BaseModel, Field


class RpgSettingsProfile(BaseModel):
    difficulty: str = "normal"
    world_activity: str = "standard"
    economy_pressure: str = "normal"
    combat_lethality: str = "normal"
    companions: bool = True
    permadeath: bool = False
    autosave: bool = True
    validator: bool = True
    background_soft_audit: bool = True
    llm_narration: bool = True
    image_generation: bool = False
    tts: bool = False
    stt: bool = False
    campaign_defaults: dict[str, Any] = Field(default_factory=dict)
    hermes_assist_mode: str = "review_each_step"
