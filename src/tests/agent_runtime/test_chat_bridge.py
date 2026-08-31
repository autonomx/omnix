from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime import chat_bridge
from app.agent_runtime.chat_bridge import (
    _agent_task,
    _direct_request,
    _select_profile,
    _unauthorized_agent_command,
    route_typed_chat_turn,
)
from app.agent_runtime.contracts import (
    AgentRunSpec,
    EvidenceDecision,
    EvidencePolicy,
    EvidenceRequirement,
    ModelRef,
    WorkspaceSpec,
)
from app.assistant_tools.models import AssistantToolResult
from app.agent_runtime.router import route_omnix_request
from app.agent_runtime.semantic_task import (
    SemanticDataDependency,
    SemanticOperation,
    SemanticSubject,
    SemanticTask,
    SemanticTaskCompilation,
)


class _DefaultV2TestParser:
    def parse_contextual(
        self,
        latest_user_message: str,
        *,
        reference_context: str = "",
        previous_objective: str = "",
    ) -> SemanticTask:
        del reference_context, previous_objective
        text = latest_user_message.casefold()
        if "buy " in text and ("share" in text or "stock" in text):
            return SemanticTask(
                intent="market execution request",
                subjects=[SemanticSubject(target="market", reference="requested shares")],
                operations=[SemanticOperation(kind="research", target="market")],
                autonomous=True,
                reason_code="market_request",
            )
        if "weather" in text:
            return SemanticTask(
                intent="weather research",
                subjects=[SemanticSubject(target="weather", reference="requested weather")],
                operations=[SemanticOperation(kind="research", target="weather")],
                data_dependencies=[
                    SemanticDataDependency(target="weather", freshness="current")
                ],
                autonomous=True,
                reason_code="weather_research",
            )
        if "research" in text or "postgresql" in text:
            target = "software_release" if "postgresql" in text else "public_web"
            return SemanticTask(
                intent="public research",
                subjects=[SemanticSubject(target=target, reference="requested research")],
                operations=[SemanticOperation(kind="research", target=target)],
                data_dependencies=[
                    SemanticDataDependency(target=target, freshness="current")
                ],
                autonomous=True,
                reason_code="public_research",
            )
        if "inspect" in text or "review" in text:
            return SemanticTask(
                intent="inspect workspace",
                subjects=[SemanticSubject(target="workspace", reference="current workspace")],
                operations=[SemanticOperation(kind="inspect", target="workspace")],
                autonomous=True,
                reason_code="workspace_inspection",
            )
        return SemanticTask(
            intent="modify workspace",
            subjects=[SemanticSubject(target="workspace", reference="current workspace")],
            operations=[
                SemanticOperation(kind="inspect", target="workspace"),
                SemanticOperation(kind="modify", target="workspace"),
                SemanticOperation(kind="validate", target="workspace"),
            ],
            autonomous=True,
            multi_step=True,
            reason_code="workspace_mutation",
        )


@pytest.fixture(autouse=True)
def _default_v2_semantic_parser(monkeypatch):
    parser = _DefaultV2TestParser()
    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_ROUTING_MODE", "v2")
    monkeypatch.setattr(
        chat_bridge,
        "default_semantic_task_parser",
        lambda **_kwargs: parser,
    )


def test_direct_home_request_compiles_without_hermes() -> None:
    request = _direct_request(
        "Turn off the Desk Plug",
        session_id="chat-1",
        message_id="msg-1",
        capability_id="home.set_state",
    )
    assert request is not None
    assert request.action_id == "home.set_state"
    assert request.input == {"target": "Desk Plug", "state": "off"}
    assert request.proposal_id == "direct:chat-1:msg-1"


def test_open_ended_agentic_text_is_not_explicit_authority() -> None:
    decision = route_omnix_request("implement the missing feature")
    assert decision.lane == "agent"
    assert decision.explicit is False


def test_workspace_retry_phrase_enters_agent_lane() -> None:
    decision = route_omnix_request(
        "i didnt include the project folder before. try again in code"
    )
    assert decision.lane == "agent"
    assert decision.reason == "workspace_retry_request"


def test_chat_profile_selection_is_semantic_and_bounded() -> None:
    assert _select_profile("fix the repository tests") == "coding"
    assert _select_profile("fix the trading UI") == "coding"
    assert _select_profile("turn off the kitchen plug") == "house"
    assert _select_profile("check my calendar") == "personal-assistant"
    assert _select_profile("research this stock") == "trading-research"
    assert _select_profile("investigate this topic") == "research"


def test_coding_profile_selection_covers_live_chat_coding_prompts() -> None:
    assert _select_profile("implement a small improvement to the agent router") == "coding"
    assert _select_profile(
        "/agent In `src/app/agent_runtime/router.py`, add a short comment and run pytest"
    ) == "coding"
    assert _select_profile(
        "/agent Review router.py and chat_bridge.py for routing inconsistencies and run router tests"
    ) == "coding"
    assert _select_profile("Push the current branch to origin and open a pull request") == "coding"
    assert _select_profile("research NVDA stock and summarize today's catalysts") == "trading-research"


