"""User experience settings profile models."""
from pydantic import BaseModel

from app.research import ResearchMode


class AppearanceSettingsProfile(BaseModel):
    mode: str = "system"
    density: str = "comfortable"
    reduce_motion: bool = False
    live_captions: bool = True


class AssistantSettingsProfile(BaseModel):
    personality_id: str = "omnix-default"
    custom_personality: str = ""
    voice_id: str = ""
    auto_speak_replies: bool = False
    speech_language: str = "en-US"
    streaming_audio: bool = True
    research_default_mode: ResearchMode = "disabled"
