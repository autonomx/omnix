"""Apply authoritative internal planning assignments before canon publication."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Protocol

from .world_forge_contract import CampaignTopicNode
from .world_forge_fact_pipeline_trusted import compile_structured_entity_facts
from .world_forge_generation import GeneratedTopic, WorldForgeTopicGenerator


def _entity_id(row: Mapping[str, Any]) -> str:
    return str(row.get("id") or row.get("entity_id") or "").strip()


def _planning_slice(context: Mapping[str, Any]) -> dict[str, Any]:
    value = context.get("planning_slice")
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any, key: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, Mapping):
        return ()
    return tuple(dict(row) for row in value.get(key) or () if isinstance(row, Mapping))


def _expected_ids(node: CampaignTopicNode) -> tuple[str, ...]:
    value = node.metadata.get("authoritative_entity_ids")
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value if str(item))


def _apply_place_plan(entity: dict[str, Any], planning: Mapping[str, Any]) -> set[str]:
    place_id = _entity_id(entity)
    row = next(
        (
            item
            for item in _rows(planning.get("settlement_origin_plan"), "settlements")
            if str(item.get("place_id") or "") == place_id
        ),
        None,
    )
    if row is None:
        return set()
    changed: set[str] = set()
    assignments = {
        "region_id": str(row.get("region_id") or ""),
        "founding_event_ids": [str(row.get("founding_event_id") or "")]
        if row.get("founding_event_id")
        else [],
        "founding_purpose": str(row.get("founding_purpose") or ""),
    }
    for field_id, value in assignments.items():
        if value not in ("", []) and entity.get(field_id) != value:
            entity[field_id] = value
            changed.add(field_id)
    return changed


def _apply_culture_plan(entity: dict[str, Any], planning: Mapping[str, Any]) -> set[str]:
    culture_id = _entity_id(entity)
    row = next(
        (
            item
            for item in _rows(planning.get("culture_lineage_plan"), "lineages")
            if str(item.get("culture_id") or "") == culture_id
        ),
        None,
    )
    if row is None:
        return set()
    regions = [str(value) for value in row.get("homeland_region_ids") or () if str(value)]
    parent = str(row.get("parent_culture_id") or "")
    event_id = str(row.get("origin_event_id") or "")
    assignments = {
        "region_ids": regions,
        "origin_region_ids": regions,
        "origin_event_ids": [event_id] if event_id else [],
        "parent_culture_ids": [parent] if parent else [],
    }
    changed: set[str] = set()
    for field_id, value in assignments.items():
        if entity.get(field_id) != value:
            entity[field_id] = value
            changed.add(field_id)
    return changed


def _apply_group_plan(entity: dict[str, Any], planning: Mapping[str, Any]) -> set[str]:
    group_id = _entity_id(entity)
    claims = [
        row
        for row in _rows(planning.get("political_claim_graph"), "claims")
        if str(row.get("claimant_group_id") or "") == group_id
    ]
    if not claims:
        return set()
    inherited = entity.get("inherited_claims")
    payload = dict(inherited) if isinstance(inherited, Mapping) else {}
    planned = [
        {
            "claim_id": str(row.get("claim_id") or ""),
            "target_region_id": str(row.get("target_region_id") or ""),
            "claim_type": str(row.get("claim_type") or ""),
            "status": str(row.get("status") or ""),
        }
        for row in claims
    ]
    if payload.get("planned_claims") == planned:
        return set()
    payload["planned_claims"] = planned
    entity["inherited_claims"] = payload
    return {"inherited_claims"}


def project_planning_into_topic(
    node: CampaignTopicNode,
    topic: GeneratedTopic,
    *,
    campaign_context: Mapping[str, Any],
    dependency_topics: Mapping[str, GeneratedTopic],
) -> GeneratedTopic:
    planning = _planning_slice(campaign_context)
    expected_ids = _expected_ids(node)
    actual_ids = tuple(_entity_id(row) for row in topic.entities if _entity_id(row))
    if expected_ids and set(actual_ids) != set(expected_ids):
        raise ValueError(
            f"authoritative_anchor_identity_mismatch:{node.topic_id}:{actual_ids}:{expected_ids}"
        )
    if not planning:
        return topic

    entities: list[dict[str, Any]] = []
    changed_fields: dict[str, set[str]] = {}
    for raw in topic.entities:
        entity = dict(raw)
        changed: set[str] = set()
        if node.topic_id == "places":
            changed.update(_apply_place_plan(entity, planning))
        elif node.topic_id == "cultures":
            changed.update(_apply_culture_plan(entity, planning))
        elif node.topic_id == "groups":
            changed.update(_apply_group_plan(entity, planning))
        entity_id = _entity_id(entity)
        if entity_id and changed:
            changed_fields[entity_id] = changed
        entities.append(entity)
    if not changed_fields:
        return topic

    facts = tuple(
        fact
        for fact in topic.facts
        if not (
            str(fact.get("subject") or "") in changed_fields
            and str(fact.get("field_id") or fact.get("predicate") or "")
            in changed_fields[str(fact.get("subject") or "")]
        )
    )
    projected = replace(
        topic,
        entities=tuple(entities),
        facts=facts,
        provenance={
            **dict(topic.provenance),
            "planning_projection_schema": "rpg_world_forge_plan_projection_v1",
            "planning_projected_entity_ids": sorted(changed_fields),
        },
    )
    return compile_structured_entity_facts(node, projected, dependency_topics)


class PlanningConstrainedWorldForgeGenerator:
    """Decorator that makes anchor and planning assignments publication-authoritative."""

    def __init__(self, delegate: WorldForgeTopicGenerator) -> None:
        self.delegate = delegate

    def generate(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: Mapping[str, Any],
        dependency_topics: Mapping[str, GeneratedTopic],
    ) -> GeneratedTopic:
        topic = self.delegate.generate(
            node,
            seed=seed,
            campaign_context=campaign_context,
            dependency_topics=dependency_topics,
        )
        return project_planning_into_topic(
            node,
            topic,
            campaign_context=campaign_context,
            dependency_topics=dependency_topics,
        )


__all__ = [
    "PlanningConstrainedWorldForgeGenerator",
    "project_planning_into_topic",
]