def test_agent_prefix_is_removed_before_building_task() -> None:
    assert _agent_task("/agent implement the router change") == "implement the router change"


def test_terse_follow_up_uses_recent_chat_context_to_select_coding_agent(monkeypatch, tmp_path) -> None:
    started = []

    class _Service:
        def start(self, spec):
            started.append(spec)
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                spec=spec,
            )

    class _ContextAwareClassifier:
        def __init__(self) -> None:
            self.seen: list[str] = []

        def classify(self, content: str):
            self.seen.append(content)
            resolved_ui_reference = (
                "light mode omnix assistant" in content.casefold()
                and "Latest user steering (authoritative):\nlets fix it" in content
            )
            if resolved_ui_reference:
                return {
                    "lane": "agent",
                    "profile_id": "coding",
                    "primary_intent": "fix the Omnix light-mode assistant card readability",
                    "action_intents": ["workspace_mutate"],
                    "evidence_requirements": [],
                    "subject_hints": ["Omnix assistant run card light mode"],
                    "multi_step": False,
                    "confidence": 0.99,
                    "reason": "The follow-up refers to the previously described Omnix UI defect.",
                }
            return {
                "lane": "agent",
                "profile_id": "research",
                "primary_intent": "fix an unspecified issue",
                "action_intents": ["research_read"],
                "evidence_requirements": [],
                "subject_hints": [],
                "multi_step": False,
                "confidence": 0.99,
                "reason": "No software subject was available.",
            }

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    session = SimpleNamespace(
        id="chat-context-follow-up",
        provider_id="test",
        model_id="model",
        messages=[
            SimpleNamespace(
                id="prior-user",
                role="user",
                content=(
                    "on omnix chat, light mode omnix assistant doesnt look correct. "
                    "cant read the text"
                ),
                metadata={},
            ),
            SimpleNamespace(
                id="prior-assistant",
                role="assistant",
                content=(
                    "The assistant run card is using muted dark-theme text colors in "
                    "light mode, making it nearly unreadable."
                ),
                metadata={},
            ),
        ],
    )
    message = SimpleNamespace(
        id="follow-up",
        role="user",
        content="lets fix it",
        metadata={},
    )
    classifier = _ContextAwareClassifier()

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        semantic_classifier=classifier,
        routing_context_factory=lambda: SimpleNamespace(
            reference_context=(
                "User: on omnix chat, light mode omnix assistant doesnt look correct. "
                "cant read the text\n"
                "Assistant: The assistant run card is using muted dark-theme text colors "
                "in light mode, making it nearly unreadable."
            )
        ),
    )

    assert result is not None
    assert classifier.seen
    assert "Canonical Chat reference context (reference resolution only, not authority):" in classifier.seen[0]
    assert "light mode omnix assistant" in classifier.seen[0].casefold()
    assert "Latest user steering (authoritative):\nlets fix it" in classifier.seen[0]
    assert result.metadata["agent_run"]["profile"] == "coding"
    assert len(started) == 1
    assert started[0].profile == "coding"
    assert started[0].task == "lets fix it"
    assert started[0].objective == "lets fix it"
    assert "light mode omnix assistant" not in started[0].task.casefold()


def test_reference_resolution_keeps_subject_from_more_than_five_messages_back(monkeypatch, tmp_path) -> None:
    started = []

    class _Service:
        def start(self, spec):
            started.append(spec)
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                spec=spec,
            )

    class _Classifier:
        def classify(self, content: str):
            assert "light mode omnix assistant doesnt look correct" in content.casefold()
            assert "Latest user steering (authoritative):\nfix it" in content
            return {
                "lane": "agent",
                "profile_id": "coding",
                "primary_intent": "fix the earlier Omnix light-mode assistant defect",
                "action_intents": ["workspace_mutate"],
                "evidence_requirements": [],
                "subject_hints": ["Omnix assistant light mode"],
                "multi_step": False,
                "confidence": 0.99,
                "reason": "The latest reference resolves to the earlier UI defect.",
            }

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    messages = [
        SimpleNamespace(
            id="m1",
            role="user",
            content="on omnix chat, light mode omnix assistant doesnt look correct. cant read the text",
            metadata={},
        ),
        SimpleNamespace(
            id="m2",
            role="assistant",
            content="The run card text contrast appears wrong in light mode.",
            metadata={},
        ),
        SimpleNamespace(id="m3", role="user", content="also check the spacing later", metadata={}),
        SimpleNamespace(id="m4", role="assistant", content="Okay.", metadata={}),
        SimpleNamespace(id="m5", role="user", content="what test suite covers this area?", metadata={}),
        SimpleNamespace(id="m6", role="assistant", content="The web component tests cover the card.", metadata={}),
        SimpleNamespace(id="m7", role="user", content="and keep the dark mode unchanged", metadata={}),
        SimpleNamespace(id="m8", role="assistant", content="Understood.", metadata={}),
    ]
    session = SimpleNamespace(
        id="chat-long-reference",
        provider_id="test",
        model_id="model",
        messages=messages,
    )
    message = SimpleNamespace(id="m9", role="user", content="fix it", metadata={})

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        semantic_classifier=_Classifier(),
        routing_context_factory=lambda: SimpleNamespace(
            reference_context="\n".join(
                f"{'User' if item.role == 'user' else 'Assistant'}: {item.content}"
                for item in messages
            )
        ),
    )

    assert result is not None
    assert result.metadata["agent_run"]["profile"] == "coding"
    assert len(started) == 1
    assert started[0].task == "fix it"
    assert "light mode omnix assistant" not in started[0].task.casefold()


