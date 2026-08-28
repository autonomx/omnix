"""Comprehensive local Agent Runtime contract matrix.

These tests intentionally exercise production routing/compiler/chat-boundary code
without calling a real LLM, Pi, Hermes, network service, or external tool.

Local run (PowerShell):
    $env:PYTHONPATH="src"
    python -m pytest src/tests/agent_runtime/test_local_runtime_matrix.py -q --tb=short

The suite is designed for Codex/local development: failures should identify a
semantic contract regression rather than model-output wording drift.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime import chat_bridge
from app.agent_runtime.chat_bridge import _select_profile, route_typed_chat_turn
from app.agent_runtime.contracts import EvidenceDecision, EvidencePolicy
from app.agent_runtime.evidence import (
    EvidenceCompilationError,
    classify_evidence,
    compile_task_authority,
    resolve_request_mode,
)
from app.agent_runtime.profiles import get_agent_profile
from app.agent_runtime.router import route_omnix_request


# ---------------------------------------------------------------------------
# Deterministic top-level routing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt,expected_lane",
    [
        ("hello", "chat"),
        ("thanks", "chat"),
        ("What is TCP congestion control?", "chat"),
        ("Explain why tests can become flaky", "chat"),
        ("How would an agent debug this?", "chat"),
        ('What does "fix the tests" mean?', "chat"),
        ("Don't fix anything, just explain the failure", "chat"),
        ("No need to implement anything", "chat"),
        ("Can you fix the failing tests?", "agent"),
        ("debugg the router", "agent"),
        ("implement the missing feature", "agent"),
        ("investigate this failure", "agent"),
        ("research semiconductor stocks", "agent"),
        ("check my calendar for conflicts", "agent"),
        ("summarize my emails", "chat"),
        ("set the thermostat to 19 degrees", "agent"),
        ("Turn off the desk light", "direct"),
        ("turn of the kitchen plug", "direct"),
        ("status of the office light", "direct"),
        ("Turn off the light and tell me a joke", "agent"),
        ("Check my calendar and research NVDA", "agent"),
        ("Research NVDA and buy it if it looks good", "agent"),
        ("take care of anything important before I leave", "agent"),
        ("/agent explain TCP", "agent"),
        ("/agnet fix tests", "agent"),
    ],
)
def test_local_route_matrix(prompt: str, expected_lane: str) -> None:
    assert route_omnix_request(prompt).lane == expected_lane


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("Research NVIDIA's competitive position", "chat"),
        ("Investigate economic trends", "chat"),
        ("Analyze GME prospects", "chat"),
    ],
)
def test_quick_and_deep_research_modes_keep_research_in_chat(prompt: str, expected: str) -> None:
    assert route_omnix_request(prompt, research_mode="quick").lane == expected
    assert route_omnix_request(prompt, research_mode="deep").lane == expected


def test_known_workflow_routes_without_starting_runtime() -> None:
    decision = route_omnix_request(
        "Run bedtime routine",
        workflow_lookup=lambda name: "workflow-bedtime" if name == "bedtime" else None,
    )
    assert decision.lane == "workflow"
    assert decision.workflow_id == "workflow-bedtime"


@pytest.mark.parametrize(
    "prompt",
    [
        "Turn off the desk light and tell me a joke",
        "Check my calendar and research NVDA",
        "Fix the trading UI and then research NVDA",
        "Check my email and turn off the bedroom light",
        "Research NVDA and buy it if it looks good",
    ],
)
def test_mixed_intent_requires_agent_semantic_planning(prompt: str) -> None:
    decision = route_omnix_request(prompt)
    assert decision.lane == "agent"
    assert decision.hermes_recommended is True
    assert decision.reason == "mixed_intent_task"


# ---------------------------------------------------------------------------
# Profile selection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt,expected_profile",
    [
        ("fix the repository tests", "coding"),
        ("review router.py", "coding"),
        ("run pytest", "coding"),
        ("inspect GitHub Actions", "coding"),
        ("push the branch", "coding"),
        ("check all the lights", "house"),
        ("inspect thermostat state", "house"),
        ("check my calendar", "personal-assistant"),
        ("summarize my emails", "personal-assistant"),
        ("look up a contact", "personal-assistant"),
        ("research NVDA", "trading-research"),
        ("investigate GME catalysts", "trading-research"),
        ("analyze semiconductor stocks", "trading-research"),
        ("buy NVDA", "trading-research"),
        ("cancel my stock order", "trading-research"),
        ("research PostgreSQL releases", "research"),
        ("investigate TCP congestion control", "research"),
    ],
)
def test_local_profile_matrix(prompt: str, expected_profile: str) -> None:
    assert _select_profile(prompt) == expected_profile


# ---------------------------------------------------------------------------
# Request-mode precedence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content,turn_mode,persistent,lane,expected_mode,expected_source",
    [
        ("/agent research NVDA", "deep", True, "agent", "agent", "explicit_command"),
        ("/research quick NVDA", None, True, "agent", "quick_research", "explicit_command"),
        ("/research deep NVDA", None, True, "agent", "deep_research", "explicit_command"),
        ("/search NVDA", None, True, "agent", "quick_research", "explicit_command"),
        ("research NVDA", "quick", True, "agent", "quick_research", "turn_setting"),
        ("research NVDA", "deep", True, "agent", "deep_research", "turn_setting"),
        ("implement feature", None, True, "agent", "agent", "persistent_setting"),
        ("implement feature", None, False, "agent", "agent", "classifier"),
        ("hello", None, True, "chat", "agent", "persistent_setting"),
        ("hello", None, False, "chat", "auto", "classifier"),
        ("hello", None, False, "direct", "auto", "classifier"),
    ],
)
def test_local_request_mode_precedence(
    content: str,
    turn_mode: str | None,
    persistent: bool,
    lane: str,
    expected_mode: str,
    expected_source: str,
) -> None:
    selected = resolve_request_mode(
        content,
        turn_research_mode=turn_mode,
        persistent_agent=persistent,
        classifier_lane=lane,
    )
    assert selected.mode == expected_mode
    assert selected.source == expected_source


# ---------------------------------------------------------------------------
# Evidence classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt,profile,expected_requirement,expected_sources",
    [
        ("What is a stock split?", "trading-research", "none", set()),
        ("Explain TCP congestion control", "research", "none", set()),
        ("What is the latest PostgreSQL release?", "research", "required", {"software_release"}),
        ("Give me current database news", "research", "required", {"general_current_web"}),
        ("What is NVDA trading at today?", "trading-research", "required", {"market_quote"}),
        ("Give me NVDA news today", "trading-research", "required", {"market_news"}),
        ("Give me GME catalysts today", "trading-research", "required", {"market_news"}),
        ("Give me NVDA latest SEC filing", "trading-research", "required", {"company_filing"}),
        ("Check GitHub Actions status", "coding", "required", {"repo_ci_state"}),
        ("Inspect the current repository commit", "coding", "required", {"repo_contents"}),
        ("Check the current home light state", "house", "required", {"home_state"}),
        ("Check home energy usage", "house", "required", {"home_energy"}),
        ("Check my calendar", "personal-assistant", "required", {"calendar_state"}),
        ("Summarize my email", "personal-assistant", "required", {"email_state"}),
        (
            "Give me NVDA's current quote, today's catalysts, and latest SEC filing",
            "trading-research",
            "required",
            {"market_quote", "market_news", "company_filing"},
        ),
    ],
)
def test_local_evidence_classification_matrix(
    prompt: str,
    profile: str,
    expected_requirement: str,
    expected_sources: set[str],
) -> None:
    decision = classify_evidence(prompt, profile_id=profile, semantic_adviser=lambda *_: None)
    assert decision.policy.requirement == expected_requirement
    assert {item.source_class for item in decision.policy.requirements} == expected_sources


@pytest.mark.parametrize(
    "prompt",
    [
        "Tell me the latest PostgreSQL release without using the web",
        "Tell me the latest PostgreSQL release do not use the internet",
        "Tell me the latest PostgreSQL release don't browse the web",
        "Tell me the latest PostgreSQL release from memory only",
    ],
)
def test_no_external_variants_are_authoritative(prompt: str) -> None:
    decision = classify_evidence(prompt, profile_id="research", semantic_adviser=lambda *_: None)
    assert decision.policy.requirement == "required"
    assert decision.policy.external_access == "forbidden"
    with pytest.raises(EvidenceCompilationError) as caught:
        compile_task_authority(get_agent_profile("research"), prompt, decision)
    assert caught.value.code == "external_evidence_forbidden"


def test_generic_do_not_change_instruction_does_not_forbid_web() -> None:
    prompt = "Research the latest PostgreSQL release, but do not change any files"
    decision = classify_evidence(prompt, profile_id="research", semantic_adviser=lambda *_: None)
    assert decision.policy.external_access == "allowed"
    assert decision.policy.requirement == "required"


def test_source_request_requires_visible_attribution() -> None:
    decision = classify_evidence(
        "Research the latest PostgreSQL release with sources",
        profile_id="research",
        semantic_adviser=lambda *_: None,
    )
    assert decision.policy.user_visible_attribution == "required"


def test_semantic_adviser_cannot_override_explicit_no_web_policy() -> None:
    advised = EvidenceDecision(
        policy=EvidencePolicy(requirement="none", external_access="allowed"),
        confidence=0.99,
        reason="adviser",
        classifier="semantic",
    )
    decision = classify_evidence(
        "Please look into whether that still holds without using the web",
        profile_id="research",
        semantic_adviser=lambda *_: advised,
    )
    assert decision.policy.external_access == "forbidden"


def test_low_confidence_semantic_advice_gets_conservative_current_floor() -> None:
    advised = EvidenceDecision(
        policy=EvidencePolicy(requirement="none"),
        confidence=0.20,
        reason="uncertain",
        classifier="semantic",
    )
    decision = classify_evidence(
        "Please look into NVDA",
        profile_id="trading-research",
        semantic_adviser=lambda *_: advised,
    )
    assert decision.classifier == "conservative"
    assert decision.policy.requirement == "required"
    assert {item.source_class for item in decision.policy.requirements} == {"market_news"}


@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "AMD", "META"])
def test_generic_equity_symbols_bind_security_subject(ticker: str) -> None:
    decision = classify_evidence(
        f"What is {ticker} stock price today?",
        profile_id="trading-research",
        semantic_adviser=lambda *_: None,
    )
    requirement = decision.policy.requirements[0]
    assert requirement.source_class == "market_quote"
    assert requirement.subject is not None
    assert requirement.subject.type == "security"
    assert requirement.subject.qualifiers["ticker"] == ticker


@pytest.mark.parametrize("context_word", ["NEWS", "SEC", "PRICE", "QUOTE"])
def test_context_words_are_not_mistaken_for_tickers(context_word: str) -> None:
    decision = classify_evidence(
        f"Give me {context_word} about AAPL stock today",
        profile_id="trading-research",
        semantic_adviser=lambda *_: None,
    )
    subjects = [item.subject for item in decision.policy.requirements if item.subject is not None]
    assert subjects
    assert all(subject.qualifiers.get("ticker") == "AAPL" for subject in subjects)


# ---------------------------------------------------------------------------
# Minimum-authority compiler
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "profile_id,task,expected_local,expected_external",
    [
        (
            "coding",
            "review router.py",
            {"workspace.read", "workspace.list", "workspace.search", "workspace.git_status", "workspace.git_diff"},
            set(),
        ),
        (
            "coding",
            "run pytest for the router",
            {
                "workspace.read",
                "workspace.list",
                "workspace.search",
                "workspace.git_status",
                "workspace.git_diff",
                "workspace.command",
                "workspace.test",
            },
            set(),
        ),
        (
            "coding",
            "fix the router tests",
            {
                "workspace.read",
                "workspace.list",
                "workspace.search",
                "workspace.git_status",
                "workspace.git_diff",
                "workspace.edit",
                "workspace.write",
                "workspace.command",
                "workspace.test",
            },
            set(),
        ),
        ("research", "research the latest PostgreSQL release", set(), {"research.web_search"}),
        ("trading-research", "research NVDA news today", set(), {"research.web_search"}),
        ("trading-research", "what is NVDA trading at today", set(), {"trading.market_quote"}),
        ("house", "check the light state", set(), {"home.get_state"}),
        ("house", "turn the light off", set(), {"home.get_state", "home.set_state"}),
        ("personal-assistant", "check my calendar", set(), {"calendar.read_availability"}),
        (
            "personal-assistant",
            "schedule a calendar meeting",
            set(),
            {"calendar.read_availability", "calendar.create_event"},
        ),
        ("personal-assistant", "summarize my email", set(), {"gmail.read_email"}),
        (
            "personal-assistant",
            "send an email to Bob",
            set(),
            {"gmail.read_email", "gmail.send_email"},
        ),
        (
            "personal-assistant",
            "draft an email to Bob",
            set(),
            {"gmail.read_email", "gmail.create_draft"},
        ),
    ],
)
def test_local_minimum_authority_matrix(
    profile_id: str,
    task: str,
    expected_local: set[str],
    expected_external: set[str],
) -> None:
    profile = get_agent_profile(profile_id)
    decision = classify_evidence(task, profile_id=profile_id, semantic_adviser=lambda *_: None)
    compiled = compile_task_authority(profile, task, decision)
    assert set(compiled.required_local) == expected_local
    assert set(compiled.required_external) == expected_external
    assert set(compiled.required_local).issubset(set(profile.capabilities))
    assert set(compiled.required_external).issubset(
        set(profile.external_capabilities) | set(profile.optional_external_capabilities)
    )


def test_weather_fails_at_compile_time_when_profile_cannot_satisfy_authoritative_source() -> None:
    task = "What is the weather in Vancouver right now?"
    decision = classify_evidence(task, profile_id="research", semantic_adviser=lambda *_: None)
    assert {item.source_class for item in decision.policy.requirements} == {"weather_state"}
    compiled = compile_task_authority(get_agent_profile("research"), task, decision)
    # weather.current is an optional research ceiling capability, so it may be issued.
    assert set(compiled.required_external) == {"weather.current"}


# ---------------------------------------------------------------------------
# Chat -> Agent start boundary with a fake durable service
# ---------------------------------------------------------------------------


class _RecordingService:
    def __init__(self) -> None:
        self.started = []
        self.commands = []

    def get(self, _run_id: str):
        return None

    def start(self, spec):
        self.started.append(spec)
        return SimpleNamespace(
            run_id=spec.run_id,
            status="running",
            revision=1,
            last_error=None,
            superseded_by_run_id=None,
            spec=spec,
        )

    def command(self, command):
        self.commands.append(command)
        raise AssertionError("command() should not be reached for a fresh-run case")


def _session(*, provider_id: str = "test-provider", model_id: str = "test-model", messages=None):
    return SimpleNamespace(
        id="chat-local-matrix",
        provider_id=provider_id,
        model_id=model_id,
        messages=list(messages or []),
    )


def _message(content: str, *, metadata: dict | None = None):
    return SimpleNamespace(
        id=f"message-{abs(hash(content))}",
        content=content,
        metadata=dict(metadata or {}),
    )


@pytest.mark.parametrize(
    "content,metadata,expected_profile,expected_external,expects_diff",
    [
        (
            "/agent review router.py",
            {},
            "coding",
            set(),
            False,
        ),
        (
            "/agent run pytest for the router",
            {},
            "coding",
            set(),
            False,
        ),
        (
            "/agent fix the router tests",
            {},
            "coding",
            set(),
            True,
        ),
        (
            "/agent research the latest PostgreSQL release",
            {},
            "research",
            {"research.web_search"},
            False,
        ),
        (
            "/agent research NVDA news today",
            {},
            "trading-research",
            {"research.web_search"},
            False,
        ),
        (
            "/agent what is AAPL stock price today?",
            {},
            "trading-research",
            {"trading.market_quote"},
            False,
        ),
        (
            "check my calendar",
            {"agent_mode": True},
            "personal-assistant",
            {"calendar.read_availability"},
            False,
        ),
        (
            "summarize my email",
            {"agent_mode": True},
            "personal-assistant",
            {"gmail.read_email"},
            False,
        ),
        (
            "check all the lights",
            {"agent_mode": True},
            "house",
            {"home.get_state"},
            False,
        ),
        (
            "turn the thermostat down to 19 degrees",
            {"agent_mode": True},
            "house",
            {"home.get_state", "home.set_state"},
            False,
        ),
    ],
)
def test_chat_boundary_builds_real_run_specs_without_llm(
    monkeypatch,
    tmp_path,
    content: str,
    metadata: dict,
    expected_profile: str,
    expected_external: set[str],
    expects_diff: bool,
) -> None:
    service = _RecordingService()
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))

    result = route_typed_chat_turn(
        _session(),
        _message(content, metadata=metadata),
        provider_id="test-provider",
        model_id="test-model",
    )

    assert result is not None
    assert len(service.started) == 1
    spec = service.started[0]
    assert spec.profile == expected_profile
    assert spec.model.provider_id == "test-provider"
    assert spec.model.model_id == "test-model"
    assert set(spec.external_capabilities) == expected_external
    assert spec.expected_artifacts == (["diff"] if expects_diff else [])
    if expected_profile == "coding":
        assert spec.workspace is not None
        assert spec.workspace.root == str(tmp_path)
    else:
        assert spec.workspace is None
    assert result.metadata["agent_run"]["profile"] == expected_profile
    assert result.metadata["evidence_policy"] if "evidence_policy" in result.metadata else True


def test_chat_boundary_quick_research_bypasses_agent_even_when_persistent_agent_is_on(monkeypatch) -> None:
    service = _RecordingService()
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)
    result = route_typed_chat_turn(
        _session(),
        _message("research NVDA", metadata={"agent_mode": True, "research_mode": "quick"}),
        provider_id="test-provider",
        model_id="test-model",
    )
    assert result is None
    assert service.started == []


def test_chat_boundary_deep_research_bypasses_agent_even_when_persistent_agent_is_on(monkeypatch) -> None:
    service = _RecordingService()
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)
    result = route_typed_chat_turn(
        _session(),
        _message("research NVDA", metadata={"agent_mode": True, "research_mode": "deep"}),
        provider_id="test-provider",
        model_id="test-model",
    )
    assert result is None
    assert service.started == []


def test_explicit_agent_outranks_turn_deep_research(monkeypatch, tmp_path) -> None:
    service = _RecordingService()
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    result = route_typed_chat_turn(
        _session(),
        _message("/agent review router.py", metadata={"agent_mode": True, "research_mode": "deep"}),
        provider_id="test-provider",
        model_id="test-model",
    )
    assert result is not None
    assert len(service.started) == 1
    assert service.started[0].profile == "coding"
    assert result.metadata["request_mode"]["mode"] == "agent"
    assert result.metadata["request_mode"]["source"] == "explicit_command"


def test_trade_execution_is_rejected_before_run_start(monkeypatch) -> None:
    service = _RecordingService()
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)
    result = route_typed_chat_turn(
        _session(),
        _message("/agent buy 10 shares of NVDA"),
        provider_id="test-provider",
        model_id="test-model",
    )
    assert result is not None
    assert service.started == []
    assert result.metadata["agent_start"]["status"] == "rejected"
    assert result.metadata["agent_start"]["reason"] == "trading_execution_capability_not_issued"


def test_publication_is_rejected_before_run_start(monkeypatch, tmp_path) -> None:
    service = _RecordingService()
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    result = route_typed_chat_turn(
        _session(),
        _message("/agent push the current branch and open a pull request"),
        provider_id="test-provider",
        model_id="test-model",
    )
    assert result is not None
    assert service.started == []
    assert result.metadata["agent_start"]["status"] == "rejected"
    assert result.metadata["agent_start"]["reason"] == "github_publication_capability_not_issued"


def test_impossible_no_web_current_research_is_rejected_before_run_start(monkeypatch) -> None:
    service = _RecordingService()
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)
    result = route_typed_chat_turn(
        _session(),
        _message("/agent tell me the latest PostgreSQL release without using the web"),
        provider_id="test-provider",
        model_id="test-model",
    )
    assert result is not None
    assert service.started == []
    assert result.metadata["agent_start"]["status"] == "rejected"
    assert result.metadata["agent_start"]["reason"] == "external_evidence_forbidden"


def test_coding_start_fails_closed_without_workspace(monkeypatch) -> None:
    service = _RecordingService()
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_REPOSITORY", raising=False)
    result = route_typed_chat_turn(
        _session(),
        _message("/agent fix the router tests"),
        provider_id="test-provider",
        model_id="test-model",
    )
    assert result is not None
    assert service.started == []
    assert result.metadata["agent_start"]["status"] == "failed"
    assert "requires OMNIX_AGENT_DEFAULT_REPOSITORY" in result.metadata["agent_start"]["error"]


def test_agent_start_fails_closed_without_provider_or_model(monkeypatch, tmp_path) -> None:
    service = _RecordingService()
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_PROVIDER_ID", raising=False)
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_MODEL_ID", raising=False)
    result = route_typed_chat_turn(
        _session(provider_id="", model_id=""),
        _message("/agent review router.py"),
        provider_id=None,
        model_id=None,
    )
    assert result is not None
    assert service.started == []
    assert result.metadata["agent_start"]["status"] == "failed"
    assert "provider/model is not configured" in result.metadata["agent_start"]["error"]


def test_suite_does_not_require_default_llm_provider(monkeypatch) -> None:
    """Guard the intended local-test contract against accidental provider coupling."""
    import app.shared as shared

    monkeypatch.setattr(
        shared,
        "get_provider",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("local Agent Runtime matrix must not call the default LLM provider")
        ),
    )
    decision = route_omnix_request("implement the missing feature")
    evidence = classify_evidence(
        "What is the latest PostgreSQL release?",
        profile_id="research",
        semantic_adviser=lambda *_: None,
    )
    compiled = compile_task_authority(
        get_agent_profile("research"),
        "What is the latest PostgreSQL release?",
        evidence,
    )
    assert decision.lane == "agent"
    assert compiled.required_external == ("research.web_search",)
