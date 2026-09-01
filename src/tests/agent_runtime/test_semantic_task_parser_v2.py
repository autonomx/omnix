from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from app.agent_runtime.semantic_task_parser import (
    ProviderSemanticTaskParser,
    default_semantic_task_parser,
)
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


class _BuiltinFakeProvider(BaseProvider):
    provider_name = "chatgpt_codex"

    def __init__(self) -> None:
        super().__init__(
            ProviderConfig(
                provider_type="chatgpt_codex",
                model="gpt-test",
            )
        )

    def chat_completion(self, messages, model=None, stream=False, **kwargs):
        raise AssertionError("parser construction must not call the provider")

    def get_models(self):
        return []

    def test_connection(self):
        return True


def test_default_parser_accepts_normalized_builtin_provider_id(monkeypatch) -> None:
    import app.shared as shared

    provider = _BuiltinFakeProvider()
    requested: list[str] = []
    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_TASK_PARSER_MODE", "auto")
    monkeypatch.delenv("OMNIX_AGENT_SEMANTIC_TASK_PARSER_PROVIDER", raising=False)
    # Retired v1 settings must not disable or redirect the v2 parser.
    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_CLASSIFIER_MODE", "off")
    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_CLASSIFIER_PROVIDER", "invalid")
    monkeypatch.setattr(
        shared,
        "get_provider",
        lambda name: requested.append(name) or provider,
    )

    normalized = default_semantic_task_parser(
        provider_id="chatgpt_codex",
        model_id=None,
    )
    namespaced = default_semantic_task_parser(
        provider_id="llm:chatgpt_codex",
        model_id="llm:chatgpt_codex:gpt-test",
    )

    assert isinstance(normalized, ProviderSemanticTaskParser)
    assert isinstance(namespaced, ProviderSemanticTaskParser)
    assert normalized.timeout_seconds == provider.config.timeout
    assert namespaced.timeout_seconds == provider.config.timeout
    assert requested == ["chatgpt_codex", "chatgpt_codex"]


def test_default_parser_accepts_any_registered_base_provider(monkeypatch) -> None:
    import app.shared as shared

    class _OpenAICompatibleFakeProvider(_BuiltinFakeProvider):
        provider_name = "openai_compatible"

    provider = _OpenAICompatibleFakeProvider()
    requested: list[str] = []
    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_TASK_PARSER_MODE", "auto")
    monkeypatch.delenv("OMNIX_AGENT_SEMANTIC_TASK_PARSER_PROVIDER", raising=False)
    monkeypatch.setattr(
        shared,
        "get_provider",
        lambda name: requested.append(name) or provider,
    )

    parser = default_semantic_task_parser(
        provider_id="llm:openai_compatible",
        model_id="llm:openai_compatible:gpt-test",
    )

    assert isinstance(parser, ProviderSemanticTaskParser)
    assert parser.model == "gpt-test"
    assert requested == ["openai_compatible"]


def test_default_parser_rejects_non_provider_registry_values(monkeypatch) -> None:
    import app.shared as shared

    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_TASK_PARSER_MODE", "auto")
    monkeypatch.delenv("OMNIX_AGENT_SEMANTIC_TASK_PARSER_PROVIDER", raising=False)
    monkeypatch.setattr(
        shared,
        "get_provider",
        lambda _name: SimpleNamespace(provider_name="not-a-provider"),
    )

    assert default_semantic_task_parser(
        provider_id="custom",
        model_id=None,
    ) is None


def test_parser_preserves_structured_failure_diagnostics() -> None:
    class _FailingProvider:
        provider_name = "failing"
        config = SimpleNamespace(model="fake-model")

        def chat_completion(self, *_args, **_kwargs):
            raise RuntimeError("semantic transport failed")

    parser = ProviderSemanticTaskParser(
        _FailingProvider(),
        timeout_seconds=2,
    )

    with pytest.raises(Exception, match="structured operation"):
        parser.parse_contextual("change the workspace label")

    assert parser.last_diagnostics["error_type"] == "StructuredOutputExhausted"
    assert parser.last_diagnostics["underlying_error_type"] == "RuntimeError"
    assert parser.last_diagnostics["underlying_error"] == "semantic transport failed"
    assert parser.last_diagnostics["provider"] == "failing"


