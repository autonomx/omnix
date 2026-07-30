from __future__ import annotations

import json
from typing import Any

import pytest

from app.providers.base import (
    BaseProvider,
    ChatMessage,
    ChatResponse,
    ModelInfo,
    ProviderConfig,
)
from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.worlds.generation_recovering_provider import (
    RecoveringFirstPassWorldForgeTopicGenerator,
)
from app.rpg_world_forge_provider import WorldForgeProviderConfig
from app.rpg_world_forge_single_pass_provider import SinglePassWorldForgeProviderError


class _Provider(BaseProvider):
    provider_name = "lmstudio"

    def __init__(self, responses: list[str]) -> None:
        super().__init__(ProviderConfig(provider_type="lmstudio", model="local-model"))
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat_completion(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> ChatResponse:
        del stream
        self.calls.append({"messages": messages, "model": model, "kwargs": kwargs})
        return ChatResponse(content=self.responses.pop(0), model=model or "local-model")

    def get_models(self) -> list[ModelInfo]:
        return []

    def test_connection(self) -> bool:
        return True


def test_failed_registry_extraction_is_non_acceptable_failure_evidence() -> None:
    malformed = {
        "topic_id": "groups",
        "items": [
            {
                "entity_id": "ent:groups:001",
                "title": "Neon Wardens",
                "type": "security cooperative",
                "description": "Citizen-owned surveillance network.",
            },
            {
                "entity_id": "ent:groups:002",
                "title": "Ash Cartel",
                "type": "salvage syndicate",
                "description": "Controls dead-grid hardware.",
            },
        ],
        "provenance": {},
    }
    provider = _Provider([json.dumps(malformed), "still not valid json"])
    generator = RecoveringFirstPassWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="lmstudio",
            model="local-model",
            max_retries=0,
            lmstudio_schema_fallback=False,
        ),
    )
    node = CampaignTopicNode(
        topic_id="groups",
        title="Groups",
        category="lore",
        target_count=2,
        metadata={},
    )

    with pytest.raises(SinglePassWorldForgeProviderError) as captured:
        generator._generate_entity_registry(
            node,
            seed=10,
            campaign_context={},
            dependency_topics={},
        )

    assert len(provider.calls) == 2
    artifact = captured.value.diagnostics["failure_artifact"]
    assert artifact["stage"] == "recovery_exhausted"
    assert artifact["correction_attempted"] is True
    assert artifact["raw_response_hash"]
