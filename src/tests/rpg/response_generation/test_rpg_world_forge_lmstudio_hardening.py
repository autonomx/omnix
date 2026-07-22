from __future__ import annotations

import json

import pytest

from app.providers.base import BaseProvider, ChatMessage, ChatResponse, ModelInfo, ProviderConfig
from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg_world_forge_provider import ProviderWorldForgeTopicGenerator, WorldForgeProviderConfig


class _Provider(BaseProvider):
    provider_name = "lmstudio"

    def __init__(self, responses: list[str | Exception]) -> None:
        self.config = ProviderConfig(provider_type="lmstudio", model="local-model")
        self.responses = list(responses)
        self.calls: list[dict] = []

    def chat_completion(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        stream: bool = False,
        **kwargs,
    ) -> ChatResponse:
        self.calls.append({"messages": messages, "model": model, "kwargs": kwargs})
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return ChatResponse(content=value, model=model or "local-model")

    def get_models(self) -> list[ModelInfo]:
        return []

    def test_connection(self) -> bool:
        return True


def _node() -> CampaignTopicNode:
    return CampaignTopicNode(
        topic_id="realm",
        title="Realm",
        category="lore",
        dependencies=(),
        generator_role="world_forge",
        required_before_launch=True,
        visibility="public",
        target_count=1,
    )


def _payload(*, entities: object | None = None) -> str:
    return json.dumps(
        {
            "topic_id": "realm",
            "documents": [],
            "entities": [] if entities is None else entities,
            "facts": [],
            "relationships": [],
            "knowledge_rules": [],
            "story_threads": [],
            "provenance": {},
        }
    )


def test_lmstudio_call_has_bounded_completion_tokens() -> None:
    provider = _Provider([_payload()])
    generator = ProviderWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="lmstudio",
            model="local-model",
            max_tokens=6144,
            max_retries=0,
        ),
    )

    generator.generate(_node(), seed=1, campaign_context={}, dependency_topics={})

    assert provider.calls[0]["kwargs"]["max_tokens"] == 6144
    assert provider.calls[0]["kwargs"]["response_format"]["type"] == "json_schema"


def test_lmstudio_retries_format_failure_with_text_fallback() -> None:
    provider = _Provider([RuntimeError("response_format is unsupported"), _payload()])
    generator = ProviderWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="lmstudio",
            model="local-model",
            max_retries=1,
            retry_backoff_seconds=0,
            lmstudio_schema_fallback=True,
        ),
    )

    topic = generator.generate(_node(), seed=1, campaign_context={}, dependency_topics={})

    assert topic.topic_id == "realm"
    assert provider.calls[0]["kwargs"]["response_format"]["type"] == "json_schema"
    assert provider.calls[1]["kwargs"]["response_format"] == {"type": "text"}
    assert topic.provenance["response_format"] == "text_json"


def test_other_provider_retries_format_failure_with_text_fallback() -> None:
    provider = _Provider([RuntimeError("response_format is unsupported"), _payload()])
    provider.provider_name = "openrouter"
    generator = ProviderWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="openrouter",
            model="remote-model",
            max_retries=1,
            retry_backoff_seconds=0,
        ),
    )

    topic = generator.generate(_node(), seed=1, campaign_context={}, dependency_topics={})

    assert provider.calls[0]["kwargs"]["response_format"] == {"type": "json_object"}
    assert provider.calls[1]["kwargs"]["response_format"] == {"type": "text"}
    assert topic.provenance["response_format"] == "text_json"


def test_world_forge_rejects_non_object_collection_rows() -> None:
    provider = _Provider([_payload(entities=["not-an-object"])])
    generator = ProviderWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="lmstudio",
            model="local-model",
            max_retries=0,
        ),
    )

    with pytest.raises(RuntimeError, match="schema validation"):
        generator.generate(_node(), seed=1, campaign_context={}, dependency_topics={})
