from __future__ import annotations

import json
from types import SimpleNamespace

from app.agent_runtime import chat_bridge
from app.agent_runtime.semantic_task import (
    SemanticOperation,
    SemanticSubject,
    SemanticTask,
)
from app.chat.models import CreateChatSessionRequest, SendChatMessageRequest
from app.chat.prompt_store import ChatSessionStore
from app.providers.base import BaseProvider, ChatResponse, ProviderConfig


class _WorkspaceMutationParser:
    def __init__(self) -> None:
        self.deadlines = []

    def parse_contextual(self, _content: str, **_kwargs) -> SemanticTask:
        self.deadlines.append(_kwargs.get("deadline_at"))
        return SemanticTask(
            intent="change a label in the Omnix chat workspace",
            subjects=[
                SemanticSubject(
                    target="workspace",
                    reference="Personality label in Omnix chat",
                )
            ],
            operations=[
                SemanticOperation(kind="inspect", target="workspace"),
                SemanticOperation(kind="modify", target="workspace"),
                SemanticOperation(kind="validate", target="workspace"),
            ],
            autonomous=True,
            multi_step=True,
            reason_code="workspace_mutation",
        )


class _DurableRecordingService:
    def __init__(self) -> None:
        self.runs = {}

    def get(self, run_id):
        return self.runs.get(run_id)

    def start(self, spec):
        snapshot = SimpleNamespace(
            run_id=spec.run_id,
            status="running",
            revision=1,
            last_error=None,
            superseded_by_run_id=None,
            spec=spec,
        )
        self.runs[spec.run_id] = snapshot
        return snapshot


class _SemanticCodexProvider(BaseProvider):
    provider_name = "chatgpt_codex"

    def __init__(self) -> None:
        super().__init__(
            ProviderConfig(
                provider_type="chatgpt_codex",
                model="gpt-test",
            )
        )
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
            content=json.dumps(
                {
                    "intent": "change a label in the Omnix chat workspace",
                    "subjects": [
                        {
                            "target": "workspace",
                            "reference": "Personality label in Omnix chat",
                            "kind": "software_ui",
                        }
                    ],
                    "operations": [
                        {"kind": "inspect", "target": "workspace"},
                        {"kind": "modify", "target": "workspace"},
                        {"kind": "validate", "target": "workspace"},
                    ],
                    "data_dependencies": [],
                    "autonomous": True,
                    "multi_step": True,
                    "ambiguity": "none",
                    "candidate_interpretations": [],
                    "confidence": 0.99,
                    "reason_code": "workspace_mutation",
                }
            ),
            model=model or "gpt-test",
            finish_reason="stop",
        )

    def get_models(self):
        return []

    def test_connection(self):
        return True


def test_exact_workspace_prompt_starts_durable_agent_before_chat_provider(
    monkeypatch,
    tmp_path,
) -> None:
    service = _DurableRecordingService()
    provider_calls = []

    parser = _WorkspaceMutationParser()

    class _Provider:
        config = SimpleNamespace(timeout=15)

        def chat_completion(self, **kwargs):
            provider_calls.append(kwargs)
            raise AssertionError("Agent-routed turn reached the ordinary Chat provider")

    import app.shared as shared

    monkeypatch.setattr(
        chat_bridge,
        "default_semantic_task_parser",
        lambda **_kwargs: parser,
    )
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)
    monkeypatch.setattr(shared, "get_provider", lambda _provider_id: _Provider())
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    # A stale inherited value must have no effect now that legacy v1 is gone.
    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_ROUTING_MODE", "shadow")

    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(
        CreateChatSessionRequest(
            title="Agent handoff",
            provider_id="test-provider",
            model_id="test-model",
        )
    )
    turn = store.begin_user_message(
        session.id,
        SendChatMessageRequest(
            content="change the title personality to profile in omnix chat",
            provider_id="test-provider",
            model_id="test-model",
        ),
    )
    assert turn is not None
    routed_session, user_message = turn

    events = list(
        store.stream_provider_reply_chunks(
            routed_session,
            user_message,
            provider_id="test-provider",
            model_id="test-model",
        )
    )

    completed = events[-1]
    assert completed["type"] == "complete"
    assert completed["content"].startswith("Started coding Agent run ")
    assert provider_calls == []
    assert parser.deadlines and parser.deadlines[0] is not None
    assert len(service.runs) == 1
    snapshot = next(iter(service.runs.values()))
    assert snapshot.spec.profile == "coding"
    assert snapshot.spec.task.startswith(
        "change the title personality to profile in omnix chat"
    )
    assert "ChatIdentityModeControl.tsx" in snapshot.spec.task
    assert "use `Profile`" in snapshot.spec.task
    assert completed["metadata"]["routing_decision"] == {
        "production_router": "semantic_v2",
        "production_lane": "agent",
        "semantic_v2": completed["metadata"]["omnix_route"],
    }


