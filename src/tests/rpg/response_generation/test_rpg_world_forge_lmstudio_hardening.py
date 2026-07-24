from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.providers.base import BaseProvider, ChatMessage, ChatResponse, ModelInfo, ProviderConfig
from app.providers.structured import UnsupportedStructuredMode
from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg_world_forge_provider import (
    ProviderWorldForgeTopicGenerator,
    WorldForgeProviderConfig,
    _payload as build_world_forge_payload,
)


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
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "provider_name": self.provider_name,
                "kwargs": kwargs,
            }
        )
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return ChatResponse(content=value, model=model or "local-model")

    def get_models(self) -> list[ModelInfo]:
        return []

    def test_connection(self) -> bool:
        return True


class _RoutingProvider(_Provider):
    def __init__(self) -> None:
        super().__init__([])
        self._lock = threading.Lock()

    def chat_completion(self, messages, model=None, stream=False, **kwargs):
        request = json.loads(messages[-1].content)
        topic_id = request["topic"]["topic_id"]
        with self._lock:
            self.calls.append(
                {
                    "messages": messages,
                    "model": model,
                    "provider_name": self.provider_name,
                    "kwargs": kwargs,
                }
            )
        return ChatResponse(content=_payload(topic_id=topic_id), model=model or "model")


class _ParallelBatchProvider(_Provider):
    def __init__(self) -> None:
        super().__init__([])
        self.active = 0
        self.peak = 0
        self._lock = threading.Lock()
        self._paired_call = threading.Event()

    def chat_completion(self, messages, model=None, stream=False, **kwargs):
        del stream
        request = json.loads(messages[-1].content)
        if "generation_batch" not in request:
            allocated_ids = list(request["allocated_entity_ids"])
            with self._lock:
                self.calls.append(
                    {
                        "messages": messages,
                        "model": model,
                        "provider_name": self.provider_name,
                        "kwargs": kwargs,
                    }
                )
            return ChatResponse(
                content=_registry_payload(
                    topic_id="regions",
                    entities=[
                        {
                            "id": entity_id,
                            "name": f"Region {index + 1}",
                            "role": "regional identity",
                            "distinction": f"distinctive territory {index + 1}",
                        }
                        for index, entity_id in enumerate(allocated_ids)
                    ],
                ),
                model=model or "local-model",
            )
        batch_index = int(request["generation_batch"]["index"])
        slot = request["generation_batch"]["assigned_entities"][0]
        with self._lock:
            self.calls.append(
                {
                    "messages": messages,
                    "model": model,
                    "provider_name": self.provider_name,
                    "kwargs": kwargs,
                }
            )
            self.active += 1
            self.peak = max(self.peak, self.active)
            if self.active == 2:
                self._paired_call.set()
        assert self._paired_call.wait(timeout=2)
        try:
            return ChatResponse(
                content=_payload(
                    topic_id="regions",
                    entities=[
                        {
                            "entity_id": slot["id"],
                            "name": slot["name"],
                        }
                    ],
                ),
                model=model or "local-model",
            )
        finally:
            with self._lock:
                self.active -= 1


def _node(topic_id: str = "realm") -> CampaignTopicNode:
    return CampaignTopicNode(
        topic_id=topic_id,
        title=topic_id.title(),
        category="lore",
        dependencies=(),
        generator_role="world_forge",
        required_before_launch=True,
        visibility="public",
        target_count=1,
    )


def _payload(*, topic_id: str = "realm", entities: object | None = None) -> str:
    return json.dumps(
        {
            "topic_id": topic_id,
            "documents": [],
            "entities": [] if entities is None else entities,
            "facts": [],
            "relationships": [],
            "knowledge_rules": [],
            "story_threads": [],
            "provenance": {},
        }
    )


def _registry_payload(*, topic_id: str, entities: object) -> str:
    return json.dumps(
        {
            "topic_id": topic_id,
            "entities": entities,
            "provenance": {},
        }
    )


def test_dependency_payload_excludes_full_dossiers_but_keeps_references() -> None:
    long_dossier = "dossier prose " * 3_000
    payload = build_world_forge_payload(
        _node("cultures"),
        seed=1,
        campaign_context={},
        dependency_topics={
            "regions": GeneratedTopic(
                topic_id="regions",
                entities=(
                    {
                        "id": "ent:region:001",
                        "name": "Ashlands",
                        "kind": "region",
                        "short_summary": "A vitrified desert.",
                        "dossier": {"sections": [{"paragraphs": [long_dossier]}]},
                    },
                ),
                documents=({"title": "Atlas", "body": long_dossier},),
            )
        },
    )

    dependency = payload["dependencies"]["regions"]
    assert dependency["entities"] == [
        {
            "id": "ent:region:001",
            "name": "Ashlands",
            "kind": "region",
            "summary": "A vitrified desert.",
        }
    ]
    assert long_dossier not in json.dumps(dependency)


