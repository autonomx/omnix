"""Credential-safe runtime status for Web Research settings and capabilities."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .policy import privacy_contract
from .quick_search import provider_coverage
from .settings import ResearchRuntimeSettings, load_research_runtime_settings


class ResearchProviderStatus(BaseModel):
    provider: str
    available: bool
    credential_required: bool
    credential_configured: bool
    coverage: str


class ResearchBudgetStatus(BaseModel):
    quick_max_results: int
    deep_max_steps: int
    deep_max_queries: int
    deep_max_sources: int
    deep_max_extracts: int


class ResearchRetentionStatus(BaseModel):
    search_cache_ttl_seconds: int
    extraction_cache_ttl_seconds: int
    raw_snapshot_retention_days: int
    source_manifest_retention_days: int


class ResearchRuntimeStatus(BaseModel):
    default_mode: str
    provider: ResearchProviderStatus
    budgets: ResearchBudgetStatus
    retention: ResearchRetentionStatus
    deep_enabled: bool
    hermes_planner_enabled: bool
    diagnostics_enabled: bool
    privacy: dict[str, object] = Field(default_factory=dict)


def research_runtime_status(
    settings: ResearchRuntimeSettings | None = None,
) -> ResearchRuntimeStatus:
    resolved = settings or load_research_runtime_settings()
    return ResearchRuntimeStatus(
        default_mode=resolved.default_mode,
        provider=ResearchProviderStatus(
            provider=resolved.provider,
            available=resolved.provider_available,
            credential_required=resolved.provider != "duckduckgo",
            credential_configured=resolved.credential_configured,
            coverage=provider_coverage(resolved.provider),
        ),
        budgets=ResearchBudgetStatus(
            quick_max_results=resolved.max_results,
            deep_max_steps=resolved.max_steps,
            deep_max_queries=resolved.max_queries,
            deep_max_sources=resolved.max_sources,
            deep_max_extracts=resolved.max_extracts,
        ),
        retention=ResearchRetentionStatus(
            search_cache_ttl_seconds=resolved.policy.search_cache_ttl_seconds,
            extraction_cache_ttl_seconds=resolved.policy.extraction_cache_ttl_seconds,
            raw_snapshot_retention_days=resolved.policy.raw_snapshot_retention_days,
            source_manifest_retention_days=resolved.policy.source_manifest_retention_days,
        ),
        deep_enabled=resolved.deep_enabled,
        hermes_planner_enabled=resolved.hermes_planner_enabled,
        diagnostics_enabled=resolved.show_diagnostics,
        privacy=privacy_contract(resolved.policy),
    )
