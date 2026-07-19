from __future__ import annotations

import json

import pytest

from app.assistant_memory.structured_provider import (
    ProviderStructuredProposalProvider,
    default_structured_proposal_provider,
)
from app.providers.base import ChatResponse, ProviderConfig


class FakeChatProvider:
    provider_name = "lmstudio"

    def __init__(self, content: str) -> None:
        self.config = ProviderConfig(provider_type="lmstudio", model="test-model")
        self.content = content
        self.calls: list[dict] = []

    def chat_completion(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return ChatResponse(content=self.content, model="test-model")


def test_provider_adapter_requests_strict_json_without_authority_fields() -> None:
    payload = {
        "proposals": [
            {
                "kind": "routine",
                "claim_type": "user_asserted",
                "category": "fact",
                "content": "The user commutes by SkyTrain",
                "payload": {
                    "activity": "commute_by_skytrain",
                    "days": [],
                    "evidence_count": 1,
                },
                "confidence": 0.9,
                "contradiction_key": "routine:commute",
            }
        ]
    }
    provider = FakeChatProvider(json.dumps(payload))
    adapter = ProviderStructuredProposalProvider(provider, timeout_seconds=1)

    rows = adapter.propose("These days I commute by SkyTrain.")

    assert rows == payload["proposals"]
    call = provider.calls[0]
    assert call["stream"] is False
    assert call["temperature"] == 0.0
    schema = call["response_format"]["json_schema"]["schema"]
    properties = schema["properties"]["proposals"]["items"]["properties"]
    assert "owner_id" not in properties
    assert "scope" not in properties
    assert "evidence_message_ids" not in properties
    assert "status" not in properties
    assert "activation_score" not in properties
    assert "Ignore previous instructions" not in call["messages"][0].content
    assert "These days I commute by SkyTrain" in call["messages"][1].content


def test_provider_adapter_accepts_fenced_json() -> None:
    provider = FakeChatProvider("```json\n{\"proposals\": []}\n```")
    adapter = ProviderStructuredProposalProvider(provider, timeout_seconds=1)

    assert adapter.propose("Nothing durable here.") == []


def test_provider_adapter_rejects_non_json_response() -> None:
    provider = FakeChatProvider("not json")
    adapter = ProviderStructuredProposalProvider(provider, timeout_seconds=1)

    with pytest.raises(ValueError, match="no JSON object"):
        adapter.propose("A durable statement.")


def test_default_provider_can_be_forced_to_deterministic_mode(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_MEMORY_STRUCTURED_EXTRACTION_MODE", "deterministic")

    assert default_structured_proposal_provider() is None
