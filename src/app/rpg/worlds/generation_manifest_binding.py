"""Bind generated entities to planner-owned canonical manifest slots."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Sequence

from app.rpg.session.genesis.world_forge_generation import GeneratedTopic


class EntityManifestBindingError(ValueError):
    """Raised when provider output cannot be mapped one-to-one to manifest slots."""


def _slots(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(dict(row) for row in value if isinstance(row, Mapping))


def _rewrite(value: Any, replacements: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return replacements.get(value, value)
    if isinstance(value, Mapping):
        return {str(key): _rewrite(item, replacements) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_rewrite(item, replacements) for item in value)
    if isinstance(value, list):
        return [_rewrite(item, replacements) for item in value]
    return value


def _ordered_entities(
    entities: tuple[Mapping[str, Any], ...],
    slots: tuple[dict[str, Any], ...],
    *,
    topic_id: str,
) -> tuple[tuple[dict[str, Any], ...], str]:
    if len(entities) != len(slots):
        raise EntityManifestBindingError(
            "world_generation_manifest_cardinality_mismatch:"
            f"{topic_id}:expected={len(slots)}:actual={len(entities)}"
        )
    rows = tuple(dict(row) for row in entities)
    expected_slot_ids = {str(row.get("slot_id") or "") for row in slots}
    supplied_slot_ids = [
        str(row.get("manifest_slot_id") or row.get("slot_id") or "")
        for row in rows
    ]
    if all(supplied_slot_ids):
        if len(set(supplied_slot_ids)) != len(supplied_slot_ids):
            raise EntityManifestBindingError(
                f"world_generation_manifest_duplicate_slot_binding:{topic_id}"
            )
        if set(supplied_slot_ids) != expected_slot_ids:
            raise EntityManifestBindingError(
                f"world_generation_manifest_slot_set_mismatch:{topic_id}"
            )
        by_slot = dict(zip(supplied_slot_ids, rows, strict=True))
        return tuple(by_slot[str(slot["slot_id"])] for slot in slots), "slot_id"

    expected_entity_ids = {str(row.get("entity_id") or "") for row in slots}
    supplied_entity_ids = [str(row.get("id") or "") for row in rows]
    if all(supplied_entity_ids) and set(supplied_entity_ids) == expected_entity_ids:
        if len(set(supplied_entity_ids)) != len(supplied_entity_ids):
            raise EntityManifestBindingError(
                f"world_generation_manifest_duplicate_entity_binding:{topic_id}"
            )
        by_id = dict(zip(supplied_entity_ids, rows, strict=True))
        return tuple(by_id[str(slot["entity_id"])] for slot in slots), "entity_id"
    return rows, "ordinal"


def bind_generated_topic_to_manifest(
    topic: GeneratedTopic,
    manifest_slots: Sequence[Mapping[str, Any]] | None,
    *,
    manifest_hash: str = "",
) -> GeneratedTopic:
    """Inject canonical IDs and rewrite exact provider references deterministically."""

    slots = _slots(manifest_slots)
    if not slots:
        return topic
    for slot in slots:
        if str(slot.get("topic_id") or "") != topic.topic_id:
            raise EntityManifestBindingError(
                "world_generation_manifest_topic_mismatch:"
                f"{slot.get('topic_id')}:{topic.topic_id}"
            )
        if not str(slot.get("slot_id") or "") or not str(slot.get("entity_id") or ""):
            raise EntityManifestBindingError(
                f"world_generation_manifest_slot_incomplete:{topic.topic_id}"
            )

    ordered, binding_mode = _ordered_entities(topic.entities, slots, topic_id=topic.topic_id)
    old_ids = [str(row.get("id") or "") for row in ordered]
    duplicates = sorted({value for value in old_ids if value and old_ids.count(value) > 1})
    if duplicates:
        raise EntityManifestBindingError(
            "world_generation_provider_entity_id_duplicate:"
            f"{topic.topic_id}:" + ",".join(duplicates)
        )

    replacements = {
        old_id: str(slot["entity_id"])
        for old_id, slot in zip(old_ids, slots, strict=True)
        if old_id and old_id != str(slot["entity_id"])
    }
    bound_entities = []
    for row, slot in zip(ordered, slots, strict=True):
        rewritten = dict(_rewrite(row, replacements))
        rewritten["id"] = str(slot["entity_id"])
        rewritten["manifest_slot_id"] = str(slot["slot_id"])
        bound_entities.append(rewritten)

    payload = topic.as_dict()
    payload["entities"] = bound_entities
    for field in (
        "documents",
        "facts",
        "relationships",
        "knowledge_rules",
        "story_threads",
    ):
        payload[field] = _rewrite(payload[field], replacements)
    provenance = dict(payload.get("provenance") or {})
    provenance["entity_manifest_binding"] = {
        "schema_version": "rpg_world_entity_manifest_binding_v1",
        "manifest_hash": manifest_hash,
        "binding_mode": binding_mode,
        "slot_count": len(slots),
        "slot_ids": [str(slot["slot_id"]) for slot in slots],
        "entity_ids": [str(slot["entity_id"]) for slot in slots],
        "rewritten_provider_ids": dict(sorted(replacements.items())),
    }
    payload["provenance"] = provenance
    return GeneratedTopic.from_dict(payload)


def manifest_slots_from_node(node_metadata: Mapping[str, Any] | None) -> tuple[dict[str, Any], ...]:
    metadata = dict(node_metadata or {})
    return _slots(metadata.get("entity_manifest_slots"))


__all__ = [
    "EntityManifestBindingError",
    "bind_generated_topic_to_manifest",
    "manifest_slots_from_node",
]