def test_normalized_codex_provider_and_quick_research_start_exact_workspace_agent(
    monkeypatch,
    tmp_path,
) -> None:
    import app.shared as shared

    service = _DurableRecordingService()
    provider = _SemanticCodexProvider()
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)
    monkeypatch.setattr(shared, "get_provider", lambda _provider_id: provider)
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))
    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_TASK_PARSER_MODE", "auto")
    monkeypatch.delenv("OMNIX_AGENT_SEMANTIC_TASK_PARSER_PROVIDER", raising=False)
    monkeypatch.delenv("OMNIX_AGENT_SEMANTIC_CLASSIFIER_PROVIDER", raising=False)

    store = ChatSessionStore(tmp_path / "normalized-provider-chat.json")
    session = store.create_session(
        CreateChatSessionRequest(
            title="Normalized Codex routing",
            provider_id="chatgpt_codex",
            model_id=None,
            research_mode_override="quick",
        )
    )
    turn = store.begin_user_message(
        session.id,
        SendChatMessageRequest(
            content="change the title personality to profile in omnix chat",
            provider_id="chatgpt_codex",
            model_id=None,
            research_mode="quick",
        ),
    )
    assert turn is not None
    routed_session, user_message = turn

    events = list(
        store.stream_provider_reply_chunks(
            routed_session,
            user_message,
            provider_id="chatgpt_codex",
            model_id=None,
        )
    )

    completed = events[-1]
    assert completed["type"] == "complete"
    assert completed["content"].startswith("Started coding Agent run ")
    assert completed["metadata"]["routing_decision"]["production_lane"] == "agent"
    assert completed["metadata"]["request_mode"]["mode"] == "agent"
    assert len(service.runs) == 1
    assert len(provider.calls) == 1
    assert provider.calls[0]["stream"] is False


def test_lmstudio_optimized_stream_cannot_bypass_agent_boundary(monkeypatch, tmp_path) -> None:
    service = _DurableRecordingService()
    parser = _WorkspaceMutationParser()
    provider_calls = []

    class _LmStudioProvider:
        provider_name = "lmstudio"
        config = SimpleNamespace(timeout=15)

        def chat_completion(self, **kwargs):
            provider_calls.append(kwargs)
            raise AssertionError("LM Studio optimized Chat stream bypassed Agent routing")

    import app.shared as shared

    monkeypatch.setattr(chat_bridge, "default_semantic_task_parser", lambda **_kwargs: parser)
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)
    monkeypatch.setattr(shared, "get_provider", lambda _provider_id: _LmStudioProvider())
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", str(tmp_path))

    store = ChatSessionStore(tmp_path / "lmstudio-boundary-chat.json")
    session = store.create_session(
        CreateChatSessionRequest(
            title="LM Studio Agent handoff",
            provider_id="lmstudio",
            model_id="local-model",
        )
    )
    turn = store.begin_user_message(
        session.id,
        SendChatMessageRequest(
            content="change the title personality to profile in omnix chat",
            provider_id="lmstudio",
            model_id="local-model",
        ),
    )
    assert turn is not None

    routed_session, user_message = turn
    events = list(
        store.stream_provider_reply_chunks(
            routed_session,
            user_message,
            provider_id="lmstudio",
            model_id="local-model",
        )
    )

    assert events[-1]["content"].startswith("Started coding Agent run ")
    assert provider_calls == []
    assert parser.deadlines and parser.deadlines[0] is not None
    assert len(service.runs) == 1


