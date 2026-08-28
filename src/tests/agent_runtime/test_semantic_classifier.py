from __future__ import annotations

import json
from types import SimpleNamespace

from app.agent_runtime import chat_bridge
from app.agent_runtime.chat_bridge import (
    _apply_semantic_route_decision,
    route_typed_chat_turn,
)
from app.agent_runtime.contracts import EvidenceDecision
from app.agent_runtime.evidence import (
    classify_evidence,
    compile_task_authority,
    evidence_decision_from_semantic,
    task_requires_workspace_mutation,
)
from app.agent_runtime.profiles import get_agent_profile
from app.agent_runtime.router import route_omnix_request
from app.agent_runtime.semantic_classifier import (
    ProviderSemanticIntentClassifier,
    SemanticEvidenceHint,
    SemanticIntentDecision,
    default_semantic_intent_classifier,
)
from app.chat import ChatSessionStore, CreateChatSessionRequest, SendChatMessageRequest
from app.providers.base import BaseProvider, ChatResponse, ProviderConfig


class _StructuredFakeProvider:
    provider_name = "fake"

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.config = SimpleNamespace(model="fake-model", base_url="")
        self.calls = []

    def chat_completion(self, messages, model=None, stream=False, **kwargs):
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "stream": stream,
                "kwargs": kwargs,
            }
        )
        return ChatResponse(
            content=json.dumps(self.payload),
            model=model or "fake-model",
            finish_reason="stop",
        )


class _ContractFakeProvider(BaseProvider):
    provider_name = "lmstudio"

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = []
        super().__init__(
            ProviderConfig(
                provider_type="lmstudio",
                base_url="http://example.test",
                model="configured-model",
            )
        )

    def chat_completion(self, messages, model=None, stream=False, **kwargs):
        self.calls.append({"messages": messages, "model": model, "kwargs": kwargs})
        return ChatResponse(
            content=json.dumps(self.payload),
            model=model or "configured-model",
            finish_reason="stop",
        )

    def get_models(self):
        return []

    def test_connection(self) -> bool:
        return True


class _RecordingService:
    def __init__(self) -> None:
        self.started = []

    def get(self, _run_id):
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


def _weather_semantic() -> SemanticIntentDecision:
    return SemanticIntentDecision(
        lane="chat",
        profile_id="research",
        primary_intent="weather_lookup",
        action_intents=[],
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
        reason="The user wants a fresh forecast for tomorrow morning.",
    )


def test_provider_semantic_classifier_uses_typed_structured_contract() -> None:
    provider = _StructuredFakeProvider(
        {
            "lane": "chat",
            "profile_id": "research",
            "primary_intent": "weather_lookup",
            "action_intents": [],
            "evidence_requirements": [
                {
                    "source_class": "weather_state",
                    "freshness": "current",
                    "trust_floor": "authoritative",
                    "fallback_policy": "fail_closed",
                }
            ],
            "temporal_scope": "tomorrow morning",
            "subject_hints": ["user location"],
            "multi_step": False,
            "confidence": 0.98,
            "reason": "fresh forecast request",
        }
    )
    classifier = ProviderSemanticIntentClassifier(
        provider,
        model="fake-model",
        timeout_seconds=2,
    )

    decision = classifier.classify(
        "i had a rough day, i want to go out tomorrow, what will the weather be like in the morning?"
    )

    assert decision.lane == "chat"
    assert decision.primary_intent == "weather_lookup"
    assert decision.temporal_scope == "tomorrow morning"
    assert [row.source_class for row in decision.evidence_requirements] == ["weather_state"]
    assert len(provider.calls) == 1


def test_semantic_classifier_can_upgrade_arbitrary_language_to_agent() -> None:
    prompt = "could you make this behave better whenever the cache starts cold?"
    deterministic = route_omnix_request(prompt)
    assert deterministic.lane == "chat"

    semantic = SemanticIntentDecision(
        lane="agent",
        profile_id="coding",
        primary_intent="repository_change",
        action_intents=["workspace_mutate"],
        evidence_requirements=[],
        multi_step=True,
        confidence=0.96,
        reason="The user is requesting a code change.",
    )
    routed = _apply_semantic_route_decision(deterministic, semantic)
    assert routed.lane == "agent"
    assert routed.reason == "semantic:repository_change"


