"""Single-pass, profile-typed provider boundary for durable World Forge jobs."""
from __future__ import annotations

import json
import re
from contextlib import nullcontext
from dataclasses import replace
from typing import Any, Literal, Mapping, Sequence, StrictBool, StrictFloat, StrictInt, StrictStr

from pydantic import BaseModel, ConfigDict, Field, create_model

from app.providers.base import ChatMessage
from app.providers.structured import StructuredContract, StructuredOutputGateway, StructuredRetryBudget
from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg_world_forge_provider import (
    ProviderWorldForgeTopicGenerator,
    WorldForgeEntityRegistryResponse,
    WorldForgeTopicResponse,
    _LMSTUDIO_WORLD_FORGE_CALLS,
    _entity_registry_contract,
    _entity_registry_payload,
    _entity_registry_system_prompt,
    _model_rows,
    _payload,
    _system_prompt,
    _token_estimate,
    _topic_contract,
)

_SAFE_MODEL = re.compile(r"[^A-Za-z0-9_]+")


class SinglePassWorldForgeProviderError(RuntimeError):
    def __init__(
        self,
        topic_id: str,
        error: Exception,
        diagnostics: Mapping[str, Any],
        *,
        unit: str = "topic",
    ) -> None:
        self.topic_id = topic_id
        self.error = error
        self.diagnostics = dict(diagnostics)
        self.unit = unit
        super().__init__(
            f"world_forge_single_pass_{unit}_failed:{topic_id}:"
            f"{type(error).__name__}:{error}"
        )


def _literal(values: Sequence[str]) -> Any:
    normalized = tuple(dict.fromkeys(str(value) for value in values if str(value)))
    return Literal.__getitem__(normalized) if normalized else StrictStr


def _field_definitions(node: CampaignTopicNode) -> tuple[dict[str, Any], ...]:
    value = node.metadata.get("field_definitions")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(dict(row) for row in value if isinstance(row, Mapping))