def test_lmstudio_call_has_bounded_completion_tokens() -> None:
    provider = _Provider([_payload()])
    generator = ProviderWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="lmstudio",
            model="bounded-local-model",
            max_tokens=6144,
            max_retries=0,
        ),
    )

    generator.generate(_node(), seed=1, campaign_context={}, dependency_topics={})

    assert provider.calls[0]["kwargs"]["max_tokens"] == 6144
    assert provider.calls[0]["kwargs"]["response_format"]["type"] == "json_schema"
    assert provider.calls[0]["kwargs"]["request_timeout_seconds"] <= 180


def test_entity_topics_are_generated_in_separate_bounded_batches() -> None:
    provider = _Provider(
        [
            _registry_payload(
                topic_id="regions",
                entities=[
                    {"id": "ent:region:001", "name": "Ashlands", "role": "wasteland", "distinction": "glass dunes"},
                    {"id": "ent:region:002", "name": "Glass Coast", "role": "coast", "distinction": "crystalline shore"},
                    {"id": "ent:region:003", "name": "Storm Range", "role": "mountains", "distinction": "perpetual thunder"},
                ],
            ),
            _payload(topic_id="regions", entities=[{"entity_id": "ent:region:001"}]),
            _payload(topic_id="regions", entities=[{"entity_id": "ent:region:002", "name": "Glass Coast"}]),
            _payload(topic_id="regions", entities=[{"entity_id": "ent:region:003", "name": "Storm Range"}]),
        ]
    )
    generator = ProviderWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="lmstudio",
            model="batched-local-model",
            max_retries=0,
            entity_batch_workers=1,
        ),
    )
    node = CampaignTopicNode(
        topic_id="regions",
        title="Regions",
        category="regions",
        dependencies=(),
        generator_role="world_forge",
        required_before_launch=True,
        visibility="public",
        target_count=3,
    )
    checkpoints: list[dict] = []
    generator.set_progress_callback(checkpoints.append)

    topic = generator.generate(node, seed=8, campaign_context={}, dependency_topics={})

    assert [entity["entity_id"] for entity in topic.entities] == [
        "ent:region:001",
        "ent:region:002",
        "ent:region:003",
    ]
    assert topic.entities[0]["name"] == "Ashlands"
    assert topic.entities[0]["registry_distinction"] == "glass dunes"
    assert len(provider.calls) == 4
    registry_request, *requests = [
        json.loads(call["messages"][-1].content) for call in provider.calls
    ]
    assert registry_request["allocated_entity_ids"] == [
        "ent:region:001",
        "ent:region:002",
        "ent:region:003",
    ]
    assert [request["topic"]["target_count"] for request in requests] == [1, 1, 1]
    assert [request["generation_batch"]["index"] for request in requests] == [0, 1, 2]
    assert [request["generation_batch"]["assigned_entity_ids"] for request in requests] == [
        ["ent:region:001"],
        ["ent:region:002"],
        ["ent:region:003"],
    ]
    assert requests[1]["generation_batch"]["previous_entities"] == [
        {"id": "ent:region:001", "name": "Ashlands"}
    ]
    assert topic.provenance["entity_batches"] == {
        "strategy": "sequential_entity_batches",
        "batch_count": 3,
        "batch_size": 1,
        "target_count": 3,
    }
    assert [row["name"] for row in topic.provenance["entity_registry"]["entities"]] == [
        "Ashlands",
        "Glass Coast",
        "Storm Range",
    ]
    assert [(item["batch_current"], item["batch_total"]) for item in checkpoints] == [
        (1, 3),
        (2, 3),
        (3, 3),
    ]
    assert checkpoints[-1]["token_usage"]["total_tokens"] > 0
    assert checkpoints[-1]["token_usage"]["source"] == "estimated"


def test_entity_batches_use_two_concurrent_lmstudio_calls_and_share_prior_waves() -> None:
    provider = _ParallelBatchProvider()
    generator = ProviderWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="lmstudio",
            model="parallel-local-model",
            max_retries=0,
            entity_batch_workers=2,
        ),
    )
    node = CampaignTopicNode(
        topic_id="regions",
        title="Regions",
        category="regions",
        dependencies=(),
        generator_role="world_forge",
        required_before_launch=True,
        visibility="public",
        target_count=4,
    )

    topic = generator.generate(node, seed=8, campaign_context={}, dependency_topics={})

    assert provider.peak == 2
    assert [entity["entity_id"] for entity in topic.entities] == [
        "ent:region:001",
        "ent:region:002",
        "ent:region:003",
        "ent:region:004",
    ]
    batch_requests = [
        json.loads(call["messages"][-1].content)
        for call in provider.calls
    ]
    requests = {
        request["generation_batch"]["index"]: request
        for request in batch_requests
        if "generation_batch" in request
    }
    assert requests[0]["generation_batch"]["previous_entities"] == []
    assert requests[1]["generation_batch"]["previous_entities"] == []
    assert requests[0]["generation_batch"]["assigned_entity_ids"] == ["ent:region:001"]
    assert requests[1]["generation_batch"]["assigned_entity_ids"] == ["ent:region:002"]
    assert requests[2]["generation_batch"]["previous_entities"] == [
        {"id": "ent:region:001", "name": "Region 1"},
        {"id": "ent:region:002", "name": "Region 2"},
    ]
    assert requests[3]["generation_batch"]["previous_entities"] == [
        {"id": "ent:region:001", "name": "Region 1"},
        {"id": "ent:region:002", "name": "Region 2"},
    ]
    assert requests[2]["generation_batch"]["assigned_entity_ids"] == ["ent:region:003"]
    assert requests[3]["generation_batch"]["assigned_entity_ids"] == ["ent:region:004"]