def test_explicit_agent_cannot_be_downgraded_by_semantic_classifier() -> None:
    deterministic = route_omnix_request("/agent explain the cache")
    semantic = SemanticIntentDecision(
        lane="chat",
        profile_id="research",
        primary_intent="explanation",
        action_intents=[],
        evidence_requirements=[],
        multi_step=False,
        confidence=0.99,
        reason="This could otherwise be answered in chat.",
    )

    routed = _apply_semantic_route_decision(deterministic, semantic)

    assert routed.lane == "agent"
    assert routed.explicit is True


def test_weather_example_compiles_fresh_authoritative_weather_evidence() -> None:
    prompt = (
        "i had a rough day, i want to go out tomorrow, "
        "what will the weather be like in the morning?"
    )
    semantic = _weather_semantic()
    proposal = evidence_decision_from_semantic(prompt, semantic)

    decision = classify_evidence(
        prompt,
        profile_id="research",
        semantic_adviser=lambda *_: proposal,
    )

    assert decision.policy.requirement == "required"
    assert {row.source_class for row in decision.policy.requirements} == {"weather_state"}
    requirement = decision.policy.requirements[0]
    assert requirement.freshness == "current"
    assert requirement.trust_floor == "authoritative"
    compiled = compile_task_authority(
        get_agent_profile("research"),
        prompt,
        decision,
    )
    assert compiled.required_external == ("weather.current",)


def test_high_confidence_semantics_can_remove_soft_regex_false_positive() -> None:
    prompt = "People keep saying latest; what does that word mean in ordinary English?"
    semantic = SemanticIntentDecision(
        lane="chat",
        profile_id="research",
        primary_intent="word_definition",
        action_intents=[],
        evidence_requirements=[],
        multi_step=False,
        confidence=0.99,
        reason="The word latest is being discussed, not requested as current information.",
    )
    proposal = evidence_decision_from_semantic(prompt, semantic)

    decision = classify_evidence(
        prompt,
        profile_id="research",
        semantic_adviser=lambda *_: proposal,
    )

    assert decision.policy.requirement == "none"
    assert decision.policy.requirements == []


def test_semantic_workspace_mutation_intent_is_compiled_but_stays_within_profile() -> None:
    semantic_actions = ["workspace_mutate"]
    compiled = compile_task_authority(
        get_agent_profile("coding"),
        "make this behave better whenever the cache starts cold",
        EvidenceDecision(),
        semantic_action_intents=semantic_actions,
    )

    assert task_requires_workspace_mutation(
        "make this behave better whenever the cache starts cold",
        semantic_action_intents=semantic_actions,
    )
    assert "workspace.edit" in compiled.required_local
    assert "workspace.write" in compiled.required_local
    assert "workspace.command" in compiled.required_local
    assert "workspace.test" in compiled.required_local


def test_semantic_home_mutation_proposal_requires_governed_home_authority() -> None:
    semantic = SemanticIntentDecision(
        lane="agent",
        profile_id="house",
        primary_intent="reduce_room_brightness",
        action_intents=["home_mutate"],
        evidence_requirements=[],
        multi_step=False,
        confidence=0.94,
        reason="The user wants the current room lighting changed.",
    )
    proposal = evidence_decision_from_semantic("it's too bright in here", semantic)
    decision = classify_evidence(
        "it's too bright in here",
        profile_id="house",
        semantic_adviser=lambda *_: proposal,
    )
    compiled = compile_task_authority(
        get_agent_profile("house"),
        "it's too bright in here",
        decision,
        semantic_action_intents=semantic.action_intents,
    )

    assert set(compiled.required_external) == {"home.get_state", "home.set_state"}


def test_weather_example_stays_chat_without_agent_mode(monkeypatch) -> None:
    service = _RecordingService()
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)
    session = SimpleNamespace(
        id="semantic-weather-chat",
        provider_id="test-provider",
        model_id="test-model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-weather",
        content=(
            "i had a rough day, i want to go out tomorrow, "
            "what will the weather be like in the morning?"
        ),
        metadata={},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test-provider",
        model_id="test-model",
        semantic_classifier=lambda _content: _weather_semantic(),
    )

    assert result is None
    assert service.started == []