def _reference_candidates(
    node: CampaignTopicNode,
    dependency_topics: Mapping[str, GeneratedTopic],
    allocated_ids: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    candidates: dict[str, tuple[str, ...]] = {}
    definitions = _field_definitions(node)
    ids_by_domain: dict[str, tuple[str, ...]] = {
        domain_id: tuple(
            str(entity.get("id") or entity.get("entity_id") or "")
            for entity in topic.entities
            if str(entity.get("id") or entity.get("entity_id") or "")
        )
        for domain_id, topic in dependency_topics.items()
    }
    ids_by_domain[node.topic_id] = allocated_ids
    for definition in definitions:
        field_id = str(definition.get("field_id") or "")
        allowed = tuple(str(value) for value in definition.get("allowed_target_domains") or ())
        candidates[field_id] = tuple(
            dict.fromkeys(
                entity_id
                for domain_id in allowed
                for entity_id in ids_by_domain.get(domain_id, ())
                if entity_id
            )
        )
    return candidates


def _python_type(
    definition: Mapping[str, Any],
    *,
    reference_ids: tuple[str, ...],
) -> Any:
    value_type = str(definition.get("value_type") or "string")
    if value_type == "string":
        return StrictStr
    if value_type == "integer":
        return StrictInt
    if value_type == "number":
        return StrictInt | StrictFloat
    if value_type == "boolean":
        return StrictBool
    if value_type == "enum":
        return _literal(tuple(str(value) for value in definition.get("enum_values") or ()))
    if value_type == "entity_ref":
        return _literal(reference_ids)
    if value_type == "entity_ref_list":
        return list[_literal(reference_ids)]
    if value_type == "structured_object":
        return dict[str, Any] | list[Any]
    return Any


def _profile_entity_model(
    node: CampaignTopicNode,
    *,
    allocated_ids: tuple[str, ...],
    dependency_topics: Mapping[str, GeneratedTopic],
) -> type[BaseModel]:
    fields: dict[str, tuple[Any, Any]] = {
        "id": (_literal(allocated_ids), ...),
        "kind": (_literal((str(node.metadata.get("entity_kind") or node.topic_id),)), ...),
    }
    references = _reference_candidates(node, dependency_topics, allocated_ids)
    for definition in _field_definitions(node):
        field_id = str(definition.get("field_id") or "").strip()
        if not field_id or field_id in {"id", "kind"}:
            continue
        annotation = _python_type(
            definition,
            reference_ids=references.get(field_id, ()),
        )
        default = ... if bool(definition.get("required", False)) else None
        if default is None:
            annotation = annotation | None
        fields[field_id] = (
            annotation,
            Field(
                default=default,
                description=str(definition.get("description") or ""),
            ),
        )
    fields.setdefault("name", (StrictStr, ...))
    fields.setdefault("entity_id", (StrictStr | None, None))
    fields.setdefault("short_summary", (StrictStr | None, None))
    fields.setdefault("dossier", (dict[str, Any] | None, None))
    fields.setdefault("registry_role", (StrictStr | None, None))
    fields.setdefault("registry_distinction", (StrictStr | None, None))
    safe_name = _SAFE_MODEL.sub("_", node.topic_id).strip("_") or "topic"
    return create_model(
        f"WorldForgeProfileEntity_{safe_name}",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


def _profile_topic_contract(
    node: CampaignTopicNode,
    *,
    expected_entity_count: int,
    expected_entity_ids: tuple[str, ...],
    expected_entity_names: tuple[str, ...],
    dependency_topics: Mapping[str, GeneratedTopic],
) -> StructuredContract[Any]:
    entity_model = _profile_entity_model(
        node,
        allocated_ids=expected_entity_ids,
        dependency_topics=dependency_topics,
    )
    safe_name = _SAFE_MODEL.sub("_", node.topic_id).strip("_") or "topic"
    response_model = create_model(
        f"WorldForgeProfileTopicResponse_{safe_name}",
        __base__=WorldForgeTopicResponse,
        entities=(list[entity_model], ...),
    )

    def validate_topic(value: Any) -> None:
        if value.topic_id != node.topic_id:
            raise ValueError(
                f"World Forge provider returned {value.topic_id or '<missing>'} for {node.topic_id}"
            )
        if len(value.entities) != expected_entity_count:
            raise ValueError(
                f"World Forge provider returned {len(value.entities)} entities for "
                f"{node.topic_id}; expected {expected_entity_count}"
            )
        actual_ids = tuple(
            str(row.get("id") or row.get("entity_id") or "")
            for row in _model_rows(value.entities)
        )
        if set(actual_ids) != set(expected_entity_ids) or len(actual_ids) != len(set(actual_ids)):
            raise ValueError(
                f"World Forge provider returned IDs {list(actual_ids)} for {node.topic_id}; "
                f"expected {list(expected_entity_ids)}"
            )
        if expected_entity_names:
            actual_names = tuple(
                str(row.get("name") or "").strip() for row in _model_rows(value.entities)
            )
            if actual_names != expected_entity_names:
                raise ValueError(
                    f"World Forge provider returned names {list(actual_names)} for "
                    f"{node.topic_id}; expected {list(expected_entity_names)}"
                )

    return StructuredContract(
        contract_id=f"rpg.world_forge.topic.{node.topic_id}",
        version=4,
        output_model=response_model,
        semantic_validator=validate_topic,
        schema_profile="canon_strict",
        schema_name=f"rpg_world_forge_{safe_name}",
        regenerate_on_semantic_failure=False,
    )


def _prompt_field_contract(
    node: CampaignTopicNode,
    *,
    allocated_ids: tuple[str, ...],
    dependency_topics: Mapping[str, GeneratedTopic],
) -> dict[str, Any]:
    references = _reference_candidates(node, dependency_topics, allocated_ids)
    return {
        "entity_kind": str(node.metadata.get("entity_kind") or node.topic_id),
        "allocated_entity_ids": list(allocated_ids),
        "extra_fields": "forbidden",
        "fields": [
            {
                **definition,
                "candidate_reference_ids": list(
                    references.get(str(definition.get("field_id") or ""), ())
                ),
            }
            for definition in _field_definitions(node)
        ],
    }


class SinglePassProviderWorldForgeTopicGenerator(ProviderWorldForgeTopicGenerator):
    """Use one provider call per planned registry or entity generation unit."""

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
        entity_count = expected_entity_count or node.target_count
        allocated_ids = expected_entity_ids or self._assigned_entity_ids(
            node,
            batch_index=batch_index or 0,
            requested_count=entity_count,
        )
        effective_batch_index = batch_index if batch_index is not None else 0
        effective_batch_count = batch_count if batch_count is not None else 1
        field_contract = _prompt_field_contract(
            node,
            allocated_ids=allocated_ids,
            dependency_topics=dependency_topics,
        )
        system_prompt = _system_prompt(
            node,
            batch_index=effective_batch_index,
            batch_count=effective_batch_count,
            existing_entities=existing_entities,
            assigned_entity_ids=allocated_ids,
            assigned_entities=assigned_entities,
        ) + (
            " The PROFILE_FIELD_CONTRACT below is authoritative. Every entity must use "
            "its exact kind and allocated ID, include every required field at the top "
            "level, use the declared JSON types, and choose references only from the "
            "listed candidate IDs. Unknown top-level entity fields are forbidden."
        )
        request_payload = _payload(
            node,
            seed=seed,
            campaign_context=campaign_context,
            dependency_topics=dependency_topics,
            batch_index=effective_batch_index,
            batch_count=effective_batch_count,
            existing_entities=existing_entities,
            assigned_entity_ids=allocated_ids,
            assigned_entities=assigned_entities,
        )
        request_payload["required_output"]["profile_field_contract"] = field_contract
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(
                role="user",
                content=json.dumps(request_payload, ensure_ascii=False, sort_keys=True),
            ),
        ]
        if _field_definitions(node):
            contract = _profile_topic_contract(
                node,
                expected_entity_count=entity_count,
                expected_entity_ids=allocated_ids,
                expected_entity_names=expected_entity_names,
                dependency_topics=dependency_topics,
            )
        else:
            contract = _topic_contract(
                node.topic_id,
                expected_entity_count=entity_count,
                expected_entity_ids=allocated_ids,
                expected_entity_names=expected_entity_names,
            )
        gateway = StructuredOutputGateway(self.provider)
        provider_key = self.config.provider.strip().casefold().removeprefix("llm:")
        limiter = _LMSTUDIO_WORLD_FORGE_CALLS if provider_key == "lmstudio" else nullcontext()
        with limiter:
            outcome = gateway.try_generate(
                messages,
                contract=replace(
                    contract,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                ),
                model=self.config.model or None,
                retry_budget=StructuredRetryBudget(
                    max_provider_calls=1,
                    max_transport_retries=0,
                    max_format_downgrades=0,
                    max_validation_regenerations=0,
                    deadline_seconds=float(self.config.timeout_seconds),
                ),
            )
        diagnostics = outcome.diagnostics
        if outcome.error is not None:
            raise SinglePassWorldForgeProviderError(
                node.topic_id,
                outcome.error,
                diagnostics.as_dict(),
                unit="topic",
            ) from outcome.error
        assert outcome.value is not None
        value = self._apply_registry_slots(outcome.value, assigned_entities)
        payload = json.dumps(
            value.model_dump(mode="python"),
            ensure_ascii=False,
            sort_keys=True,
        )
        return (
            value,
            diagnostics.as_dict(),
            sum(_token_estimate(message.content) for message in messages),
            _token_estimate(payload),
        )

    def _generate_entity_registry(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: Mapping[str, Any],
        dependency_topics: Mapping[str, GeneratedTopic],
    ) -> tuple[WorldForgeEntityRegistryResponse, Mapping[str, Any], int, int]:
        allocated_ids = self._allocated_entity_ids(node)
        messages = [
            ChatMessage(role="system", content=_entity_registry_system_prompt(node)),
            ChatMessage(
                role="user",
                content=json.dumps(
                    _entity_registry_payload(
                        node,
                        seed=seed,
                        campaign_context=campaign_context,
                        dependency_topics=dependency_topics,
                        assigned_entity_ids=allocated_ids,
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ),
        ]
        gateway = StructuredOutputGateway(self.provider)
        provider_key = self.config.provider.strip().casefold().removeprefix("llm:")
        limiter = _LMSTUDIO_WORLD_FORGE_CALLS if provider_key == "lmstudio" else nullcontext()
        with limiter:
            outcome = gateway.try_generate(
                messages,
                contract=replace(
                    _entity_registry_contract(
                        node.topic_id,
                        expected_entity_ids=allocated_ids,
                    ),
                    temperature=self.config.temperature,
                    max_tokens=min(self.config.max_tokens, 2048),
                ),
                model=self.config.model or None,
                retry_budget=StructuredRetryBudget(
                    max_provider_calls=1,
                    max_transport_retries=0,
                    max_format_downgrades=0,
                    max_validation_regenerations=0,
                    deadline_seconds=float(self.config.timeout_seconds),
                ),
            )
        diagnostics = outcome.diagnostics
        if outcome.error is not None:
            raise SinglePassWorldForgeProviderError(
                node.topic_id,
                outcome.error,
                diagnostics.as_dict(),
                unit="registry",
            ) from outcome.error
        assert outcome.value is not None
        payload = json.dumps(
            outcome.value.model_dump(mode="python"),
            ensure_ascii=False,
            sort_keys=True,
        )
        return (
            outcome.value,
            diagnostics.as_dict(),
            sum(_token_estimate(message.content) for message in messages),
            _token_estimate(payload),
        )


__all__ = [
    "SinglePassProviderWorldForgeTopicGenerator",
    "SinglePassWorldForgeProviderError",
]