def test_natural_continuation_uses_context_without_reference_regex(monkeypatch, tmp_path) -> None:
    started = []

    class _Service:
        def start_with_context(self, spec, *, reference_context=""):
            started.append((spec, reference_context))
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                spec=spec,
            )

    class _ContextAwareClassifier:
        def classify(self, content: str):
            assert "light-mode Agent card" in content
            assert "Latest user steering (authoritative):\nmake the button bigger" in content
            return {
                "lane": "agent",
                "profile_id": "coding",
                "primary_intent": "increase the earlier Omnix button size",
                "action_intents": ["workspace_mutate"],
                "evidence_requirements": [],
                "subject_hints": ["Omnix Agent card button"],
                "multi_step": False,
                "confidence": 0.99,
                "reason": "The continuation refers to the earlier UI subject.",
            }

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    session = SimpleNamespace(
        id="chat-natural-continuation",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="m9",
        role="user",
        content="make the button bigger",
        metadata={},
    )
    context = (
        "User: the button on the light-mode Agent card is too small\n"
        "Assistant: I can adjust that UI control."
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        semantic_classifier=_ContextAwareClassifier(),
        routing_context_factory=lambda: SimpleNamespace(reference_context=context),
    )

    assert result is not None
    assert result.metadata["agent_run"]["profile"] == "coding"
    assert len(started) == 1
    spec, passed_context = started[0]
    assert spec.task == "make the button bigger"
    assert passed_context == context


def test_direct_request_does_not_build_canonical_routing_context() -> None:
    calls = []
    session = SimpleNamespace(id="chat-direct", provider_id="test", model_id="model", messages=[])
    message = SimpleNamespace(
        id="direct",
        role="user",
        content="turn off the desk plug",
        metadata={},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        routing_context_factory=lambda: calls.append("built"),
    )

    assert result is not None
    assert calls == []


def test_initial_agent_context_is_ephemeral_and_not_persisted_in_task(monkeypatch, tmp_path) -> None:
    captured = []

    class _Service:
        def start_with_context(self, spec, *, reference_context=""):
            captured.append((spec, reference_context))
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                spec=spec,
            )

    class _Classifier:
        def classify(self, content: str):
            return {
                "lane": "agent",
                "profile_id": "coding",
                "primary_intent": "fix the Omnix light-mode card",
                "action_intents": ["workspace_mutate"],
                "evidence_requirements": [],
                "subject_hints": ["Omnix light mode"],
                "multi_step": False,
                "confidence": 0.99,
                "reason": "Resolved from prior conversation.",
            }

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    session = SimpleNamespace(id="chat-clean-context", provider_id="test", model_id="model", messages=[])
    message = SimpleNamespace(id="m9", role="user", content="fix it", metadata={})
    context = "User: the Omnix light-mode Agent card text is unreadable"

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        semantic_classifier=_Classifier(),
        routing_context_factory=lambda: SimpleNamespace(reference_context=context),
    )

    assert result is not None
    assert len(captured) == 1
    spec, passed_context = captured[0]
    assert spec.task == "fix it"
    assert spec.objective == "fix it"
    assert context not in spec.model_dump_json()
    assert passed_context == context


def test_active_agent_steering_carries_reference_context_without_widening_message() -> None:
    captured = []

    snapshot = SimpleNamespace(
        run_id="run-active",
        status="running",
        revision=3,
        last_error=None,
        spec=AgentRunSpec(
            run_id="run-active",
            task="Inspect the current repository issue",
            objective="Inspect the current repository issue",
            profile="coding",
            model=ModelRef(provider_id="test", model_id="model"),
            capabilities=["workspace.read", "workspace.edit", "workspace.test"],
        ),
    )

    class _Service:
        def command_with_context(self, command, *, reference_context=""):
            captured.append((command, reference_context))
            return snapshot

    decision = route_omnix_request("fix it")
    context = "User: the Omnix light-mode Agent card text is unreadable"

    result = chat_bridge._continue_agent_run(
        _Service(),
        snapshot,
        "fix it",
        decision,
        reference_context=context,
    )

    assert result is not None
    assert len(captured) == 1
    command, passed_context = captured[0]
    assert command.payload["message"] == "fix it"
    assert "reference_context" not in command.payload
    assert passed_context == context
    assert "light-mode Agent card" not in command.payload["message"]


