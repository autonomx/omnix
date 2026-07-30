from __future__ import annotations

import json
from dataclasses import replace
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
from app.rpg.session.genesis.world_forge_dossiers import dossier_prompt_contract
from app.rpg.worlds.generation_first_pass_provider import (
    FirstPassWorldForgeTopicGenerator,
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
        return ChatResponse(
            content=self.responses.pop(0),
            model=model or "local-model",
        )

    def get_models(self) -> list[ModelInfo]:
        return []

    def test_connection(self) -> bool:
        return True


def _generator(provider: _Provider) -> FirstPassWorldForgeTopicGenerator:
    return FirstPassWorldForgeTopicGenerator(
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


def _topic_payload(topic_id: str, entity: dict[str, Any]) -> str:
    canonical_topic_id = (
        topic_id
        if not topic_id.startswith("ent:")
        else topic_id.split(":", 2)[1]
    )
    sections = dossier_prompt_contract(canonical_topic_id)["entity_fields"][
        "dossier"
    ]["sections"]
    entity = {
        **entity,
        "kind": entity.get("kind") or canonical_topic_id,
        "short_summary": entity.get("short_summary")
        or "A provider-authored historical summary.",
        "dossier": entity.get("dossier")
        or {
            "sections": {
                section["id"]: {
                    "paragraphs": ["Provider-authored long-form historical lore."]
                }
                for section in sections
            },
        },
        **({"attributes": {}} if canonical_topic_id == "threats" else {}),
    }
    return json.dumps(
        {
            "topic_id": topic_id,
            "documents": [],
            "entities": [entity],
            "relationships": [],
            "knowledge_rules": [],
            "story_threads": [],
        }
    )


def _schema(call: dict[str, Any]) -> dict[str, Any]:
    return call["kwargs"]["response_format"]["json_schema"]["schema"]


def _resolve(schema: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    reference = value.get("$ref")
    if not isinstance(reference, str):
        return value
    current: Any = schema
    for part in reference.removeprefix("#/").split("/"):
        current = current[part]
    return current


def test_history_timeline_root_identity_is_schema_pinned_on_first_call() -> None:
    provider = _Provider(
        [
            _topic_payload(
                "history_timeline",
                {
                    "id": "ent:history_timeline:001",
                    "kind": "historical_event",
                    "name": "The Blackout Accords",
                    "year": 2088,
                    "event": "City grids were divided among corporate utilities.",
                },
            )
        ]
    )

    topic = _generator(provider).generate(
        _history_node(),
        seed=8,
        campaign_context={},
        dependency_topics={},
    )

    assert topic.topic_id == "history_timeline"
    assert len(provider.calls) == 1
    schema = _schema(provider.calls[0])
    assert schema["properties"]["topic_id"]["const"] == "history_timeline"
    entity_schema = _resolve(
        schema,
        schema["properties"]["entities"]["items"],
    )
    assert entity_schema["properties"]["id"]["const"] == (
        "ent:history_timeline:001"
    )
    system_prompt = provider.calls[0]["messages"][0].content
    assert "Never place an entity ID in root topic_id" in system_prompt
    request = json.loads(provider.calls[0]["messages"][1].content)
    identity = request["required_output"]["identity_contract"]
    assert identity["root_topic_id"] == "history_timeline"
    assert identity["allocated_entity_ids"] == ["ent:history_timeline:001"]


def test_dossier_regeneration_pins_requested_entity_and_quality_target() -> None:
    node = replace(
        _history_node(),
        metadata={
            **dict(_history_node().metadata),
            "entity_dossier_regeneration": {
                "entity_id": "ent:history_timeline:007",
                "entity_name": "The Seventh Accord",
                "editorial_only": True,
            },
        },
    )
    provider = _Provider(
        [
            _topic_payload(
                "history_timeline",
                {
                    "id": "ent:history_timeline:007",
                    "kind": "historical_event",
                    "name": "The Seventh Accord",
                    "year": 2097,
                    "event": "The seventh utility compact divided the remaining grid.",
                },
            )
        ]
    )

    topic = _generator(provider).generate(
        node,
        seed=8,
        campaign_context={
            "entity_dossier_regeneration": {
                "entity_id": "ent:history_timeline:007",
                "current_canonical_entity": {
                    "id": "ent:history_timeline:007",
                    "name": "The Seventh Accord",
                },
            }
        },
        dependency_topics={},
    )

    assert topic.entities[0]["id"] == "ent:history_timeline:007"
    schema = _schema(provider.calls[0])
    entity_schema = _resolve(schema, schema["properties"]["entities"]["items"])
    assert entity_schema["properties"]["id"]["const"] == "ent:history_timeline:007"
    prompt = provider.calls[0]["messages"][0].content
    assert "dossier-only regeneration" in prompt
    assert "at least 438 words" in prompt
    assert "validator requires 350" in prompt
    assert "every paragraph at least 24 words" in prompt


def test_logged_entity_id_in_root_topic_id_is_rejected_by_schema() -> None:
    provider = _Provider(
        [
            _topic_payload(
                "ent:history_timeline:001",
                {
                    "id": "ent:history_timeline:001",
                    "kind": "historical_event",
                    "name": "The Blackout Accords",
                    "year": 2088,
                    "event": "City grids were divided among corporate utilities.",
                },
            )
        ]
    )

    with pytest.raises(SinglePassWorldForgeProviderError) as raised:
        _generator(provider).generate(
            _history_node(),
            seed=8,
            campaign_context={},
            dependency_topics={},
        )

    assert len(provider.calls) == 1
    assert "topic_id_mismatch" not in str(raised.value)
    assert _schema(provider.calls[0])["properties"]["topic_id"]["const"] == (
        "history_timeline"
    )


def test_non_profile_topic_root_identity_is_also_schema_pinned() -> None:
    node = CampaignTopicNode(
        topic_id="threats",
        title="Threats",
        category="lore",
        target_count=1,
        metadata={},
    )
    provider = _Provider(
        [
            _topic_payload(
                "threats",
                {
                    "id": "ent:threats:001",
                    "name": "Ghost Market",
                },
            )
        ]
    )

    _generator(provider).generate(
        node,
        seed=9,
        campaign_context={},
        dependency_topics={},
    )

    assert _schema(provider.calls[0])["properties"]["topic_id"]["const"] == "threats"


def test_registry_root_and_allocated_ids_are_schema_pinned() -> None:
    node = CampaignTopicNode(
        topic_id="groups",
        title="Groups",
        category="lore",
        target_count=2,
        metadata={},
    )
    provider = _Provider(
        [
            json.dumps(
                {
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
                }
            )
        ]
    )

    registry, _, _, _ = _generator(provider)._generate_entity_registry(
        node,
        seed=10,
        campaign_context={},
        dependency_topics={},
    )

    assert registry.topic_id == "groups"
    schema = _schema(provider.calls[0])
    assert schema["properties"]["topic_id"]["const"] == "groups"
    item_schema = _resolve(
        schema,
        schema["properties"]["entities"]["items"],
    )
    assert set(item_schema["properties"]["id"]["enum"]) == {
        "ent:groups:001",
        "ent:groups:002",
    }
