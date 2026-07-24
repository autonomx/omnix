"""Bounded targeted regeneration for live World Forge topic proposals."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

from .world_forge_contract import CampaignTopicNode
from .world_forge_fact_pipeline import (
    StructuredFactIssue,
    StructuredFactValidationError,
)
from .world_forge_generation import GeneratedTopic, WorldForgeTopicGenerator
from .world_forge_integrity import WorldForgeIntegrityError
from .world_forge_semantic_quality import WorldForgeSemanticQualityError


@dataclass(frozen=True)
class RegenerationRequest:
    topic_id: str
    attempt: int
    reason_codes: tuple[str, ...]
    entity_ids: tuple[str, ...]
    fields: tuple[str, ...]
    scope: str
    instructions: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "attempt": self.attempt,
            "reason_codes": list(self.reason_codes),
            "entity_ids": list(self.entity_ids),
            "fields": list(self.fields),
            "scope": self.scope,
            "instructions": list(self.instructions),
        }


def regeneration_request_from_error(
    node: CampaignTopicNode,
    error: Exception,
    *,
    attempt: int,
) -> RegenerationRequest | None:
    codes: set[str] = set()
    entity_ids: set[str] = set()
    fields: set[str] = set()
    instructions: set[str] = set()
    scopes: set[str] = set()

    if isinstance(error, WorldForgeIntegrityError):
        for issue in error.issues:
            codes.add(issue.code)
            if issue.field in {"source_id", "target_id", "entity_refs", "entities"}:
                scopes.add("topic")
            else:
                if issue.item_id:
                    entity_ids.add(issue.item_id)
                scopes.add("entity_fields" if issue.field else "topic")
            if issue.field:
                fields.add(issue.field)
            instructions.add(
                issue.message
                or f"Resolve {issue.field or 'reference'} without fallback substitution."
            )
    elif isinstance(error, StructuredFactValidationError):
        for issue in error.issues:
            codes.add(issue.code)
            if issue.entity_id:
                entity_ids.add(issue.entity_id)
            if issue.field_id:
                fields.add(issue.field_id)
            instructions.add(issue.message)
            scopes.add("entity_fields")
    elif isinstance(error, WorldForgeSemanticQualityError):
        for issue in error.report.issues:
            if issue.severity != "error":
                continue
            codes.add(issue.code)
            entity_ids.update(issue.entity_ids)
            fields.update(issue.fields)
            instructions.add(issue.reason)
            scopes.add(issue.regeneration_scope)
    else:
        return None

    scope = (
        "topic"
        if "topic" in scopes
        else ("entities" if "entities" in scopes else "entity_fields")
    )
    return RegenerationRequest(
        topic_id=node.topic_id,
        attempt=attempt,
        reason_codes=tuple(sorted(codes)),
        entity_ids=tuple(sorted(value for value in entity_ids if value)),
        fields=tuple(sorted(value for value in fields if value)),
        scope=scope,
        instructions=tuple(sorted(value for value in instructions if value)),
    )


def _entity_id(entity: Mapping[str, Any]) -> str:
    return str(entity.get("id") or entity.get("entity_id") or "").strip()


def _entity_snapshot(
    topic: GeneratedTopic,
    selected_ids: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entity in topic.entities:
        entity_id = _entity_id(entity)
        if selected_ids and entity_id not in selected_ids:
            continue
        rows.append(dict(entity))
    return rows


def targeted_regeneration_context(
    campaign_context: Mapping[str, Any],
    request: RegenerationRequest,
    prior_topic: GeneratedTopic,
) -> dict[str, Any]:
    all_entity_ids = tuple(
        _entity_id(entity)
        for entity in prior_topic.entities
        if _entity_id(entity)
    )
    selected_ids = set(request.entity_ids)
    if request.scope == "topic" or not selected_ids:
        selected_ids = set(all_entity_ids)
    return {
        **dict(campaign_context),
        "targeted_regeneration": {
            **request.as_dict(),
            "required_behavior": (
                "Regenerate only the identified topic, entities, or fields. Preserve "
                "stable IDs and all unaffected structured values. Do not choose fallback "
                "references, add generic filler, or alter unrelated canon."
            ),
            "prior_failing_entities": _entity_snapshot(prior_topic, selected_ids),
            "preserve_entity_ids": sorted(set(all_entity_ids) - selected_ids),
        },
    }


def _regeneration_invariant_error(
    request: RegenerationRequest,
    *,
    entity_id: str,
    field_id: str,
    message: str,
    supplied_value: Any = None,
) -> StructuredFactValidationError:
    return StructuredFactValidationError(
        (
            StructuredFactIssue(
                code="targeted_regeneration_invariant",
                topic_id=request.topic_id,
                entity_id=entity_id,
                field_id=field_id,
                message=message,
                supplied_value=supplied_value,
            ),
        )
    )


def enforce_targeted_regeneration(
    prior_topic: GeneratedTopic,
    candidate: GeneratedTopic,
    request: RegenerationRequest,
) -> GeneratedTopic:
    """Deterministically preserve every value outside the requested retry scope."""

    if candidate.topic_id != prior_topic.topic_id or candidate.topic_id != request.topic_id:
        raise _regeneration_invariant_error(
            request,
            entity_id="",
            field_id="topic_id",
            message="Targeted regeneration may not change the topic ID.",
            supplied_value=candidate.topic_id,
        )

    prior_entities = {
        _entity_id(entity): dict(entity)
        for entity in prior_topic.entities
        if _entity_id(entity)
    }
    candidate_entities = {
        _entity_id(entity): dict(entity)
        for entity in candidate.entities
        if _entity_id(entity)
    }
    selected_ids = set(request.entity_ids)

    if request.scope == "topic":
        if prior_entities and set(candidate_entities) != set(prior_entities):
            raise _regeneration_invariant_error(
                request,
                entity_id="",
                field_id="id",
                message=(
                    "Topic regeneration must preserve the complete stable entity ID set."
                ),
                supplied_value=sorted(candidate_entities),
            )
        return replace(
            candidate,
            provenance={
                **dict(candidate.provenance),
                "targeted_regeneration_enforced": True,
                "targeted_regeneration_scope": request.scope,
            },
        )

    missing = selected_ids.difference(candidate_entities)
    if missing:
        raise _regeneration_invariant_error(
            request,
            entity_id=sorted(missing)[0],
            field_id="id",
            message="Regenerated output omitted a selected stable entity ID.",
            supplied_value=sorted(candidate_entities),
        )

    merged_entities: list[dict[str, Any]] = []
    for entity in prior_topic.entities:
        entity_id = _entity_id(entity)
        prior = dict(entity)
        if entity_id not in selected_ids:
            merged_entities.append(prior)
            continue
        regenerated = candidate_entities[entity_id]
        if request.scope == "entities":
            merged_entities.append(regenerated)
            continue
        merged = dict(prior)
        for field_id in request.fields:
            if field_id not in regenerated:
                raise _regeneration_invariant_error(
                    request,
                    entity_id=entity_id,
                    field_id=field_id,
                    message="Regenerated output omitted a selected field.",
                )
            merged[field_id] = regenerated[field_id]
        merged_entities.append(merged)

    return replace(
        candidate,
        documents=prior_topic.documents,
        entities=tuple(merged_entities),
        facts=prior_topic.facts,
        relationships=prior_topic.relationships,
        knowledge_rules=prior_topic.knowledge_rules,
        story_threads=prior_topic.story_threads,
        provenance={
            **dict(candidate.provenance),
            "targeted_regeneration_enforced": True,
            "targeted_regeneration_scope": request.scope,
            "targeted_regeneration_preserved_entity_ids": sorted(
                set(prior_entities) - selected_ids
            ),
            "targeted_regeneration_updated_entity_ids": sorted(selected_ids),
            "targeted_regeneration_updated_fields": list(request.fields),
        },
    )


def _provider_generated(topic: GeneratedTopic) -> bool:
    return str(dict(topic.provenance).get("generator") or "").startswith(
        "structured_world_forge_provider_"
    )


def generate_with_targeted_regeneration(
    generator: WorldForgeTopicGenerator,
    node: CampaignTopicNode,
    *,
    seed: int,
    campaign_context: Mapping[str, Any],
    dependency_topics: Mapping[str, GeneratedTopic],
    process: Callable[[GeneratedTopic], GeneratedTopic],
    max_attempts: int = 3,
) -> GeneratedTopic:
    """Generate, validate, and retry only actionable live-provider failures."""

    attempts = max(1, min(int(max_attempts), 5))
    context = dict(campaign_context)
    history: list[dict[str, Any]] = []
    last_error: Exception | None = None
    prior_failed_topic: GeneratedTopic | None = None
    pending_request: RegenerationRequest | None = None

    for attempt in range(1, attempts + 1):
        generated = generator.generate(
            node,
            seed=seed,
            campaign_context=context,
            dependency_topics=dependency_topics,
        )
        topic = generated
        try:
            if pending_request is not None and prior_failed_topic is not None:
                topic = enforce_targeted_regeneration(
                    prior_failed_topic,
                    generated,
                    pending_request,
                )
            processed = process(topic)
        except Exception as error:
            last_error = error
            if not _provider_generated(generated) or attempt >= attempts:
                raise
            request = regeneration_request_from_error(
                node,
                error,
                attempt=attempt + 1,
            )
            if request is None:
                raise
            history.append(request.as_dict())
            if pending_request is None:
                prior_failed_topic = generated
            context = targeted_regeneration_context(
                context,
                request,
                prior_failed_topic or generated,
            )
            pending_request = request
            continue
        if history:
            processed = replace(
                processed,
                provenance={
                    **dict(processed.provenance),
                    "targeted_regeneration_attempt_count": attempt,
                    "targeted_regeneration_history": history,
                    "targeted_regeneration_succeeded": True,
                },
            )
        return processed
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"world_forge_regeneration_exhausted:{node.topic_id}")
