"""Core typed Settings Control Center profile models."""
from __future__ import annotations

from pydantic import BaseModel

SETTINGS_PROFILE_KEY = "settings_control_center"
SETTINGS_SCHEMA_VERSION = 1


class ProviderDefaults(BaseModel):
    llm: str = "lmstudio"
