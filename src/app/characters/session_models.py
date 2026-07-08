"""Session-level Character Mode API contracts."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import InteractionMode, TranscriptPolicy


class SetSessionInteractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction_mode: InteractionMode
    character_id: str | None = Field(default=None, max_length=160)
    voice_asset_id: str | None = Field(default=None, max_length=240)
    read_memory: bool = False
    write_memory: bool = False
    transcript_policy: TranscriptPolicy = "persistent"
    continue_topic: bool = False

    @model_validator(mode="after")
    def validate_selection(self) -> "SetSessionInteractionRequest":
        if self.interaction_mode == "character" and not self.character_id:
            raise ValueError("character mode requires character_id")
        if self.interaction_mode == "system" and self.character_id:
            raise ValueError("system mode cannot select character_id")
        if self.interaction_mode == "system" and (self.read_memory or self.write_memory):
            raise ValueError("system memory is controlled by normal Chat memory settings")
        return self