def test_entity_batch_rejects_an_id_allocated_to_another_parallel_batch() -> None:
    provider = _Provider(
        [
            _registry_payload(
                topic_id="regions",
                entities=[
                    {"id": "ent:region:001", "name": "Ashlands", "role": "wasteland", "distinction": "glass dunes"},
                    {"id": "ent:region:002", "name": "Glass Coast", "role": "coast", "distinction": "crystalline shore"},
                ],
            ),
            _payload(
                topic_id="regions",
                entities=[{"entity_id": "ent:region:001", "name": "Ashlands"}],
            ),
            _payload(
                topic_id="regions",
                entities=[{"entity_id": "ent:region:001", "name": "Ashlands Again"}],
            ),
            _payload(
                topic_id="regions",
                entities=[{"entity_id": "ent:region:001", "name": "Ashlands Again"}],
            ),
        ]
    )
    generator = ProviderWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="lmstudio",
            model="allocated-id-local-model",
            max_retries=0,
            entity_batch_workers=1,
        ),
    )
    node = CampaignTopicNode(
        topic_id="regions",
        title="Regions",
        category="regions",
        dependencies=(),
        generator_role="world_forge",
        required_before_launch=True,
        visibility="public",
        target_count=2,
    )

    with pytest.raises(RuntimeError, match="structured World Forge provider failed"):
        generator.generate(node, seed=8, campaign_context={}, dependency_topics={})


def test_lmstudio_retries_typed_format_failure_with_text_fallback() -> None:
    provider = _Provider(
        [UnsupportedStructuredMode("schema mode unavailable"), _payload()]
    )
    generator = ProviderWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="lmstudio",
            model="fallback-local-model",
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


def test_other_provider_retries_typed_format_failure_with_text_fallback() -> None:
    provider = _Provider(
        [UnsupportedStructuredMode("object mode unavailable"), _payload()]
    )
    provider.provider_name = "transport-provider"
    generator = ProviderWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="openrouter",
            model="fallback-remote-model",
            max_retries=1,
            retry_backoff_seconds=0,
        ),
    )

    topic = generator.generate(_node(), seed=1, campaign_context={}, dependency_topics={})

    assert provider.provider_name == "transport-provider"
    assert provider.calls[0]["provider_name"] == "transport-provider"
    assert provider.calls[0]["kwargs"]["response_format"] == {"type": "json_object"}
    assert provider.calls[1]["kwargs"]["response_format"] == {"type": "text"}
    assert topic.provenance["response_format"] == "text_json"


def test_world_forge_route_identity_is_immutable_across_concurrent_calls() -> None:
    provider = _RoutingProvider()
    provider.provider_name = "shared-transport"
    realm = ProviderWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="lmstudio",
            model="concurrent-local-model",
            max_retries=0,
        ),
    )
    history = ProviderWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="openrouter",
            model="concurrent-remote-model",
            max_retries=0,
        ),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                generator.generate,
                _node(topic_id),
                seed=1,
                campaign_context={},
                dependency_topics={},
            )
            for generator, topic_id in ((realm, "realm"), (history, "history"))
        ]
        results = [future.result() for future in futures]

    assert {topic.topic_id for topic in results} == {"realm", "history"}
    assert provider.provider_name == "shared-transport"
    assert {call["provider_name"] for call in provider.calls} == {"shared-transport"}
    assert {call["kwargs"]["response_format"]["type"] for call in provider.calls} == {
        "json_schema",
        "json_object",
    }


def test_world_forge_rejects_non_object_collection_rows() -> None:
    provider = _Provider([_payload(entities=["not-an-object"])])
    generator = ProviderWorldForgeTopicGenerator(
        provider,
        WorldForgeProviderConfig(
            mode="live",
            provider="lmstudio",
            model="invalid-row-local-model",
            max_retries=0,
        ),
    )

    with pytest.raises(RuntimeError, match="schema validation"):
        generator.generate(_node(), seed=1, campaign_context={}, dependency_topics={})
