from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assistant_context.models import AssistantContextBuildResult
from app.assistant_context.routes import register_assistant_context_routes
from app.chat import ChatSessionStore, CreateChatSessionRequest
from app.jobs import SQLiteJobStore
from app.research.policy import ResearchPolicy, ResearchRateLimiter
from app.research.release_policy import (
    ResearchReleasePolicy,
    research_release_availability,
    resolve_research_release,
)
from app.research.settings import ResearchRuntimeSettings


class EmptyContextService:
    def __init__(self) -> None:
        self.requests = []

    def build(self, request):
        self.requests.append(request)
        return AssistantContextBuildResult()


def settings(*, deep_enabled: bool, hermes_enabled: bool = False) -> ResearchRuntimeSettings:
    return ResearchRuntimeSettings(
        provider="duckduckgo",
        deep_enabled=deep_enabled,
        hermes_planner_enabled=hermes_enabled,
        policy=ResearchPolicy(),
    )


def test_master_rollback_blocks_research_without_affecting_disabled_chat() -> None:
    policy = ResearchReleasePolicy(master_enabled=False)
    quick = resolve_research_release(
        "quick",
        settings(deep_enabled=True),
        policy,
        identity="session:one",
    )
    disabled = resolve_research_release(
        "disabled",
        settings(deep_enabled=True),
        policy,
        identity="session:one",
    )

    assert quick.status == "unavailable"
    assert quick.reason == "research_master_rollback_active"
    assert disabled.status == "allowed"
    assert disabled.effective_mode == "disabled"


def test_deep_uses_local_planner_before_separate_hermes_release() -> None:
    local = resolve_research_release(
        "deep",
        settings(deep_enabled=True, hermes_enabled=True),
        ResearchReleasePolicy(hermes_enabled=False, hermes_percentage=0),
        identity="session:one",
    )
    hermes = resolve_research_release(
        "deep",
        settings(deep_enabled=True, hermes_enabled=True),
        ResearchReleasePolicy(hermes_enabled=True, hermes_percentage=100),
        identity="session:one",
    )

    assert local.status == "allowed"
    assert local.use_hermes_planner is False
    assert hermes.status == "allowed"
    assert hermes.use_hermes_planner is True


def test_release_cohorts_are_deterministic_and_can_partition_sessions() -> None:
    policy = ResearchReleasePolicy(quick_percentage=50)
    resolved = settings(deep_enabled=False)
    first = research_release_availability(resolved, policy, identity="session:stable")
    second = research_release_availability(resolved, policy, identity="session:stable")
    population = {
        research_release_availability(resolved, policy, identity=f"session:{index}").quick
        for index in range(200)
    }

    assert first.quick == second.quick
    assert population == {False, True}


def test_deep_unavailable_requires_explicit_downgrade_consent() -> None:
    without_consent = resolve_research_release(
        "deep",
        settings(deep_enabled=False),
        ResearchReleasePolicy(),
        identity="session:one",
        allow_downgrade=False,
    )
    with_consent = resolve_research_release(
        "deep",
        settings(deep_enabled=False),
        ResearchReleasePolicy(),
        identity="session:one",
        allow_downgrade=True,
    )

    assert without_consent.status == "unavailable"
    assert without_consent.effective_mode == "disabled"
    assert with_consent.status == "downgraded"
    assert with_consent.effective_mode == "quick"
    assert with_consent.warnings == ["deep_research_downgraded_to_quick"]


def test_route_rejects_silent_downgrade_and_persists_visible_opt_in_notice(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMNIX_INLINE_RESEARCH_JOB_EXECUTOR", "0")
    chat_store = ChatSessionStore(tmp_path / "chat.json")
    job_store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    limiter = ResearchRateLimiter(tmp_path / "limits.sqlite")
    context_service = EmptyContextService()
    session = chat_store.create_session(CreateChatSessionRequest(title="Release test"))
    app = FastAPI()
    register_assistant_context_routes(
        app,
        chat_store_factory=lambda: chat_store,
        job_store_factory=lambda: job_store,
        context_service_factory=lambda: context_service,
        rate_limiter_factory=lambda: limiter,
        settings_factory=lambda: settings(deep_enabled=False),
        release_policy_factory=ResearchReleasePolicy,
    )
    client = TestClient(app)

    rejected = client.post(
        f"/api/assistant/context/chat/sessions/{session.id}/messages",
        json={"content": "Research this", "web_research_mode": "deep"},
    )
    accepted = client.post(
        f"/api/assistant/context/chat/sessions/{session.id}/messages",
        json={
            "content": "Research this with fallback",
            "web_research_mode": "deep",
            "allow_research_downgrade": True,
        },
    )

    assert rejected.status_code == 409
    assert rejected.json()["detail"] == {
        "code": "research_mode_unavailable",
        "requested_mode": "deep",
        "reason": "deep_research_disabled_in_settings",
        "available_modes": ["disabled", "quick"],
        "downgrade_available": True,
    }
    assert accepted.status_code == 200
    assert context_service.requests[-1].web_research_mode == "quick"
    assistant = accepted.json()["session"]["messages"][-1]
    assert assistant["role"] == "assistant"
    assert "Research mode notice" in assistant["content"]
    assert "explicitly allowed a downgrade" in assistant["content"]
    assert assistant["metadata"]["research_requested_mode"] == "deep"
    assert assistant["metadata"]["research_effective_mode"] == "quick"
    assert assistant["metadata"]["research_release_status"] == "downgraded"