def test_repeated_steering_text_with_different_context_has_distinct_idempotency() -> None:
    captured = []
    snapshot = SimpleNamespace(
        run_id="run-active",
        status="running",
        revision=3,
        last_error=None,
        spec=AgentRunSpec(
            run_id="run-active",
            task="Inspect the repository",
            objective="Inspect the repository",
            profile="coding",
            model=ModelRef(provider_id="test", model_id="model"),
            capabilities=["workspace.read", "workspace.edit", "workspace.test"],
        ),
    )

    class _Service:
        def command(self, command):
            captured.append(command)
            return snapshot

    decision = route_omnix_request("fix it")
    for context in ("User: fix issue A", "User: fix issue B"):
        chat_bridge._continue_agent_run(
            _Service(),
            snapshot,
            "fix it",
            decision,
            reference_context=context,
        )

    assert captured[0].idempotency_key != captured[1].idempotency_key


def test_chat_created_agent_runs_disable_reasoning_by_default(monkeypatch, tmp_path) -> None:
    started = []

    class _Service:
        def start(self, spec):
            started.append(spec)
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                spec=spec,
            )

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    monkeypatch.delenv("OMNIX_AGENT_REASONING_EFFORT", raising=False)
    session = SimpleNamespace(id="chat-1", provider_id="test", model_id="model", messages=[])
    message = SimpleNamespace(
        id="message-1",
        content="/agent implement a small improvement to the agent router",
        metadata={},
    )

    result = route_typed_chat_turn(session, message, provider_id="test", model_id="model")

    assert result is not None
    assert len(started) == 1
    assert started[0].model.reasoning_effort == "none"


def test_stale_shadow_environment_cannot_restore_legacy_production(monkeypatch, tmp_path) -> None:
    started = []

    class _Service:
        def get(self, _run_id):
            return None

        def start(self, spec):
            started.append(spec)
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                superseded_by_run_id=None,
                spec=spec,
            )

    class _ChatParser:
        def parse(self, _content):
            return SemanticTask(
                intent="discuss UI appearance",
                operations=[
                    SemanticOperation(kind="explain", target="conversation")
                ],
                autonomous=False,
                multi_step=False,
                ambiguity="none",
                reason_code="conversation",
            )

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_ROUTING_MODE", "shadow")
    session = SimpleNamespace(
        id="chat-shadow",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-shadow",
        content="in omnix, the plus sign on assistant-context-add-button should be centered",
        metadata={},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        semantic_classifier=_ChatParser(),
    )

    assert result is None
    assert started == []
    assert message.metadata["routing_decision"]["production_router"] == "semantic_v2"
    assert message.metadata["routing_decision"]["production_lane"] == "chat"
    assert "legacy" not in message.metadata["routing_decision"]


def test_stale_shadow_environment_keeps_semantic_v2_profile(monkeypatch, tmp_path) -> None:
    class _CodingParser:
        def parse_contextual(self, _content, **_kwargs):
            return SemanticTask(
                intent="modify software workspace",
                subjects=[SemanticSubject(target="workspace", reference="current workspace")],
                operations=[SemanticOperation(kind="modify", target="workspace")],
                autonomous=True,
                reason_code="workspace_mutation",
            )

    started = []

    class _Service:
        def get(self, _run_id):
            return None

        def start(self, spec):
            started.append(spec)
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                superseded_by_run_id=None,
                spec=spec,
            )

    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_ROUTING_MODE", "shadow")
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    session = SimpleNamespace(id="shadow-profile", provider_id="test", model_id="model", messages=[])
    message = SimpleNamespace(
        id="shadow-profile-message",
        content="fix the bedroom light; it won't turn on",
        metadata={},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        semantic_classifier=_CodingParser(),
    )

    assert result is not None
    routing = result.metadata["routing_decision"]
    assert routing["production_router"] == "semantic_v2"
    assert routing["production_lane"] == "agent"
    assert routing["semantic_v2"]["lane"] == "agent"
    assert started[0].profile == "coding"
    assert "legacy" not in routing


