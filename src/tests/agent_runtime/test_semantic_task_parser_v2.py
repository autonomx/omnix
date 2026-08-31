from __future__ import annotations

import json
from types import SimpleNamespace

from app.agent_runtime.semantic_task_parser import ProviderSemanticTaskParser
from app.providers.base import ChatResponse


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
    assert "you never select a lane" in system
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
