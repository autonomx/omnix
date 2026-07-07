"""Runtime adapter for centralized Settings Control Center research defaults."""
from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field

from .policy import ResearchPolicy, research_policy_from_env

ResearchProvider = Literal["duckduckgo", "brave", "tavily"]


class ResearchRuntimeSettings(BaseModel):
    default_mode: str = "disabled"
    provider: ResearchProvider = "duckduckgo"
    max_results: int = Field(default=5, ge=1, le=8)
    max_steps: int = Field(default=6, ge=1, le=12)
    max_queries: int = Field(default=5, ge=1, le=10)
    max_sources: int = Field(default=12, ge=1, le=30)
    max_extracts: int = Field(default=8, ge=0, le=20)
    show_diagnostics: bool = True
    deep_enabled: bool = False
    hermes_planner_enabled: bool = False
    policy: ResearchPolicy

    @property
    def credential_configured(self) -> bool:
        if self.provider == "duckduckgo":
            return True
        return bool(os.environ.get("OMNIX_WEB_SEARCH_API_KEY"))

    @property
    def provider_available(self) -> bool:
        return self.provider == "duckduckgo" or self.credential_configured


def load_research_runtime_settings() -> ResearchRuntimeSettings:
    """Load saved profile values, falling back safely to environment policy defaults."""

    environment_policy = research_policy_from_env()
    try:
        from app.shared import load_settings
        from app.platform.settings_profile_repository import load_settings_profile

        profile = load_settings_profile(load_settings())
        assistant = profile.assistant
    except Exception:
        return ResearchRuntimeSettings(policy=environment_policy)

    policy = ResearchPolicy(
        search_cache_ttl_seconds=assistant.research_search_cache_ttl_seconds,
        extraction_cache_ttl_seconds=assistant.research_extraction_cache_ttl_seconds,
        quick_requests_per_minute=environment_policy.quick_requests_per_minute,
        deep_requests_per_hour=environment_policy.deep_requests_per_hour,
        provider_requests_per_minute=environment_policy.provider_requests_per_minute,
        raw_snapshot_retention_days=assistant.research_raw_retention_days,
        source_manifest_retention_days=assistant.research_manifest_retention_days,
        max_active_deep_jobs_per_session=environment_policy.max_active_deep_jobs_per_session,
        planner_receives_conversation_history=False,
        synthesis_receives_raw_page_bodies=False,
    )
    return ResearchRuntimeSettings(
        default_mode=assistant.research_default_mode,
        provider=assistant.research_provider,
        max_results=assistant.research_max_results,
        max_steps=assistant.research_max_steps,
        max_queries=assistant.research_max_queries,
        max_sources=assistant.research_max_sources,
        max_extracts=assistant.research_max_extracts,
        show_diagnostics=assistant.research_show_diagnostics,
        deep_enabled=assistant.research_deep_enabled,
        hermes_planner_enabled=assistant.research_hermes_planner_enabled,
        policy=policy,
    )


def apply_research_planner_environment(settings: ResearchRuntimeSettings) -> None:
    """Expose the central planner preference to the existing planner feature boundary."""

    if settings.hermes_planner_enabled:
        os.environ.setdefault("OMNIX_DEEP_RESEARCH_HERMES_ENABLED", "1")
