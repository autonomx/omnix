"""User experience settings profile models."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.research import ResearchMode


class AppearanceSettingsProfile(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    mode: str = "system"
    theme: str = "aurora"
    density: str = "comfortable"
    reduce_motion: bool = Field(False, alias="reduceMotion")
    live_captions: bool = Field(True, alias="liveCaptions")


class AssistantSettingsProfile(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    personality_id: str = Field(default="omnix-default", alias="personalityId")
    custom_personality: str = Field(default="", alias="customPersonality")
    voice_id: str = Field(default="", alias="voiceId")
    auto_speak_replies: bool = Field(default=False, alias="autoSpeakReplies")
    speech_language: str = Field(default="en-US", alias="speechLanguage")
    streaming_audio: bool = Field(default=True, alias="streamingAudio")

    research_default_mode: ResearchMode = Field(default="disabled", alias="researchDefaultMode")
    research_provider: Literal["duckduckgo", "brave", "tavily", "playwright"] = Field(
        default="duckduckgo",
        alias="researchProvider",
    )
    research_max_results: int = Field(default=5, ge=1, le=8, alias="researchMaxResults")
    research_max_steps: int = Field(default=6, ge=1, le=12, alias="researchMaxSteps")
    research_max_queries: int = Field(default=5, ge=1, le=10, alias="researchMaxQueries")
    research_max_sources: int = Field(default=12, ge=1, le=30, alias="researchMaxSources")
    research_max_extracts: int = Field(default=8, ge=0, le=20, alias="researchMaxExtracts")
    research_search_cache_ttl_seconds: int = Field(
        default=300,
        ge=1,
        le=86400,
        alias="researchSearchCacheTtlSeconds",
    )
    research_extraction_cache_ttl_seconds: int = Field(
        default=3600,
        ge=1,
        le=604800,
        alias="researchExtractionCacheTtlSeconds",
    )
    research_raw_retention_days: int = Field(
        default=7,
        ge=0,
        le=365,
        alias="researchRawRetentionDays",
    )
    research_manifest_retention_days: int = Field(
        default=30,
        ge=1,
        le=3650,
        alias="researchManifestRetentionDays",
    )
    research_show_diagnostics: bool = Field(default=True, alias="researchShowDiagnostics")
    research_deep_enabled: bool = Field(default=False, alias="researchDeepEnabled")
    research_hermes_planner_enabled: bool = Field(
        default=False,
        alias="researchHermesPlannerEnabled",
    )
