"""RPG settings profile model."""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RpgSettingsProfile(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    difficulty: str = "normal"
    world_activity: str = Field("standard", alias="worldActivity")
    economy_pressure: str = Field("normal", alias="economyPressure")
    combat_lethality: str = Field("normal", alias="combatLethality")
    companions: bool = True
    permadeath: bool = False
    autosave: bool = True
    validator: bool = True
    background_soft_audit: bool = Field(True, alias="backgroundSoftAudit")
    llm_narration: bool = Field(True, alias="llmNarration")
    image_generation: bool = Field(False, alias="imageGeneration")
    tts: bool = False
    stt: bool = False
    campaign_defaults: dict[str, Any] = Field(default_factory=dict, alias="campaignDefaults")
    hermes_assist_mode: str = Field("review_each_step", alias="hermesAssistMode")