def test_provider_semantic_task_parser_uses_v2_contract_without_authority_fields(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_TASK_CACHE", "0")
    provider = _StructuredFakeProvider(
        {
            "intent": "repair Aurora appearance",
            "subjects": [
                {
                    "target": "workspace",
                    "reference": "Aurora light mode",
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
            "confidence": 0.93,
            "reason_code": "workspace_ui_mutation",
        }
    )
    parser = ProviderSemanticTaskParser(
        provider,
        model="fake-model",
        timeout_seconds=2,
    )

    task = parser.parse_contextual(
        "fix it",
        reference_context="User: Aurora light mode has poor contrast.",
    )

    assert task.intent == "repair Aurora appearance"
    assert task.operations[1].target == "workspace"
    assert task.ambiguity == "none"
    assert len(provider.calls) == 1

    system = provider.calls[0]["messages"][0].content
    user_payload = json.loads(provider.calls[0]["messages"][1].content)
    assert "never select a lane" in system
    assert "profile" in system
    assert user_payload["contract_version"] == "agent_runtime_semantic_task_v2"
    assert user_payload["latest_user_message"] == "fix it"
    assert "Aurora light mode" in user_payload["reference_context"]
    assert user_payload["current_environment"] is None
    assert (
        user_payload["authority_contract"]["current_environment"]
        == "current_state_only_not_action_authority"
    )
    assert parser.last_diagnostics["cache_hit"] is False
    assert parser.last_diagnostics["max_output_tokens"] == 420


def test_parser_bounds_structured_provider_call_to_request_deadline(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_TASK_CACHE", "0")
    provider = _StructuredFakeProvider(
        {
            "intent": "rename chat title",
            "subjects": [{"target": "workspace", "reference": "chat UI"}],
            "operations": [{"kind": "modify", "target": "workspace"}],
            "data_dependencies": [],
            "autonomous": True,
            "multi_step": False,
            "ambiguity": "none",
            "candidate_interpretations": [],
            "confidence": 0.99,
            "reason_code": "workspace_ui_mutation",
        }
    )
    parser = ProviderSemanticTaskParser(provider, model="fake-model", timeout_seconds=90)
    deadline_at = time.monotonic() + 4

    parser.parse_contextual("change the title", deadline_at=deadline_at)

    request_timeout = provider.calls[0]["kwargs"]["request_timeout_seconds"]
    assert 0 < request_timeout <= 4


def test_parser_rejects_expired_request_deadline_before_provider_call(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_TASK_CACHE", "0")
    provider = _StructuredFakeProvider({})
    parser = ProviderSemanticTaskParser(provider, model="fake-model", timeout_seconds=90)

    with pytest.raises(Exception, match="deadline has expired"):
        parser.parse_contextual("change the title", deadline_at=time.monotonic() - 1)

    assert provider.calls == []
    assert parser.last_diagnostics["error_type"] == "ProviderTimeout"


def test_semantic_task_parser_uses_context_sensitive_cache_key(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_TASK_CACHE", "1")
    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_TASK_CACHE_TTL_SECONDS", "300")
    provider = _StructuredFakeProvider(
        {
            "intent": "fix referenced issue",
            "subjects": [{"target": "workspace", "reference": "referenced issue"}],
            "operations": [{"kind": "modify", "target": "workspace"}],
            "data_dependencies": [],
            "autonomous": True,
            "multi_step": False,
            "ambiguity": "resolvable_from_context",
            "candidate_interpretations": [],
            "confidence": 0.9,
            "reason_code": "contextual_workspace_fix",
        }
    )
    parser = ProviderSemanticTaskParser(provider, model="fake-model")

    first = parser.parse_contextual(
        "fix it",
        reference_context="User: the Aurora stylesheet is broken",
    )
    again = parser.parse_contextual(
        "fix it",
        reference_context="User: the Aurora stylesheet is broken",
    )
    other = parser.parse_contextual(
        "fix it",
        reference_context="User: the bedroom bulb is broken",
    )

    assert first == again
    assert other.intent == first.intent
    assert len(provider.calls) == 2
    assert parser.last_diagnostics["cache_hit"] is False


def test_semantic_task_parser_receives_active_objective_and_current_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_TASK_CACHE", "0")
    provider = _StructuredFakeProvider(
        {
            "intent": "resume blocked label edit",
            "subjects": [
                {
                    "target": "workspace",
                    "reference": "Personality to Profile label edit",
                    "kind": "software_ui",
                }
            ],
            "operations": [
                {"kind": "modify", "target": "workspace"},
                {"kind": "validate", "target": "workspace"},
            ],
            "data_dependencies": [],
            "autonomous": True,
            "multi_step": True,
            "objective_relation": "resume",
            "ambiguity": "resolvable_from_context",
            "candidate_interpretations": [],
            "confidence": 0.98,
            "reason_code": "resume_blocked_workspace_edit",
        }
    )
    parser = ProviderSemanticTaskParser(provider, model="fake-model")

    task = parser.parse_contextual(
        "i didnt include the project folder before. try again in code",
        reference_context="Assistant: the prior attempt could not access the workspace.",
        previous_objective=(
            '{"canonical_request":"change Personality to Profile",'
            '"profile":"coding","status":"blocked"}'
        ),
        current_environment={
            "active_workspace": "omnix",
            "workspace_source": "turn_attachment",
            "workspace_attached_this_turn": True,
        },
    )

    assert task.objective_relation == "resume"
    payload = json.loads(provider.calls[0]["messages"][1].content)
    assert "change Personality to Profile" in payload["previous_objective"]
    assert payload["current_environment"]["active_workspace"] == "omnix"
    assert payload["current_environment"]["workspace_attached_this_turn"] is True


def test_semantic_task_cache_is_sensitive_to_current_environment(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_TASK_CACHE", "1")
    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_TASK_CACHE_TTL_SECONDS", "300")
    provider = _StructuredFakeProvider(
        {
            "intent": "resume referenced workspace edit",
            "subjects": [{"target": "workspace", "reference": "referenced edit"}],
            "operations": [{"kind": "modify", "target": "workspace"}],
            "data_dependencies": [],
            "autonomous": True,
            "multi_step": False,
            "objective_relation": "resume",
            "ambiguity": "resolvable_from_context",
            "candidate_interpretations": [],
            "confidence": 0.95,
            "reason_code": "contextual_workspace_resume",
        }
    )
    parser = ProviderSemanticTaskParser(provider, model="fake-model")
    objective = '{"canonical_request":"fix the label","profile":"coding"}'

    parser.parse_contextual(
        "try again",
        previous_objective=objective,
        current_environment={"active_workspace": "omnix"},
    )
    parser.parse_contextual(
        "try again",
        previous_objective=objective,
        current_environment={"active_workspace": "other-project"},
    )

    assert len(provider.calls) == 2
