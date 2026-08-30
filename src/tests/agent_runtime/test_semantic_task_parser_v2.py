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