def test_persistent_agent_mode_uses_semantic_weather_evidence(monkeypatch) -> None:
    service = _RecordingService()
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)
    session = SimpleNamespace(
        id="semantic-weather-agent",
        provider_id="test-provider",
        model_id="test-model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-weather-agent",
        content=(
            "i had a rough day, i want to go out tomorrow, "
            "what will the weather be like in the morning?"
        ),
        metadata={"agent_mode": True},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test-provider",
        model_id="test-model",
        semantic_classifier=lambda _content: _weather_semantic(),
    )

    assert result is not None
    assert len(service.started) == 1
    spec = service.started[0]
    assert spec.profile == "research"
    assert spec.external_capabilities == ["weather.current"]
    assert spec.evidence_policy.requirements[0].source_class == "weather_state"
    assert result.metadata["semantic_intent"]["primary_intent"] == "weather_lookup"


def test_unknown_test_provider_keeps_local_matrix_llm_free(monkeypatch) -> None:
    import app.shared as shared

    monkeypatch.setattr(
        shared,
        "get_provider",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unknown test provider must not resolve a live LLM")
        ),
    )

    assert default_semantic_intent_classifier(
        provider_id="test-provider",
        model_id="test-model",
    ) is None


def test_namespaced_ui_provider_identity_resolves_semantic_classifier(monkeypatch) -> None:
    import app.shared as shared

    provider = _ContractFakeProvider(
        {
            "lane": "chat",
            "profile_id": "research",
            "primary_intent": "weather_lookup",
            "action_intents": [],
            "evidence_requirements": [
                {
                    "source_class": "weather_state",
                    "freshness": "current",
                    "trust_floor": "authoritative",
                    "fallback_policy": "fail_closed",
                }
            ],
            "temporal_scope": "tomorrow morning",
            "subject_hints": ["user location"],
            "multi_step": False,
            "confidence": 0.98,
            "reason": "fresh forecast request",
        }
    )
    requested = []
    monkeypatch.setattr(
        shared,
        "get_provider",
        lambda provider_name=None: requested.append(provider_name) or provider,
    )

    classifier = default_semantic_intent_classifier(
        provider_id="llm:lmstudio",
        model_id="llm:lmstudio:qwen-test",
    )

    assert classifier is not None
    decision = classifier.classify("Will I need an umbrella tomorrow morning?")
    assert requested == ["lmstudio"]
    assert decision.primary_intent == "weather_lookup"
    assert provider.calls[0]["model"] == "qwen-test"


def test_non_streaming_chat_uses_generalized_semantic_router(
    monkeypatch,
    tmp_path,
) -> None:
    semantic = SemanticIntentDecision(
        lane="agent",
        profile_id="coding",
        primary_intent="repository_change",
        action_intents=["workspace_mutate"],
        evidence_requirements=[],
        multi_step=True,
        confidence=0.97,
        reason="The user is asking for a repository change in indirect language.",
    )
    service = _RecordingService()
    monkeypatch.setattr(
        chat_bridge,
        "default_semantic_intent_classifier",
        lambda **_kwargs: (lambda _content: semantic),
    )
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))

    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(
        CreateChatSessionRequest(
            title="Semantic routing",
            provider_id="test-provider",
            model_id="test-model",
        )
    )
    appended = store.append_user_message(
        session.id,
        SendChatMessageRequest(
            content="could you make this behave better whenever the cache starts cold?",
            provider_id="test-provider",
            model_id="test-model",
        ),
    )

    assert appended is not None
    assert len(service.started) == 1
    assert service.started[0].profile == "coding"
    assert "workspace.edit" in service.started[0].capabilities
    stored = store.get_session(session.id)
    assert stored is not None
    assert stored.messages[-2].metadata["omnix_route"]["lane"] == "agent"
    assert stored.messages[-1].metadata["semantic_intent"]["primary_intent"] == "repository_change"


