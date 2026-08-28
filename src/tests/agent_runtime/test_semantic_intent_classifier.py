from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime import chat_bridge
from app.agent_runtime.contracts import EvidenceDecision
from app.agent_runtime.evidence import (
    EvidenceCompilationError,
    classify_evidence,
    compile_task_authority,
    evidence_decision_from_semantic,
)
from app.agent_runtime.profiles import get_agent_profile
from app.agent_runtime.router import route_omnix_request
from app.agent_runtime.semantic_classifier import (
    SemanticEvidenceHint,
    SemanticIntentDecision,
)


class FakeSemanticClassifier:
    def __init__(self, decision: SemanticIntentDecision) -> None:
        self.decision = decision
        self.calls: list[str] = []

    def classify(self, content: str) -> SemanticIntentDecision:
        self.calls.append(content)
        return self.decision


class RecordingService:
    def __init__(self) -> None:
        self.started = []

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


def session():
    return SimpleNamespace(
        id="semantic-chat",
        provider_id="test-provider",
        model_id="test-model",
        messages=[],
    )


def message(content: str, *, metadata: dict | None = None):
    return SimpleNamespace(
        id="semantic-message",
        content=content,
        metadata=dict(metadata or {}),
    )


def test_conversational_tomorrow_weather_is_current_weather_evidence_even_without_llm() -> None:
    prompt = (
        "i had a rough day, i want to go out tomorrow, "
        "what will the weather be like in the morning?"
    )
    decision = classify_evidence(
        prompt,
        profile_id="research",
        semantic_adviser=lambda *_: None,
    )
    assert decision.policy.requirement == "required"
    assert {row.source_class for row in decision.policy.requirements} == {"weather_state"}
    requirement = decision.policy.requirements[0]
    assert requirement.freshness == "current"
    assert requirement.max_age_seconds is not None


def test_semantic_classifier_understands_weather_inside_background_context() -> None:
    prompt = (
        "i had a rough day, i want to go out tomorrow, "
        "what will the weather be like in the morning?"
    )
    semantic = SemanticIntentDecision(
        lane="chat",
        profile_id="research",
        primary_intent="weather_lookup",
        action_intents=["research_read"],
        evidence_requirements=[
            SemanticEvidenceHint(
                source_class="weather_state",
                freshness="current",
                trust_floor="authoritative",
                fallback_policy="fail_closed",
            )
        ],
        temporal_scope="tomorrow morning",
        subject_hints=["user location"],
        multi_step=False,
        confidence=0.98,
        reason="The background explains a simple future weather lookup.",
    )
    classifier = FakeSemanticClassifier(semantic)
    user_message = message(prompt)

    result = chat_bridge.route_typed_chat_turn(
        session(),
        user_message,
        provider_id="test-provider",
        model_id="test-model",
        semantic_classifier=classifier,
    )

    assert result is None
    assert classifier.calls == [prompt]
    assert user_message.metadata["semantic_intent"]["primary_intent"] == "weather_lookup"
    evidence = user_message.metadata["semantic_evidence"]
    assert evidence["policy"]["requirement"] == "required"
    assert {
        row["source_class"] for row in evidence["policy"]["requirements"]
    } == {"weather_state"}


def test_semantics_can_correct_a_deterministic_false_positive_back_to_chat() -> None:
    prompt = "I need to fix dinner after work; can you explain recursion?"
    assert route_omnix_request(prompt).lane == "agent"

    semantic = SemanticIntentDecision(
        lane="chat",
        profile_id="research",
        primary_intent="conceptual_explanation",
        action_intents=[],
        evidence_requirements=[],
        multi_step=False,
        confidence=0.97,
        reason="Fix refers to dinner; the requested task is an explanation.",
    )

    result = chat_bridge.route_typed_chat_turn(
        session(),
        message(prompt),
        provider_id="test-provider",
        model_id="test-model",
        semantic_classifier=FakeSemanticClassifier(semantic),
    )
    assert result is None


def test_semantics_can_promote_indirect_coding_language_to_agent(monkeypatch, tmp_path) -> None:
    service = RecordingService()
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))

    prompt = "The router feels brittle. Please make it more resilient."
    semantic = SemanticIntentDecision(
        lane="agent",
        profile_id="coding",
        primary_intent="repository_change",
        action_intents=["workspace_read", "workspace_mutate"],
        evidence_requirements=[],
        multi_step=True,
        confidence=0.96,
        reason="The user is asking for a code change despite indirect wording.",
    )

    result = chat_bridge.route_typed_chat_turn(
        session(),
        message(prompt),
        provider_id="test-provider",
        model_id="test-model",
        semantic_classifier=FakeSemanticClassifier(semantic),
    )

    assert result is not None
    assert len(service.started) == 1
    spec = service.started[0]
    assert spec.profile == "coding"
    assert "workspace.edit" in spec.capabilities
    assert "workspace.write" in spec.capabilities
    assert "workspace.test" in spec.capabilities
    assert spec.expected_artifacts == ["diff"]
    assert result.metadata["omnix_route"]["reason"].startswith("semantic_intent:")