def test_semantic_required_quick_research_turn_fails_closed_without_parser(
    monkeypatch,
    tmp_path,
) -> None:
    provider_calls = []

    class _Provider:
        def chat_completion(self, **kwargs):
            provider_calls.append(kwargs)
            raise AssertionError("unclassified turn reached ordinary Chat")

    import app.shared as shared

    monkeypatch.setattr(
        chat_bridge,
        "default_semantic_task_parser",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(shared, "get_provider", lambda _provider_id: _Provider())

    store = ChatSessionStore(tmp_path / "missing-parser-chat.json")
    session = store.create_session(
        CreateChatSessionRequest(
            title="Missing parser",
            provider_id="chatgpt_codex",
            research_mode_override="quick",
        )
    )
    turn = store.begin_user_message(
        session.id,
        SendChatMessageRequest(
            content="change the title personality to profile in omnix chat",
            provider_id="chatgpt_codex",
            research_mode="quick",
        ),
    )
    assert turn is not None
    routed_session, user_message = turn

    events = list(
        store.stream_provider_reply_chunks(
            routed_session,
            user_message,
            provider_id="chatgpt_codex",
            model_id=None,
        )
    )

    completed = events[-1]
    assert completed["type"] == "complete"
    assert completed["metadata"]["semantic_gate"]["reason"] == "semantic_parser_unavailable"
    assert completed["metadata"]["request_mode"]["mode"] == "quick_research"
    assert provider_calls == []


def test_agent_route_marker_fails_closed_at_provider_boundary(monkeypatch, tmp_path) -> None:
    provider_calls = []

    class _Provider:
        def chat_completion(self, **kwargs):
            provider_calls.append(kwargs)
            return []

    import app.shared as shared

    monkeypatch.setattr(shared, "get_provider", lambda _provider_id: _Provider())
    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(CreateChatSessionRequest(title="Boundary"))
    turn = store.begin_user_message(
        session.id,
        SendChatMessageRequest(content="make the workspace change"),
    )
    assert turn is not None
    routed_session, user_message = turn
    user_message.metadata.update(
        {
            "omnix_chat_routed": True,
            "omnix_route": {"lane": "agent", "reason": "test"},
        }
    )

    events = list(
        store.stream_provider_reply_chunks(
            routed_session,
            user_message,
            provider_id="test-provider",
            model_id="test-model",
        )
    )

    assert provider_calls == []
    assert events[-1]["metadata"]["agent_start"]["reason"] == "agent_handoff_invariant"

    reply = store._generate_provider_reply(
        routed_session,
        user_message,
        provider_id="test-provider",
        model_id="test-model",
        context_items=[],
    )
    assert provider_calls == []
    assert reply["metadata"]["agent_start"]["reason"] == "agent_handoff_invariant"


def test_direct_json_store_cannot_bypass_agent_provider_boundary(monkeypatch, tmp_path) -> None:
    provider_calls = []

    class _Provider:
        def chat_completion(self, **kwargs):
            provider_calls.append(kwargs)
            raise AssertionError("direct JSON store bypassed Agent routing")

    import app.shared as shared
    from app.chat.store import ChatSessionStore as LegacyJsonStore

    monkeypatch.setattr(shared, "get_provider", lambda _provider_id: _Provider())
    store = LegacyJsonStore(tmp_path / "legacy-chat.json")
    session = store.create_session(CreateChatSessionRequest(title="Legacy boundary"))
    turn = store.begin_user_message(
        session.id,
        SendChatMessageRequest(content="make the workspace change"),
    )
    assert turn is not None
    routed_session, user_message = turn
    user_message.metadata.update(
        {
            "omnix_chat_routed": True,
            "omnix_route": {"lane": "agent", "reason": "test"},
        }
    )

    events = list(
        store.stream_provider_reply_chunks(
            routed_session,
            user_message,
            provider_id="test-provider",
            model_id="test-model",
        )
    )

    assert provider_calls == []
    assert events[-1]["metadata"]["agent_start"]["reason"] == "agent_handoff_invariant"
