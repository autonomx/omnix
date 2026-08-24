from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assistant_context.models import AssistantContextBuildResult
from app.assistant_context.routes import register_assistant_context_routes
from app.chat import ChatSessionStore, CreateChatSessionRequest
from app.jobs import SQLiteJobStore
from app.research.compatibility import reset_research_compatibility_telemetry
from app.research.policy import ResearchPolicy
from app.research.release_policy import ResearchReleasePolicy
from app.research.settings import ResearchRuntimeSettings, load_research_runtime_settings


def runtime_settings(**overrides) -> ResearchRuntimeSettings:
    payload = {
        "default_mode": "quick",
        "provider": "brave",
        "provider_fallbacks": ("playwright", "duckduckgo"),
        "max_results": 7,
        "max_steps": 9,
        "max_queries": 4,
        "max_sources": 18,
        "max_extracts": 6,
        "show_diagnostics": True,
        "deep_enabled": True,
        "hermes_planner_enabled": True,
        "policy": ResearchPolicy(
            search_cache_ttl_seconds=901,
            extraction_cache_ttl_seconds=1802,
            raw_snapshot_retention_days=3,
            source_manifest_retention_days=44,
        ),
    }
    payload.update(overrides)
    return ResearchRuntimeSettings(**payload)


def test_runtime_settings_load_saved_profile_values(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.shared.load_settings",
        lambda: {
            "provider": "lmstudio",
            "settings_control_center": {
                "assistant": {
                    "researchDefaultMode": "deep",
                    "researchProvider": "tavily",
                    "researchProviderFallbacks": ["playwright", "duckduckgo"],
                    "researchMaxResults": 6,
                    "researchMaxSteps": 10,
                    "researchMaxQueries": 7,
                    "researchMaxSources": 20,
                    "researchMaxExtracts": 9,
                    "researchSearchCacheTtlSeconds": 700,
                    "researchExtractionCacheTtlSeconds": 1700,
                    "researchRawRetentionDays": 5,
                    "researchManifestRetentionDays": 55,
                    "researchShowDiagnostics": False,
                    "researchDeepEnabled": True,
                    "researchHermesPlannerEnabled": True,
                }
            },
        },
    )

    settings = load_research_runtime_settings()

    assert settings.default_mode == "deep"
    assert settings.provider == "tavily"
    assert settings.provider_fallbacks == ("playwright", "duckduckgo")
    assert settings.effective_provider_chain == ("tavily", "playwright", "duckduckgo")
    assert settings.max_results == 6
    assert settings.max_steps == 10
    assert settings.max_queries == 7
    assert settings.max_sources == 20
    assert settings.max_extracts == 9
    assert settings.policy.search_cache_ttl_seconds == 700
    assert settings.policy.extraction_cache_ttl_seconds == 1700
    assert settings.policy.raw_snapshot_retention_days == 5
    assert settings.policy.source_manifest_retention_days == 55
    assert settings.show_diagnostics is False
    assert settings.deep_enabled is True
    assert settings.hermes_planner_enabled is True


class CapturingContextService:
    def __init__(self) -> None:
        self.request = None

    def build(self, request):
        self.request = request
        return AssistantContextBuildResult()


