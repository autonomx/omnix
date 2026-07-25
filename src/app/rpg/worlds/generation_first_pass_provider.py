"""Schema-pinned first-pass World Forge provider contracts.

The provider receives two different identity namespaces in the same response:
the root topic ID and one or more allocated entity IDs.  Keep those identities
in the JSON Schema itself so guided decoding cannot place an entity ID in the
root ``topic_id`` field.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any, Mapping

from pydantic import create_model

from app.providers.base import ChatMessage
from app.providers.structured import StructuredContract, StructuredOutputGateway
from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg_world_forge_provider import (
    WorldForgeEntityRegistryItem,
    WorldForgeEntityRegistryResponse,
    WorldForgeTopicResponse,
    _entity_registry_contract as _legacy_entity_registry_contract,
    _entity_registry_payload,
    _entity_registry_system_prompt,
    _model_rows,
    _payload,
    _system_prompt,
    _token_estimate,
    _topic_contract as _legacy_topic_contract,
)
from app.rpg_world_forge_single_pass_provider import (
    SinglePassProviderWorldForgeTopicGenerator,
    SinglePassWorldForgeProviderError,
    _definitions,
    _entity_model,
    _field_contract,
    _literal,
    _one_call_budget,
)

_SAFE_MODEL = re.compile(r"[^A-Za-z0-9_]+")


def _safe_name(value: str) -> str:
    return _SAFE_MODEL.sub("_", value).strip("_") or "topic"


def _strict_profile_contract(
    node: CampaignTopicNode,
    *,
    expected_count: int,
    expected_ids: tuple[str, ...],
    expected_names: tuple[str, ...],
    dependencies: Mapping[str, GeneratedTopic],
) -> StructuredContract[Any]:
    safe = _safe_name(node.topic_id)
    entity_model = _entity_model(
        node,
        allocated_ids=expected_ids,
        dependencies=dependencies,
    )
    response_model = create_model(
        f"WorldForgeStrictProfileTopicResponse_{safe}",
        __base__=WorldForgeTopicResponse,
        topic_id=(_literal((node.topic_id,)), ...),
        entities=(list[entity_model], ...),
    )

    def validate(value: Any) -> None:
        # These checks remain as defence in depth for providers that ignore
        # response_format. Guided decoders receive the same rules as constants.
        if value.topic_id != node.topic_id:
            raise ValueError(f"topic_id_mismatch:{value.topic_id}:{node.topic_id}")
        if len(value.entities) != expected_count:
            raise ValueError(
                f"entity_count_mismatch:{len(value.entities)}:{expected_count}"
            )
        rows = _model_rows(value.entities)
        actual_ids = tuple(str(row.get("id") or "") for row in rows)
        if set(actual_ids) != set(expected_ids) or len(actual_ids) != len(set(actual_ids)):
            raise ValueError(f"entity_id_set_mismatch:{actual_ids}:{expected_ids}")
        if expected_names:
            actual_names = tuple(str(row.get("name") or "").strip() for row in rows)
            if actual_names != expected_names:
                raise ValueError(
                    f"entity_name_set_mismatch:{actual_names}:{expected_names}"
                )

    return StructuredContract(
        contract_id=f"rpg.world_forge.topic.{node.topic_id}",
        version=5,
        output_model=response_model,
        semantic_validator=validate,
        schema_profile="canon_strict",
        schema_name=f"rpg_world_forge_strict_{safe}",
        regenerate_on_semantic_failure=False,
    )


def _strict_topic_contract(
    expected_topic_id: str,
    *,
    expected_entity_count: int | None,
    expected_entity_ids: tuple[str, ...],
    expected_entity_names: tuple[str, ...],
) -> StructuredContract[Any]:
    base = _legacy_topic_contract(
        expected_topic_id,
        expected_entity_count=expected_entity_count,
        expected_entity_ids=expected_entity_ids,
        expected_entity_names=expected_entity_names,
    )
    safe = _safe_name(expected_topic_id)
    response_model = create_model(
        f"WorldForgeStrictTopicResponse_{safe}",
        __base__=WorldForgeTopicResponse,
        topic_id=(_literal((expected_topic_id,)), ...),
    )
    return replace(
        base,
        contract_id=f"rpg.world_forge.topic.{expected_topic_id}",
        version=4,
        output_model=response_model,
        schema_name=f"rpg_world_forge_strict_{safe}",
        regenerate_on_semantic_failure=False,
    )


def _strict_registry_contract(
    expected_topic_id: str,
    *,
    expected_entity_ids: tuple[str, ...],
) -> StructuredContract[Any]:
    base = _legacy_entity_registry_contract(
        expected_topic_id,
        expected_entity_ids=expected_entity_ids,
    )
    safe = _safe_name(expected_topic_id)
    item_model = create_model(
        f"WorldForgeStrictRegistryItem_{safe}",
        __base__=WorldForgeEntityRegistryItem,
        id=(_literal(expected_entity_ids), ...),
    )
    response_model = create_model(
        f"WorldForgeStrictRegistryResponse_{safe}",
        __base__=WorldForgeEntityRegistryResponse,
        topic_id=(_literal((expected_topic_id,)), ...),
        entities=(list[item_model], ...),
    )
    return replace(
        base,
        contract_id=f"rpg.world_forge.entity_registry.{expected_topic_id}",
        version=2,
        output_model=response_model,
        schema_name=f"rpg_world_forge_registry_strict_{safe}",
        regenerate_on_semantic_failure=False,
    )


def _identity_contract(topic_id: str, entity_ids: tuple[str, ...]) -> dict[str, Any]:
    return {
        "root_topic_id": topic_id,
        "entity_id_path": "entities[].id",
        "allocated_entity_ids": list(entity_ids),
        "root_topic_id_must_not_be_an_entity_id": True,
    }


def _identity_instruction(topic_id: str, entity_ids: tuple[str, ...]) -> str:
    allocated = ", ".join(entity_ids) or "none"
    return (
        f" ROOT_IDENTITY_CONTRACT: the root topic_id must be exactly {topic_id!r}. "
        "Never place an entity ID in root topic_id. Entity IDs belong only in "
        f"entities[].id and must come from this allocation: {allocated}."
    )


class FirstPassWorldForgeTopicGenerator(SinglePassProviderWorldForgeTopicGenerator):
    """Single-call generation with schema-pinned root and entity identities."""

    def _generate_response(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: Mapping[str, Any],
        dependency_topics: Mapping[str, GeneratedTopic],
        expected_entity_count: int | None = None,
        expected_entity_ids: tuple[str, ...] = (),
        expected_entity_names: tuple[str, ...] = (),
        batch_index: int | None = None,
        batch_count: int | None = None,
        existing_entities: tuple[Mapping[str, str], ...] = (),
        assigned_entity_ids: tuple[str, ...] = (),
        assigned_entities: tuple[Mapping[str, str], ...] = (),
    ) -> tuple[WorldForgeTopicResponse, Mapping[str, Any], int, int]:
        count = expected_entity_count or node.target_count
        ids = expected_entity_ids or self._assigned_entity_ids(
            node,
            batch_index=batch_index or 0,
            requested_count=count,
        )
        index = batch_index if batch_index is not None else 0
        total = batch_count if batch_count is not None else 1
        prompt = _system_prompt(
            node,
            batch_index=index,
            batch_count=total,
            existing_entities=existing_entities,
            assigned_entity_ids=ids,
            assigned_entities=assigned_entities,
        ) + (
            " PROFILE_FIELD_CONTRACT is authoritative. Use the exact allocated ID "
            "and entity kind, include all required top-level fields, obey declared "
            "JSON types, and use only listed reference IDs. Unknown fields are forbidden."
        ) + _identity_instruction(node.topic_id, ids)
        request = _payload(
            node,
            seed=seed,
            campaign_context=campaign_context,
            dependency_topics=dependency_topics,
            batch_index=index,
            batch_count=total,
            existing_entities=existing_entities,
            assigned_entity_ids=ids,
            assigned_entities=assigned_entities,
        )
        request["required_output"]["identity_contract"] = _identity_contract(
            node.topic_id,
            ids,
        )
        request["required_output"]["profile_field_contract"] = _field_contract(
            node,
            allocated_ids=ids,
            dependencies=dependency_topics,
        )
        messages = [
            ChatMessage(role="system", content=prompt),
            ChatMessage(
                role="user",
                content=json.dumps(request, ensure_ascii=False, sort_keys=True),
            ),
        ]
        contract = (
            _strict_profile_contract(
                node,
                expected_count=count,
                expected_ids=ids,
                expected_names=expected_entity_names,
                dependencies=dependency_topics,
            )
            if _definitions(node)
            else _strict_topic_contract(
                node.topic_id,
                expected_entity_count=count,
                expected_entity_ids=ids,
                expected_entity_names=expected_entity_names,
            )
        )
        gateway = StructuredOutputGateway(self.provider)
        with self._limiter():
            outcome = gateway.try_generate(
                messages,
                contract=replace(
                    contract,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                ),
                model=self.config.model or None,
                retry_budget=_one_call_budget(self.config.timeout_seconds),
            )
        if outcome.error is not None:
            raise SinglePassWorldForgeProviderError(
                node.topic_id,
                outcome.error,
                outcome.diagnostics.as_dict(),
                unit="topic",
            ) from outcome.error
        assert outcome.value is not None
        value = self._apply_registry_slots(outcome.value, assigned_entities)
        rendered = json.dumps(
            value.model_dump(mode="python"),
            ensure_ascii=False,
            sort_keys=True,
        )
        return (
            value,
            outcome.diagnostics.as_dict(),
            sum(_token_estimate(message.content) for message in messages),
            _token_estimate(rendered),
        )

    def _generate_entity_registry(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: Mapping[str, Any],
        dependency_topics: Mapping[str, GeneratedTopic],
    ) -> tuple[WorldForgeEntityRegistryResponse, Mapping[str, Any], int, int]:
        ids = self._allocated_entity_ids(node)
        request = _entity_registry_payload(
            node,
            seed=seed,
            campaign_context=campaign_context,
            dependency_topics=dependency_topics,
            assigned_entity_ids=ids,
        )
        request["required_output"]["identity_contract"] = _identity_contract(
            node.topic_id,
            ids,
        )
        messages = [
            ChatMessage(
                role="system",
                content=_entity_registry_system_prompt(node)
                + _identity_instruction(node.topic_id, ids),
            ),
            ChatMessage(
                role="user",
                content=json.dumps(request, ensure_ascii=False, sort_keys=True),
            ),
        ]
        gateway = StructuredOutputGateway(self.provider)
        with self._limiter():
            outcome = gateway.try_generate(
                messages,
                contract=replace(
                    _strict_registry_contract(
                        node.topic_id,
                        expected_entity_ids=ids,
                    ),
                    temperature=self.config.temperature,
                    max_tokens=min(self.config.max_tokens, 2048),
                ),
                model=self.config.model or None,
                retry_budget=_one_call_budget(self.config.timeout_seconds),
            )
        if outcome.error is not None:
            raise SinglePassWorldForgeProviderError(
                node.topic_id,
                outcome.error,
                outcome.diagnostics.as_dict(),
                unit="registry",
            ) from outcome.error
        assert outcome.value is not None
        rendered = json.dumps(
            outcome.value.model_dump(mode="python"),
            ensure_ascii=False,
            sort_keys=True,
        )
        return (
            outcome.value,
            outcome.diagnostics.as_dict(),
            sum(_token_estimate(message.content) for message in messages),
            _token_estimate(rendered),
        )


__all__ = ["FirstPassWorldForgeTopicGenerator"]
