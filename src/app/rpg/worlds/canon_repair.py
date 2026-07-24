"""Representation-only normalization and fail-closed publication validation."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from app.rpg.session.genesis.canon_audit import audit_generated_canon
from app.rpg.session.genesis.canon_relationships import compile_cross_domain_relationships
from app.rpg.session.genesis.world_forge_contract import CampaignTopicGraph
from app.rpg.session.genesis.world_forge_fact_pipeline import (
    compile_structured_entity_facts,
)
from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    WorldForgeGenerationResult,
)
from app.rpg.session.genesis.world_forge_integrity import (
    WorldForgeIntegrityError,
    WorldForgeIntegrityIssue,
)
from app.rpg.session.genesis.world_forge_presentation import (
    render_fact_derived_presentations,
)
from app.rpg.session.genesis.world_forge_quality import apply_world_forge_quality_audit
from app.rpg.session.genesis.world_forge_semantic_quality import (
    require_topic_semantic_quality,
)

_NON_GENERATION_CATEGORIES = {"compiler", "audit", "index", "bootstrap"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _normalize_entity(row: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    entity_id = _text(normalized.get("id") or normalized.get("entity_id"))
    if entity_id:
        normalized["id"] = entity_id
    if "name" not in normalized and normalized.get("title"):
        normalized["name"] = _text(normalized.get("title"))
    return normalized


def _normalize_document(row: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    document_id = _text(normalized.get("document_id") or normalized.get("id"))
    if document_id:
        normalized["document_id"] = document_id
    if "full_text" not in normalized and normalized.get("content") is not None:
        normalized["full_text"] = _text(normalized.get("content"))
    return normalized


def _normalize_fact(row: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    fact_id = _text(
        normalized.get("id")
        or normalized.get("fact_id")
        or normalized.get("evidence_id")
    )
    if fact_id:
        normalized["id"] = fact_id
    if "content" not in normalized and normalized.get("statement") is not None:
        normalized["content"] = _text(normalized.get("statement"))
    return normalized


def _normalize_relationship(row: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    relationship_id = _text(
        normalized.get("id") or normalized.get("relationship_id")
    )
    if relationship_id:
        normalized["id"] = relationship_id
    source_id = _text(
        normalized.get("source_id") or normalized.get("source_entity_id")
    )
    target_id = _text(
        normalized.get("target_id") or normalized.get("target_entity_id")
    )
    if source_id:
        normalized["source_id"] = source_id
    if target_id:
        normalized["target_id"] = target_id
    return normalized


def normalize_generation_contracts(
    generation: WorldForgeGenerationResult,
) -> WorldForgeGenerationResult:
    """Normalize declared field aliases without changing semantic meaning."""

    topics = tuple(
        replace(
            topic,
            documents=tuple(_normalize_document(row) for row in topic.documents),
            entities=tuple(_normalize_entity(row) for row in topic.entities),
            facts=tuple(_normalize_fact(row) for row in topic.facts),
            relationships=tuple(
                _normalize_relationship(row) for row in topic.relationships
            ),
            provenance={
                **dict(topic.provenance),
                "publication_normalization": "representation_only_v1",
            },
        )
        for topic in generation.topics
    )
    return replace(generation, topics=topics)


def _profile_revalidated_generation(
    generation: WorldForgeGenerationResult,
    topic_graph: CampaignTopicGraph,
    generation_context: Mapping[str, Any],
) -> WorldForgeGenerationResult:
    """Re-run Phase 4-7 gates from the pinned graph before publication."""

    source_topics = {topic.topic_id: topic for topic in generation.topics}
    processed: dict[str, GeneratedTopic] = {}
    for node in topic_graph.topological_order():
        if node.category in _NON_GENERATION_CATEGORIES:
            continue
        topic = source_topics.get(node.topic_id)
        if topic is None:
            continue
        dependencies = {
            dependency_id: processed[dependency_id]
            for dependency_id in node.dependencies
            if dependency_id in processed
        }
        if node.metadata.get("field_definitions"):
            topic = compile_structured_entity_facts(
                node,
                topic,
                dependencies,
            )
            semantic_report = require_topic_semantic_quality(
                node,
                topic,
                generation_context,
            )
            topic = replace(
                topic,
                provenance={
                    **dict(topic.provenance),
                    "publication_semantic_quality": semantic_report.as_dict(),
                },
            )
            topic = render_fact_derived_presentations(node, topic)
        processed[node.topic_id] = topic

    ordered_topics = tuple(
        processed.get(topic.topic_id, topic)
        for topic in generation.topics
    )
    return replace(generation, topics=ordered_topics)


def validate_generation_contracts(
    generation: WorldForgeGenerationResult,
    *,
    topic_graph: CampaignTopicGraph | None = None,
    generation_context: Mapping[str, Any] | None = None,
) -> WorldForgeGenerationResult:
    validated = generation
    if topic_graph is not None:
        validated = _profile_revalidated_generation(
            validated,
            topic_graph,
            dict(generation_context or {}),
        )

    relationships = compile_cross_domain_relationships(validated.topics)
    report = apply_world_forge_quality_audit(
        validated.topics,
        audit_generated_canon(
            validated.topics,
            compiled_relationships=relationships,
        ),
    )
    if report.passed:
        return validated
    issues = tuple(
        WorldForgeIntegrityIssue(
            code=issue.code,
            topic_id="publication",
            item_id=issue.item_id,
            field="",
            supplied_value="",
            message=issue.message,
        )
        for issue in report.issues
        if issue.severity == "error"
    )
    raise WorldForgeIntegrityError(issues)


def repair_generation_contracts(
    generation: WorldForgeGenerationResult,
    *,
    starting_location: str,
    topic_graph: CampaignTopicGraph | None = None,
    generation_context: Mapping[str, Any] | None = None,
) -> WorldForgeGenerationResult:
    """Deprecated repair entry point retained as a strict publication gate.

    ``starting_location`` is intentionally ignored. Publication may not move an
    entity or choose a fallback location to make a proposal appear valid.
    """

    del starting_location
    normalized = normalize_generation_contracts(generation)
    return validate_generation_contracts(
        normalized,
        topic_graph=topic_graph,
        generation_context=generation_context,
    )
