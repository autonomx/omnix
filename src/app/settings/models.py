"""Settings API DTOs owned by the settings kernel."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SettingsPayload(BaseModel):
    success: bool = True
    provider: str
    audio_provider_tts: str
    audio_provider_stt: str
    image_enabled: bool
    rpg_visual_enabled: bool
    worker_urls: dict[str, str] = Field(default_factory=dict)
    hermes_status: dict[str, Any] = Field(default_factory=dict)
    hermes_commands: dict[str, str] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)
    # Each setting's revision (0 = never saved); send them back in a save so a
    # concurrent change is refused instead of overwritten.
    revisions: dict[str, int] = Field(default_factory=dict)


class SettingsSaveResponse(BaseModel):
    success: bool = True