def test_required_chat_evidence_is_retrieved_and_injected_before_provider(monkeypatch) -> None:
    class _ResearchParser:
        def parse_contextual(self, _content, **_kwargs):
            return SemanticTask(
                intent="check a current public fact",
                operations=[SemanticOperation(kind="read", target="public_web")],
                data_dependencies=[
                    SemanticDataDependency(
                        target="public_web",
                        freshness="current",
                    )
                ],
                autonomous=False,
                multi_step=False,
                reason_code="bounded_current_lookup",
            )

    monkeypatch.setattr(
        chat_bridge,
        "validate_required_evidence_capabilities",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        chat_bridge,
        "review_assistant_tool_request",
        lambda _request: SimpleNamespace(
            allowed=True,
            executable=True,
            approval_required=False,
            reason=None,
            result_summary="",
        ),
    )
    monkeypatch.setattr(
        chat_bridge,
        "hermes_assistant_tool_execute_payload",
        lambda _content, request: SimpleNamespace(
            execution_result=AssistantToolResult(
                tool_id=request.tool_id,
                action_id=request.action_id,
                session_id=request.session_id,
                result_summary="Found current sources.",
                output={
                    "items": [
                        {
                            "title": "Current source",
                            "url": "https://example.com/current",
                            "snippet": "Current verified fact",
                        }
                    ],
                    "source_count": 1,
                    "provider": "test-search",
                },
            )
        ),
    )

    context_items = []
    session = SimpleNamespace(id="chat-evidence", provider_id="test", model_id="model", messages=[])
    message = SimpleNamespace(
        id="chat-evidence-message",
        content="is the current public status still the same?",
        metadata={},
    )
    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        context_items=context_items,
        semantic_classifier=_ResearchParser(),
    )

    assert result is None
    assert context_items
    assert context_items[-1]["source_id"].startswith("omnix-evidence:")
    assert message.metadata["semantic_evidence_set"]["passed"] is True


def test_explicit_agent_syntax_remains_available_when_semantic_parser_is_unavailable(monkeypatch) -> None:
    session = SimpleNamespace(
        id="chat-parser-down",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-parser-down",
        content="/agent fix the issue we discussed earlier",
        metadata={},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        semantic_classifier=None,
    )

    assert result is not None
    assert result.metadata["agent_mode"] is True
    assert result.metadata["omnix_route"]["lane"] == "agent"
    assert result.metadata["routing_decision"]["production_router"] == "semantic_v2"
    assert "semantic_gate" not in result.metadata


def test_chat_created_agent_reasoning_can_be_overridden(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_AGENT_REASONING_EFFORT", "high")
    assert chat_bridge._agent_reasoning_effort() == "high"


def test_explicit_agent_start_failure_does_not_fall_back_to_chat(monkeypatch, tmp_path) -> None:
    class _FailingService:
        def start(self, _spec):
            raise RuntimeError("pi executable unavailable")

        def get(self, _run_id):
            return None

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _FailingService())
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    session = SimpleNamespace(
        id="chat-1",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-1",
        content="/agent implement a small improvement to the agent router",
        metadata={},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
    )

    assert result is not None
    assert "failed to start" in result.content
    assert result.metadata["omnix_route"]["lane"] == "agent"
    assert result.metadata["agent_start"]["durable"] is False


def test_publication_request_is_rejected_before_start_without_github_authority(monkeypatch, tmp_path) -> None:
    started = []

    class _Service:
        def start(self, spec):
            started.append(spec)
            raise AssertionError("publication request must not start a local-only run")

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    session = SimpleNamespace(
        id="chat-1",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-1",
        content="/agent Push the current branch to origin and open a pull request",
        metadata={},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
    )

    assert result is not None
    assert result.metadata["agent_start"]["status"] == "rejected"
    assert result.metadata["agent_start"]["reason"] == "github_publication_capability_not_issued"
    assert started == []


def test_research_request_starts_without_workspace(monkeypatch) -> None:
    started = []

    class _Service:
        def start(self, spec):
            started.append(spec)
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                spec=spec,
            )

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_REPOSITORY", raising=False)
    session = SimpleNamespace(
        id="chat-1",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-1",
        content="/agent research the latest PostgreSQL maintenance release",
        metadata={},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
    )

    assert result is not None
    assert result.metadata["agent_run"]["profile"] == "research"
    assert len(started) == 1
    assert started[0].workspace is None
    assert started[0].external_capabilities == ["research.web_search"]


def test_quick_search_informational_turn_bypasses_agent_planner() -> None:
    session = SimpleNamespace(
        id="chat-1",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-1",
        content="hows the weather in Vancouver right now?",
        metadata={"agent_mode": True, "research_mode": "quick"},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        context_items=[{"source_id": "web_search", "content": "Current weather"}],
    )

    assert result is None


def test_explicit_agent_request_still_uses_agent_lane_with_quick_search(monkeypatch) -> None:
    started = []

    class _Service:
        def start(self, spec):
            started.append(spec)
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                spec=spec,
            )

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    session = SimpleNamespace(
        id="chat-1",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-1",
        content="/agent research Vancouver weather sources",
        metadata={"agent_mode": True, "research_mode": "quick"},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
        context_items=[{"source_id": "web_search", "content": "Current weather"}],
    )

    assert result is not None
    assert result.metadata["agent_run"]["profile"] == "research"
    assert len(started) == 1


def test_trade_execution_request_is_rejected_before_start(monkeypatch) -> None:
    started = []

    class _Service:
        def start(self, spec):
            started.append(spec)
            raise AssertionError("research profile must not start for trade execution")

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_REPOSITORY", raising=False)
    session = SimpleNamespace(
        id="chat-1",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-1",
        content="/agent Buy 10 shares of NVDA",
        metadata={},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
    )

    assert result is not None
    assert result.metadata["agent_start"]["status"] == "rejected"
    assert result.metadata["agent_start"]["reason"] == "trading_execution_capability_not_issued"
    assert started == []


