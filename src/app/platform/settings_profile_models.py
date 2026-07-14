from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .settings_profile_capture import ImageSettingsProfile, StorageSettingsProfile, SttSettingsProfile
from .settings_profile_core import SETTINGS_SCHEMA_VERSION, ProviderConfigs
from .settings_profile_experience import AppearanceSettingsProfile, AssistantSettingsProfile
from .settings_profile_global import GlobalSettingsProfile
from .settings_profile_podcast import PodcastSettingsProfile
from .settings_profile_rpg import RpgSettingsProfile
from .settings_profile_story import StorytellerSettingsProfile
from .settings_profile_voice import VoiceSettingsProfile


class SettingsProfile(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    schema_version: int = Field(SETTINGS_SCHEMA_VERSION, alias="schemaVersion")
    revision: str = "default"
    global_settings: GlobalSettingsProfile = Field(default_factory=GlobalSettingsProfile, alias="global")
    provider_configs: ProviderConfigs = Field(default_factory=ProviderConfigs, alias="providerConfigs")
    appearance: AppearanceSettingsProfile = Field(default_factory=AppearanceSettingsProfile)
    assistant: AssistantSettingsProfile = Field(default_factory=AssistantSettingsProfile)
    voice: VoiceSettingsProfile = Field(default_factory=VoiceSettingsProfile)
    storyteller: StorytellerSettingsProfile = Field(default_factory=StorytellerSettingsProfile)
    podcast: PodcastSettingsProfile = Field(default_factory=PodcastSettingsProfile)
    rpg: RpgSettingsProfile = Field(default_factory=RpgSettingsProfile)
    image: ImageSettingsProfile = Field(default_factory=ImageSettingsProfile)
    stt: SttSettingsProfile = Field(default_factory=SttSettingsProfile)
    storage: StorageSettingsProfile = Field(default_factory=StorageSettingsProfile)


class SettingsProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_revision: str | None = None
    patch: dict[str, Any] = Field(default_factory=dict)