def test_explicit_agent_keeps_authoritative_lane_but_uses_semantics_for_profile(monkeypatch, tmp_path) -> None:
    service = RecordingService()
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))

    semantic = SemanticIntentDecision(
        lane="chat",
        profile_id="coding",
        primary_intent="repository_change",
        action_intents=["workspace_mutate"],
        evidence_requirements=[],
        multi_step=False,
        confidence=0.95,
        reason="Semantic interpretation proposes coding; explicit Agent owns the lane.",
    )
    classifier = FakeSemanticClassifier(semantic)

    result = chat_bridge.route_typed_chat_turn(
        session(),
        message("/agent make this router less brittle"),
        provider_id="test-provider",
        model_id="test-model",
        semantic_classifier=classifier,
    )

    assert result is not None
    assert len(service.started) == 1
    assert service.started[0].profile == "coding"
    assert result.metadata["omnix_route"]["lane"] == "agent"
    assert result.metadata["request_mode"]["source"] == "explicit_command"


def test_low_confidence_semantic_decision_falls_back_to_deterministic_route(monkeypatch) -> None:
    service = RecordingService()
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_REPOSITORY", raising=False)

    prompt = "fix the router"
    semantic = SemanticIntentDecision(
        lane="chat",
        profile_id="research",
        primary_intent="uncertain",
        action_intents=[],
        evidence_requirements=[],
        multi_step=False,
        confidence=0.20,
        reason="uncertain",
    )

    result = chat_bridge.route_typed_chat_turn(
        session(),
        message(prompt),
        provider_id="test-provider",
        model_id="test-model",
        semantic_classifier=FakeSemanticClassifier(semantic),
    )

    assert result is not None
    assert result.metadata["omnix_route"]["lane"] == "agent"
    assert result.metadata["agent_start"]["status"] == "failed"


def test_exact_direct_fast_path_does_not_call_semantic_classifier() -> None:
    decision = route_omnix_request("Turn off the desk light")
    assert decision.lane == "direct"
    assert chat_bridge._should_use_semantic_classifier(
        decision,
        research_mode=None,
    ) is False


def test_semantic_evidence_cannot_override_explicit_no_web() -> None:
    prompt = "I want to go out tomorrow; tell me the weather without using the web"
    semantic = SemanticIntentDecision(
        lane="chat",
        profile_id="research",
        primary_intent="weather_lookup",
        action_intents=["research_read"],
        evidence_requirements=[
            SemanticEvidenceHint(
                source_class="weather_state",
                freshness="current",
                trust_floor="authoritative",
            )
        ],
        multi_step=False,
        confidence=0.99,
        reason="weather lookup",
    )
    advised = evidence_decision_from_semantic(prompt, semantic)
    decision = classify_evidence(
        prompt,
        profile_id="research",
        semantic_adviser=lambda *_: advised,
    )

    assert decision.policy.external_access == "forbidden"
    with pytest.raises(EvidenceCompilationError) as caught:
        compile_task_authority(get_agent_profile("research"), prompt, decision)
    assert caught.value.code == "external_evidence_forbidden"


def test_semantic_workspace_mutation_cannot_override_explicit_read_only_instruction() -> None:
    compiled = compile_task_authority(
        get_agent_profile("coding"),
        "Inspect the router but do not change files",
        EvidenceDecision(),
        semantic_action_intents=["workspace_mutate"],
    )
    assert "workspace.read" in compiled.required_local
    assert "workspace.edit" not in compiled.required_local
    assert "workspace.write" not in compiled.required_local


def test_semantic_home_mutation_cannot_override_explicit_prohibition() -> None:
    compiled = compile_task_authority(
        get_agent_profile("house"),
        "Check the bedroom light but do not turn anything off",
        EvidenceDecision(),
        semantic_action_intents=["home_read", "home_mutate"],
    )
    assert "home.get_state" in compiled.required_external
    assert "home.set_state" not in compiled.required_external


def test_semantic_email_send_cannot_override_explicit_prohibition() -> None:
    compiled = compile_task_authority(
        get_agent_profile("personal-assistant"),
        "Draft a reply but do not send the email",
        EvidenceDecision(),
        semantic_action_intents=["email_read", "email_draft", "email_send"],
    )
    assert "gmail.read_email" in compiled.required_external
    assert "gmail.create_draft" in compiled.required_external
    assert "gmail.send_email" not in compiled.required_external