def test_read_only_runs_defer_workspace_mutation_to_revision_compiler_and_reject_trading_mutation() -> None:
    def snapshot(profile: str):
        return SimpleNamespace(
            run_id="run-1",
            status="running",
            revision=1,
            last_error=None,
            spec=AgentRunSpec(
                run_id="run-1",
                task="research",
                profile=profile,
                model=ModelRef(provider_id="test", model_id="model"),
                capabilities=[],
                external_capabilities=["research.web_search"],
            ),
        )

    workspace_rejection = _unauthorized_agent_command(
        snapshot("research"),
        "edit the repository based on those findings",
    )
    trading_rejection = _unauthorized_agent_command(snapshot("trading-research"), "Buy 10 shares.")

    assert workspace_rejection is None
    assert trading_rejection is not None
    assert trading_rejection["reason"] == "trading_execution_capability_not_issued"


def test_read_only_run_rejects_publication_without_github_capability() -> None:
    snapshot = SimpleNamespace(
        run_id="run-1",
        status="running",
        revision=1,
        last_error=None,
        spec=AgentRunSpec(
            run_id="run-1",
            task="coding",
            profile="coding",
            model=ModelRef(provider_id="test", model_id="model"),
            capabilities=["workspace.command"],
            external_capabilities=[],
        ),
    )

    rejection = _unauthorized_agent_command(snapshot, "push the current branch and open a pull request")

    assert rejection is not None
    assert rejection["reason"] == "github_publication_capability_not_issued"


def test_live_voice_metadata_can_be_detected_without_session_state() -> None:
    from app.agent_runtime.chat_bridge import _is_live_voice
    message = SimpleNamespace(metadata={"speech_segment_id": "voice-segment:abc"})
    assert _is_live_voice(message) is True



def test_attached_local_folder_overrides_default_coding_workspace(monkeypatch, tmp_path) -> None:
    selected = tmp_path / "selected"
    default = tmp_path / "default"
    selected.mkdir()
    default.mkdir()
    started = []

    class _Service:
        def start(self, spec):
            started.append(spec)
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                spec=spec,
            )

        def get(self, _run_id):
            return None

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(default))
    session = SimpleNamespace(
        id="chat-workspace",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-workspace",
        content="/agent inspect the repository tests",
        metadata={"workspace_root": str(selected)},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
    )

    assert result is not None
    assert len(started) == 1
    workspace = started[0].workspace
    assert workspace is not None
    assert workspace.root == str(selected.resolve())
    assert workspace.repository is None
    assert workspace.worktree is None


def test_attached_local_folder_allows_ui_agent_action_during_research_turn(
    monkeypatch,
    tmp_path,
) -> None:
    selected = tmp_path / "omnix"
    selected.mkdir()
    started = []

    class _Service:
        def start(self, spec):
            started.append(spec)
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                spec=spec,
            )

        def get(self, _run_id):
            return None

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_REPOSITORY", raising=False)
    session = SimpleNamespace(
        id="chat-attached-ui-action",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-attached-ui-action",
        content="in omnix chat, increase the distance between the full screen and personality button",
        metadata={
            "workspace_root": str(selected),
            "research_mode": "quick",
            "coding_approval_policy": "always_ask",
        },
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
    )

    assert result is not None
    assert len(started) == 1
    assert result.metadata["request_mode"]["mode"] == "agent"
    assert result.metadata["request_mode"]["source"] == "classifier"
    assert started[0].profile == "coding"
    assert started[0].workspace.root == str(selected.resolve())
    assert started[0].approval_policy == "always_ask"
    assert {
        "workspace.edit",
        "workspace.write",
        "workspace.command",
        "workspace.test",
    }.issubset(started[0].capabilities)
    assert started[0].expected_artifacts == ["diff"]


def test_coding_retry_reuses_prior_request_after_workspace_unavailable_message(
    monkeypatch,
    tmp_path,
) -> None:
    selected = tmp_path / "omnix"
    selected.mkdir()
    started = []

    class _Service:
        def start(self, spec):
            started.append(spec)
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                spec=spec,
            )

        def get(self, _run_id):
            return None

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_REPOSITORY", raising=False)
    original_task = "can you change the text personality to profile. make the change."
    session = SimpleNamespace(
        id="chat-workspace-retry-message",
        provider_id="test",
        model_id="model",
        messages=[
            SimpleNamespace(
                id="message-original-coding-task",
                role="user",
                content=original_task,
                metadata={},
            ),
            SimpleNamespace(
                id="message-workspace-unavailable",
                role="assistant",
                content=(
                    "I still don't have access to the project folder in the coding "
                    "workspace—only the image is available."
                ),
                metadata={},
            ),
        ],
    )
    message = SimpleNamespace(
        id="message-coding-retry",
        role="user",
        content="i didnt include the project folder before. try again in code",
        metadata={"workspace_root": str(selected)},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
    )

    assert result is not None
    assert len(started) == 1
    assert started[0].task == original_task
    assert started[0].profile == "coding"
    assert started[0].workspace.root == str(selected.resolve())
    assert result.metadata["agent_retry"]["task"] == original_task


