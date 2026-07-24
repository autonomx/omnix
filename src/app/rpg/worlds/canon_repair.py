"""Representation-only normalization and fail-closed publication validation."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from app.rpg.session.genesis.canon_audit import audit_generated_canon
from app.rpg.session.genesis.canon_relationships import compile_cross_domain_relationships
from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    WorldForgeGenerationResult,
)
from app.rpg.session.genesis.world_forge_integrity import (
    WorldForgeIntegrityError,
    WorldForgeIntegrityIssue,
)
from app.rpg.session.genesis.world_forge_quality import apply_world_forge_quality_audit


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
        normalized.get("id") or normalized.get("fact_id") or normalized.get("evidence_id")
    )
    if fact_id:
        normalized["id"] = fact_id
    if "content" not in normalized and normalized.get("statement") is not None:
        normalized["content"] = _text(normalized.get("statement"))
    return normalized


def _normalize_relationship(row: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    relationship_id = _text(normalized.get("id") or normalized.get("relationship_id"))
    if relationship_id:
        normalized["id"] = relationship_id
    source_id = _text(normalized.get("source_id") or normalized.get("source_entity_id"))
    target_id = _text(normalized.get("target_id") or normalized.get("target_entity_id"))
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


def validate_generation_contracts(
    generation: WorldForgeGenerationResult,
) -> None:
    relationships = compile_cross_domain_relationships(generation.topics)
    report = apply_world_forge_quality_audit(
        generation.topics,
        audit_generated_canon(
            generation.topics,
            compiled_relationships=relationships,
        ),
    )
    if report.passed:
        return
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
) -> WorldForgeGenerationResult:
    """Deprecated entry point retained only as a fail-closed publication gate.

    ``starting_location`` is intentionally ignored. Publication may not move an
    entity or choose a fallback location to make a proposal appear valid.
    """

    del starting_location
    normalized = normalize_generation_contracts(generation)
    validate_generation_contracts(normalized)
    return normalized
