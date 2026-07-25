from __future__ import annotations

import json
from typing import Any

from app.providers.base import (
    BaseProvider,
    ChatMessage,
    ChatResponse,
    ModelInfo,
    ProviderConfig,
)
from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_review import result_status
from app.rpg.worlds.generation_recovering_provider import (
    RecoveringFirstPassWorldForgeTopicGenerator,
)
from app.rpg_world_forge_provider import WorldForgeProviderConfig


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
        return ChatResponse(
            content=self.responses.pop(0),
            model=model or "local-model",
        )

    def get_models(self) -> list[ModelInfo]:
        return []

    def test_connection(self) -> bool:
        return True


def _generator(provider: _Provider) -> RecoveringFirstPassWorldForgeTopicGenerator:
    return RecoveringFirstPassWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="lmstudio",
            model="local-model",
            max_retries=0,
            lmstudio_schema_fallback=False,
        ),
    )


def _history_node() -> CampaignTopicNode:
    return CampaignTopicNode(
        topic_id="history_timeline",
        title="History Timeline",
        category="lore",
        dependencies=("setting_rules",),
        generator_role="world_forge",
        required_before_launch=True,
        visibility="game_master_canon",
        target_count=1,
        metadata={
            "entity_kind": "historical_event",
            "field_definitions": [
                {
                    "field_id": "name",
                    "value_type": "string",
                    "required": True,
                    "description": "Event name.",
                },
                {
                    "field_id": "year",
                    "value_type": "integer",
                    "required": True,
                    "description": "Event year.",
                },
                {
                    "field_id": "event",
                    "value_type": "string",
                    "required": True,
                    "description": "What happened.",
                },
            ],
        },
    )


def _entity() -> dict[str, Any]:
    return {
        "id": "ent:history_timeline:001",
        "kind": "historical_event",
        "name": "The Blackout Accords",
        "year": 2088,
        "event": "City grids were divided among corporate utilities.",
    }


def _topic_payload(topic_id: str = "history_timeline") -> str:
    return json.dumps(
        {
            "topic_id": topic_id,
            "documents": [],
            "entities": [_entity()],
            "facts": [],
            "relationships": [],
            "knowledge_rules": [],
            "story_threads": [],
            "provenance": {},
        }
    )


def _malformed_alias_payload() -> str:
    return json.dumps(
        {
            "topic_id": "history_timeline",
            "documents": [],
            "items": [
                {
                    "entity_id": "ent:history_timeline:001",
                    "type": "historical_event",
                    "title": "The Blackout Accords",
                    "year": 2088,
                    "description": "City grids were divided among corporate utilities.",
                }
            ],
            "facts": [],
            "relationships": [],
            "knowledge_rules": [],
            "story_threads": [],
            "provenance": {},
        }
    )


def test_entity_id_in_root_is_fixed_without_another_model_call() -> None:
    provider = _Provider([_topic_payload("ent:history_timeline:001")])

    topic = _generator(provider).generate(
        _history_node(),
        seed=8,
        campaign_context={},
        dependency_topics={},
    )

    assert len(provider.calls) == 1
    assert topic.topic_id == "history_timeline"
    assert topic.entities[0]["id"] == "ent:history_timeline:001"
    assert result_status(topic) == "needs_review"
    record = topic.provenance["structured_recovery"]["records"][0]
    assert record["method"] == "deterministic_normalisation"
    assert "root_topic_id_from_entity_id" in record["repair_codes"]


def test_same_configured_model_extracts_malformed_fields_into_schema() -> None:
    provider = _Provider([_malformed_alias_payload(), _topic_payload()])

    topic = _generator(provider).generate(
        _history_node(),
        seed=8,
        campaign_context={},
        dependency_topics={},
    )

    assert len(provider.calls) == 2
    assert {call["model"] for call in provider.calls} == {"local-model"}
    assert "loss-minimising JSON recovery transformer" in (
        provider.calls[1]["messages"][0].content
    )
    recovery_request = provider.calls[1]["messages"][1].content
    assert "The Blackout Accords" in recovery_request
    assert "Do not invent, enrich, summarise, or regenerate lore" in recovery_request
    assert topic.entities[0]["name"] == "The Blackout Accords"
    assert result_status(topic) == "needs_review"
    record = topic.provenance["structured_recovery"]["records"][0]
    assert record["method"] == "same_model_extraction"
    assert topic.provenance["attempt_count"] == 2


def test_failed_extraction_retains_candidate_for_review_instead_of_raising() -> None:
    provider = _Provider([_malformed_alias_payload(), "not valid json"])

    topic = _generator(provider).generate(
        _history_node(),
        seed=8,
        campaign_context={},
        dependency_topics={},
    )

    assert len(provider.calls) == 2
    assert result_status(topic) == "needs_review"
    record = topic.provenance["structured_recovery"]["records"][0]
    assert record["method"] == "retained_invalid_candidate"
    retained = topic.provenance["structured_recovery_retained_candidate"]
    assert retained["decoded_candidate"]["items"][0]["title"] == (
        "The Blackout Accords"
    )


def test_registry_uses_same_model_extraction_without_alternate_setup() -> None:
    node = CampaignTopicNode(
        topic_id="groups",
        title="Groups",
        category="lore",
        target_count=2,
        metadata={},
    )
    valid_registry = {
        "topic_id": "groups",
        "entities": [
            {
                "id": "ent:groups:001",
                "name": "Neon Wardens",
                "role": "security cooperative",
                "distinction": "citizen-owned surveillance",
            },
            {
                "id": "ent:groups:002",
                "name": "Ash Cartel",
                "role": "salvage syndicate",
                "distinction": "controls dead-grid hardware",
            },
        ],
        "provenance": {},
    }
    malformed_registry = {
        "topic_id": "groups",
        "items": valid_registry["entities"],
        "provenance": {},
    }
    provider = _Provider(
        [json.dumps(malformed_registry), json.dumps(valid_registry)]
    )

    registry, diagnostics, _, _ = _generator(provider)._generate_entity_registry(
        node,
        seed=10,
        campaign_context={},
        dependency_topics={},
    )

    assert len(provider.calls) == 2
    assert {call["model"] for call in provider.calls} == {"local-model"}
    assert registry.topic_id == "groups"
    assert diagnostics["structured_recovery"]["method"] == "same_model_extraction"