def test_launcher_default_workspace_allows_ui_agent_action_during_research_turn(
    monkeypatch,
    tmp_path,
) -> None:
    started = []

    class _Service:
        def start(self, spec):
            started.append(spec)
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                spec=spec,
            )

        def get(self, _run_id):
            return None

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    session = SimpleNamespace(
        id="chat-default-ui-action",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-default-ui-action",
        content=(
            "in omnix chat, increase the distance between the full screen and "
            "personality button. theyre too close. lets fix it"
        ),
        metadata={"research_mode": "quick"},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
    )

    assert result is not None
    assert len(started) == 1
    assert result.metadata["request_mode"]["mode"] == "agent"
    assert started[0].profile == "coding"
    assert started[0].workspace.root == str(tmp_path)
    assert "workspace.edit" in started[0].capabilities


def test_workspace_action_without_workspace_fails_deterministically_during_research_turn(
    monkeypatch,
) -> None:
    class _Service:
        def start(self, _spec):
            raise AssertionError("workspace preflight must fail before runtime start")

        def get(self, _run_id):
            return None

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_REPOSITORY", raising=False)
    session = SimpleNamespace(
        id="chat-missing-workspace-ui-action",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-missing-workspace-ui-action",
        content="inspect the omnix repository and report the fullscreen button margin",
        metadata={"research_mode": "quick"},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
    )

    assert result is not None
    assert result.metadata["agent_start"]["status"] == "failed"
    assert result.metadata["agent_start"]["reason"] == "workspace_required"
    assert "Attach a Local folder and send \"try again\"" in result.content


def test_attached_workspace_localizes_repo_contents_evidence() -> None:
    compilation = SemanticTaskCompilation(
        lane="agent",
        profile_id="coding",
        action_intents=["workspace_mutate"],
        evidence_decision=EvidenceDecision(
            policy=EvidencePolicy(
                requirement="required",
                requirements=[
                    EvidenceRequirement(
                        id="current-repo",
                        source_class="repo_contents",
                        freshness="current",
                    )
                ],
            )
        ),
    )
    message = SimpleNamespace(metadata={"workspace_root": "F:/LLM/omnix"})

    localized = chat_bridge._localize_attached_workspace_evidence(
        message,
        compilation,
    )

    assert localized is not None
    assert localized.evidence_decision.policy.requirement == "none"
    assert localized.evidence_decision.policy.requirements == []
    assert localized.evidence_decision.reason == "attached_workspace_local_authority"