def test_quick_search_route_applies_saved_provider_chain_result_limit_and_policy(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_INLINE_RESEARCH_JOB_EXECUTOR", "0")
    monkeypatch.setenv("OMNIX_WEB_SEARCH_API_KEY", "fixture-key")
    chat_store = ChatSessionStore(tmp_path / "chat.json")
    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    context_service = CapturingContextService()
    session = chat_store.create_session(CreateChatSessionRequest(title="Quick settings"))
    settings = runtime_settings()
    app = FastAPI()
    register_assistant_context_routes(
        app,
        chat_store_factory=lambda: chat_store,
        job_store_factory=lambda: job_store,
        context_service_factory=lambda: context_service,
        settings_factory=lambda: settings,
    )

    response = TestClient(app).post(
        f"/api/assistant/context/chat/sessions/{session.id}/messages",
        json={"content": "Find the current release", "web_research_mode": "quick"},
    )

    assert response.status_code == 200
    assert context_service.request is not None
    assert context_service.request.internal_research_provider == "brave"
    assert context_service.request.internal_research_provider_chain == [
        "brave",
        "playwright",
        "duckduckgo",
    ]
    assert context_service.request.web_search_max_results == 7
    assert context_service.request.internal_research_policy["search_cache_ttl_seconds"] == 901
    assert context_service.request.internal_research_policy["extraction_cache_ttl_seconds"] == 1802


def test_deep_research_job_freezes_saved_provider_chain_budgets_and_cache_ttls(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_INLINE_RESEARCH_JOB_EXECUTOR", "0")
    monkeypatch.setenv("OMNIX_WEB_SEARCH_API_KEY", "fixture-key")
    chat_store = ChatSessionStore(tmp_path / "chat.json")
    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    session = chat_store.create_session(CreateChatSessionRequest(title="Deep settings"))
    settings = runtime_settings()
    app = FastAPI()
    register_assistant_context_routes(
        app,
        chat_store_factory=lambda: chat_store,
        job_store_factory=lambda: job_store,
        settings_factory=lambda: settings,
        release_policy_factory=lambda: ResearchReleasePolicy(
            hermes_enabled=True,
            hermes_percentage=100,
        ),
    )

    response = TestClient(app).post(
        f"/api/assistant/context/chat/sessions/{session.id}/messages",
        json={"content": "Research the current release", "web_research_mode": "deep"},
    )

    assert response.status_code == 200
    payload = response.json()["job"]["input_payload"]
    assert payload["research_provider"] == "brave"
    assert payload["research_provider_chain"] == ["brave", "playwright", "duckduckgo"]
    assert payload["max_steps"] == 9
    assert payload["max_queries"] == 4
    assert payload["max_sources"] == 18
    assert payload["max_extracts"] == 6
    assert payload["search_cache_ttl_seconds"] == 901
    assert payload["extraction_cache_ttl_seconds"] == 1802
    assert payload["hermes_planner_enabled"] is True


def test_deep_research_honors_explicit_duckduckgo_primary_priority(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMNIX_INLINE_RESEARCH_JOB_EXECUTOR", "0")
    chat_store = ChatSessionStore(tmp_path / "chat.json")
    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    session = chat_store.create_session(CreateChatSessionRequest(title="Deep browser settings"))
    settings = runtime_settings(
        provider="duckduckgo",
        provider_fallbacks=("playwright",),
    )
    app = FastAPI()
    register_assistant_context_routes(
        app,
        chat_store_factory=lambda: chat_store,
        job_store_factory=lambda: job_store,
        settings_factory=lambda: settings,
    )

    response = TestClient(app).post(
        f"/api/assistant/context/chat/sessions/{session.id}/messages",
        json={"content": "Research current local coding models", "web_research_mode": "deep"},
    )

    assert response.status_code == 200
    payload = response.json()["job"]["input_payload"]
    assert payload["research_provider"] == "duckduckgo"
    assert payload["research_provider_chain"] == ["duckduckgo", "playwright"]


def test_api_backed_environment_provider_overrides_duckduckgo_primary(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_INLINE_RESEARCH_JOB_EXECUTOR", "0")
    monkeypatch.setenv("OMNIX_WEB_SEARCH_PROVIDER", "brave")
    monkeypatch.setenv("OMNIX_WEB_SEARCH_API_KEY", "fixture-key")
    chat_store = ChatSessionStore(tmp_path / "chat.json")
    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    context_service = CapturingContextService()
    session = chat_store.create_session(CreateChatSessionRequest(title="Provider override"))
    settings = runtime_settings(provider="duckduckgo", provider_fallbacks=("playwright", "duckduckgo"))
    app = FastAPI()
    register_assistant_context_routes(
        app,
        chat_store_factory=lambda: chat_store,
        job_store_factory=lambda: job_store,
        context_service_factory=lambda: context_service,
        settings_factory=lambda: settings,
    )

    response = TestClient(app).post(
        f"/api/assistant/context/chat/sessions/{session.id}/messages",
        json={"content": "Find the current release", "web_research_mode": "quick"},
    )
    status = TestClient(app).get("/api/assistant/research/status")

    assert response.status_code == 200
    assert context_service.request is not None
    assert context_service.request.internal_research_provider == "brave"
    assert context_service.request.internal_research_provider_chain == [
        "brave",
        "playwright",
        "duckduckgo",
    ]
    assert status.json()["provider"]["provider"] == "brave"
    assert status.json()["provider"]["coverage"] == "general web search"


def test_research_status_reports_provider_chain_without_exposing_secret(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_WEB_SEARCH_API_KEY", "never-return-this-secret")
    monkeypatch.setenv("OMNIX_RESEARCH_LEGACY_ALIASES_ENABLED", "1")
    monkeypatch.setenv("OMNIX_RESEARCH_LEGACY_ALIAS_SUNSET", "2026-09-01")
    reset_research_compatibility_telemetry()
    app = FastAPI()
    settings = runtime_settings()
    register_assistant_context_routes(
        app,
        chat_store_factory=lambda: ChatSessionStore(tmp_path / "chat.json"),
        job_store_factory=lambda: SQLiteJobStore(tmp_path / "jobs.sqlite"),
        settings_factory=lambda: settings,
    )

    response = TestClient(app).get("/api/assistant/research/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"]["provider"] == "brave"
    assert payload["provider"]["credential_required"] is True
    assert payload["provider"]["credential_configured"] is True
    assert payload["provider"]["available"] is True
    assert [item["provider"] for item in payload["provider_chain"]] == [
        "brave",
        "playwright",
        "duckduckgo",
    ]
    assert payload["provider_chain"][1]["credential_required"] is False
    assert payload["budgets"]["deep_max_steps"] == 9
    assert payload["retention"]["raw_snapshot_retention_days"] == 3
    assert payload["compatibility"]["aliases_enabled"] is True
    assert payload["compatibility"]["sunset"] == "2026-09-01"
    assert payload["compatibility"]["canonical_field"] == "web_research_mode"
    assert payload["compatibility"]["total_legacy_requests"] == 0
    assert "never-return-this-secret" not in json.dumps(payload)
