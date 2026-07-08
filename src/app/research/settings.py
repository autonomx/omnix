"""Runtime adapter for centralized Settings Control Center research defaults."""
from __future__ import annotations

import os
from typing import Literal, cast

from pydantic import BaseModel, Field

from .policy import ResearchPolicy, research_policy_from_env

ResearchProvider = Literal["duckduckgo", "brave", "tavily", "playwright"]


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
        if self.provider in {"duckduckgo", "playwright"}:
            return True
        return bool(os.environ.get("OMNIX_WEB_SEARCH_API_KEY"))

    @property
    def provider_available(self) -> bool:
        return self.provider in {"duckduckgo", "playwright"} or self.credential_configured

    @property
    def effective_provider(self) -> ResearchProvider:
        env_provider = os.environ.get("OMNIX_WEB_SEARCH_PROVIDER", "").strip().lower()
        if (
            self.provider == "duckduckgo"
            and (
                env_provider == "playwright"
                or (env_provider in {"brave", "tavily"} and os.environ.get("OMNIX_WEB_SEARCH_API_KEY"))
            )
        ):
            return cast(ResearchProvider, env_provider)
        return self.provider


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
        raw_snapshot_retention_days=assistant.research_raw_retention_days,
        source_manifest_retention_days=assistant.research_manifest_retention_days,
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