def test_try_again_restarts_immediately_preceding_failed_agent_with_attached_workspace(
    monkeypatch,
    tmp_path,
) -> None:
    selected = tmp_path / "omnix"
    selected.mkdir()
    started = []

    class _Service:
        def start(self, spec):
            started.append(spec)
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                spec=spec,
            )

        def get(self, _run_id):
            return None

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_REPOSITORY", raising=False)
    task = (
        "in omnix chat, increase the distance between the full screen and "
        "personality button. theyre too close. lets fix it"
    )
    session = SimpleNamespace(
        id="chat-retry-failed-agent",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    original = SimpleNamespace(
        id="message-original",
        role="user",
        content=task,
        metadata={},
    )

    failed = route_typed_chat_turn(
        session,
        original,
        provider_id="test",
        model_id="model",
    )

    assert failed is not None
    assert failed.metadata["agent_start"]["status"] == "failed"
    assert failed.metadata["agent_run"]["task"] == task
    assert started == []
    session.messages = [
        original,
        SimpleNamespace(
            id="message-failed-agent",
            role="assistant",
            content=failed.content,
            metadata=failed.metadata,
        ),
    ]
    retry = SimpleNamespace(
        id="message-retry",
        role="user",
        content="try agian",
        metadata={"workspace_root": str(selected)},
    )

    result = route_typed_chat_turn(
        session,
        retry,
        provider_id="test",
        model_id="model",
    )

    assert result is not None
    assert len(started) == 1
    assert started[0].task == task
    assert started[0].profile == "coding"
    assert started[0].workspace.root == str(selected.resolve())
    assert result.metadata["agent_retry"] == {
        "status": "started",
        "failed_message_id": "message-failed-agent",
        "task": task,
        "profile": "coding",
    }


def test_try_again_does_not_replay_a_stale_failed_agent_request(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    failed_metadata = {
        "agent_start": {"status": "failed", "durable": False},
        "agent_run": {
            "run_id": None,
            "status": "failed",
            "profile": "coding",
            "task": "change the workspace",
        },
    }
    session = SimpleNamespace(
        id="chat-stale-retry",
        provider_id="test",
        model_id="model",
        messages=[
            SimpleNamespace(
                id="failed",
                role="assistant",
                content="Agent request could not start",
                metadata=failed_metadata,
            ),
            SimpleNamespace(
                id="intervening-user",
                role="user",
                content="something else",
                metadata={},
            ),
        ],
    )
    message = SimpleNamespace(
        id="retry",
        role="user",
        content="try again",
        metadata={},
    )

    assert chat_bridge._pending_failed_agent_retry(session, message) is None


def test_attached_local_folder_does_not_grant_workspace_to_research_profile(
    monkeypatch,
    tmp_path,
) -> None:
    started = []

    class _Service:
        def start(self, spec):
            started.append(spec)
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                spec=spec,
            )

        def get(self, _run_id):
            return None

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_REPOSITORY", raising=False)
    session = SimpleNamespace(
        id="chat-research-workspace",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-research-workspace",
        content="/agent research the latest PostgreSQL maintenance release",
        metadata={"workspace_root": str(tmp_path / "does-not-need-to-exist")},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
    )

    assert result is not None
    assert len(started) == 1
    assert started[0].profile == "research"
    assert started[0].workspace is None


def test_invalid_attached_local_folder_fails_coding_run_before_start(
    monkeypatch,
    tmp_path,
) -> None:
    started = []

    class _Service:
        def start(self, spec):
            started.append(spec)
            raise AssertionError("invalid workspace must not reach runtime start")

        def get(self, _run_id):
            return None

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_REPOSITORY", raising=False)
    session = SimpleNamespace(
        id="chat-invalid-workspace",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="message-invalid-workspace",
        content="/agent inspect the repository tests",
        metadata={"workspace_root": str(tmp_path / "missing")},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
    )

    assert result is not None
    assert started == []
    assert result.metadata["agent_start"]["status"] == "failed"
    assert "does not exist" in result.metadata["agent_start"]["error"]



def test_active_agent_rejects_switch_to_different_attached_workspace(
    monkeypatch,
    tmp_path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    snapshot = SimpleNamespace(
        run_id="active-workspace-run",
        status="running",
        revision=1,
        last_error=None,
        spec=AgentRunSpec(
            run_id="active-workspace-run",
            session_id="chat-active-workspace",
            task="inspect tests",
            profile="coding",
            model=ModelRef(provider_id="test", model_id="model"),
            capabilities=["workspace.read"],
            workspace=WorkspaceSpec(root=str(first)),
        ),
    )

    class _Service:
        def get(self, run_id):
            return snapshot if run_id == snapshot.run_id else None

        def command(self, _command):
            raise AssertionError("workspace-mismatched steering must not reach the active run")

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    session = SimpleNamespace(
        id="chat-active-workspace",
        provider_id="test",
        model_id="model",
        messages=[
            SimpleNamespace(
                role="assistant",
                metadata={"agent_run": {"run_id": snapshot.run_id}},
            )
        ],
    )
    message = SimpleNamespace(
        id="message-switch-workspace",
        content="/agent inspect the repository tests",
        metadata={"workspace_root": str(second)},
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
    )

    assert result is not None
    assert result.metadata["agent_start"]["status"] == "rejected"
    assert result.metadata["agent_start"]["reason"] == "active_run_workspace_mismatch"
    assert "different Local folder" in result.content



def test_agent_reference_images_accept_supported_chat_data_url() -> None:
    images = chat_bridge._agent_reference_images(
        {"image_data_url": "data:image/png;base64,YWJj"}
    )
    assert images == [
        {"type": "image", "data": "YWJj", "mimeType": "image/png"}
    ]
    assert chat_bridge._agent_reference_images(
        {"image_data_url": "data:text/plain;base64,YWJj"}
    ) == []


def test_agent_chat_forwards_image_attachment_to_runtime(monkeypatch, tmp_path) -> None:
    started = []

    class _Service:
        def start_with_context(
            self,
            spec,
            *,
            reference_context="",
            reference_images=None,
        ):
            started.append((spec, reference_context, reference_images))
            return SimpleNamespace(
                run_id=spec.run_id,
                status="running",
                revision=1,
                last_error=None,
                spec=spec,
            )

    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: _Service())
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    session = SimpleNamespace(
        id="chat-image-agent",
        provider_id="test",
        model_id="model",
        messages=[],
    )
    message = SimpleNamespace(
        id="image-turn",
        role="user",
        content="fix the light mode UI style shown in the image",
        metadata={
            "agent_mode": True,
            "image_data_url": "data:image/webp;base64,YWJj",
        },
    )

    result = route_typed_chat_turn(
        session,
        message,
        provider_id="test",
        model_id="model",
    )

    assert result is not None
    assert result.metadata["agent_run"]["profile"] == "coding"
    assert len(started) == 1
    spec, _context, images = started[0]
    assert spec.task == "fix the light mode UI style shown in the image"
    assert images == [
        {"type": "image", "data": "YWJj", "mimeType": "image/webp"}
    ]
