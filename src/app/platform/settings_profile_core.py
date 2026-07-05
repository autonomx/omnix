"""Core typed Settings Control Center profile models."""
from __future__ import annotations

from pydantic import BaseModel

SETTINGS_PROFILE_KEY = "settings_control_center"
SETTINGS_SCHEMA_VERSION = 1


class ProviderDefaults(BaseModel):
    llm: str = "lmstudio"
    tts: str = "faster-qwen3-tts"
    stt: str = "parakeet"
    image: str = ""
    voice_cloning: str = ""


class ModelDefaults(BaseModel):
    chat: str = ""
    fast: str = ""
    quality: str = ""
    background: str = ""
    embedding: str = ""
    image_prompt: str = ""


class RoutingDefaults(BaseModel):
    fallback_behavior: str = "next-available"
