"""Bounded targeted regeneration for live World Forge topic proposals."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

from .world_forge_contract import CampaignTopicNode
from .world_forge_fact_pipeline import StructuredFactValidationError
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
            if issue.item_id:
                entity_ids.add(issue.item_id)
            if issue.field:
                fields.add(issue.field)
            instructions.add(
                issue.message
                or f"Resolve {issue.field or 'reference'} without fallback substitution."
            )
            scopes.add("entity_fields" if issue.field else "topic")
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

    scope = "topic" if "topic" in scopes else (
        "entities" if "entities" in scopes else "entity_fields"
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


def _entity_snapshot(topic: GeneratedTopic, selected_ids: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entity in topic.entities:
        entity_id = str(entity.get("id") or entity.get("entity_id") or "")
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
        str(entity.get("id") or entity.get("entity_id") or "")
        for entity in prior_topic.entities
        if str(entity.get("id") or entity.get("entity_id") or "")
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
    for attempt in range(1, attempts + 1):
        topic = generator.generate(
            node,
            seed=seed,
            campaign_context=context,
            dependency_topics=dependency_topics,
        )
        try:
            processed = process(topic)
        except Exception as error:
            last_error = error
            if not _provider_generated(topic) or attempt >= attempts:
                raise
            request = regeneration_request_from_error(
                node,
                error,
                attempt=attempt + 1,
            )
            if request is None:
                raise
            history.append(request.as_dict())
            context = targeted_regeneration_context(context, request, topic)
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