def test_semantic_classifier_cannot_override_explicit_negated_action() -> None:
    prompt = "Don't change anything, just explain why the cache is cold."
    deterministic = route_omnix_request(prompt)
    assert deterministic.reason == "negated_action"

    semantic = SemanticIntentDecision(
        lane="agent",
        profile_id="coding",
        primary_intent="repository_change",
        action_intents=["workspace_mutate"],
        evidence_requirements=[],
        multi_step=True,
        confidence=0.99,
        reason="deliberately wrong semantic proposal for the guard test",
    )

    routed = _apply_semantic_route_decision(
        deterministic,
        semantic,
        content=prompt,
    )

    assert routed.lane == "chat"
    assert routed.reason == "negated_action"


def test_narrow_email_send_negation_can_still_route_to_agent_for_drafting() -> None:
    prompt = "don't send anything. read the latest message from Maya and draft the response she needs."
    deterministic = route_omnix_request(prompt)
    assert deterministic.reason == "negated_action"

    semantic = SemanticIntentDecision(
        lane="agent",
        profile_id="personal-assistant",
        primary_intent="draft_without_sending",
        action_intents=["email_read", "email_draft"],
        evidence_requirements=[],
        multi_step=True,
        confidence=0.99,
        reason="The user requests email reading and drafting while prohibiting send.",
    )

    routed = _apply_semantic_route_decision(
        deterministic,
        semantic,
        content=prompt,
    )

    assert routed.lane == "agent"


def test_narrow_home_mutation_negation_can_still_route_to_agent_for_read() -> None:
    prompt = "don't change the lights. just tell me whether the porch light is currently on."
    deterministic = route_omnix_request(prompt)
    assert deterministic.reason == "negated_action"

    semantic = SemanticIntentDecision(
        lane="agent",
        profile_id="house",
        primary_intent="read_light_state",
        action_intents=["home_read"],
        evidence_requirements=[],
        multi_step=False,
        confidence=0.99,
        reason="The user requests state inspection while prohibiting mutation.",
    )

    routed = _apply_semantic_route_decision(
        deterministic,
        semantic,
        content=prompt,
    )

    assert routed.lane == "agent"


def test_rhetorical_dont_just_explain_can_still_route_to_requested_coding_work() -> None:
    prompt = "don't just tell me why the parser breaks — actually update the code so it works."
    deterministic = route_omnix_request(prompt)
    assert deterministic.reason == "negated_action"

    semantic = SemanticIntentDecision(
        lane="agent",
        profile_id="coding",
        primary_intent="repository_change",
        action_intents=["workspace_mutate"],
        evidence_requirements=[],
        multi_step=False,
        confidence=0.99,
        reason="The user explicitly requests a code change.",
    )

    routed = _apply_semantic_route_decision(
        deterministic,
        semantic,
        content=prompt,
    )

    assert routed.lane == "agent"


def test_explicit_no_edit_instruction_blocks_semantic_workspace_mutation() -> None:
    compiled = compile_task_authority(
        get_agent_profile("coding"),
        "do not edit the files; explain the cache behavior",
        EvidenceDecision(),
        semantic_action_intents=["workspace_mutate"],
    )

    assert "workspace.edit" not in compiled.required_local
    assert "workspace.write" not in compiled.required_local
    assert "workspace.command" not in compiled.required_local
    assert "workspace.test" not in compiled.required_local


def test_explicit_email_send_negation_blocks_send_but_allows_requested_draft() -> None:
    semantic = SemanticIntentDecision(
        lane="agent",
        profile_id="personal-assistant",
        primary_intent="draft_without_sending",
        action_intents=["email_send", "email_draft"],
        evidence_requirements=[],
        multi_step=False,
        confidence=0.99,
        reason="The user wants a draft only.",
    )
    proposal = evidence_decision_from_semantic(
        "don't send the email; draft an email to Bob instead",
        semantic,
    )
    decision = classify_evidence(
        "don't send the email; draft an email to Bob instead",
        profile_id="personal-assistant",
        semantic_adviser=lambda *_: proposal,
    )
    compiled = compile_task_authority(
        get_agent_profile("personal-assistant"),
        "don't send the email; draft an email to Bob instead",
        decision,
        semantic_action_intents=semantic.action_intents,
    )

    assert "gmail.send_email" not in compiled.required_external
    assert "gmail.create_draft" in compiled.required_external
    assert "gmail.read_email" in compiled.required_external
