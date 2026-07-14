"""Compile explicit and dossier-derived cross-domain canon relationships."""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from .world_forge_generation import GeneratedTopic


def _slug(value: str) -> str:
    return "_".join("".join(ch.casefold() if ch.isalnum() else " " for ch in value).split())


def _relationship(
    source_id: str,
    target_id: str,
    kind: str,
    *,
    visibility: str = "game_master_canon",
    content: str = "",
    source: str = "relationship_compiler",
) -> dict[str, Any]:
    return {
        "id": f"relationship:{_slug(source_id)}:{_slug(kind)}:{_slug(target_id)}",
        "source_id": source_id,
        "target_id": target_id,
        "kind": kind,
        "content": content or f"{source_id} {kind.replace('_', ' ')} {target_id}.",
        "authority": "generated_proposal",
        "approved_authority": "objective_canon",
        "visibility": visibility,
        "entity_refs": [source_id, target_id],
        "compiled_by": source,
    }


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple | set):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def compile_cross_domain_relationships(
    topics: Iterable[GeneratedTopic],
) -> tuple[dict[str, Any], ...]:
    """Derive relationship records from structured entity dossier fields."""

    explicit: list[dict[str, Any]] = []
    entities: dict[str, Mapping[str, Any]] = {}
    for topic in topics:
        explicit.extend(dict(row) for row in topic.relationships)
        for row in topic.entities:
            entity_id = str(row.get("id") or "").strip()
            if entity_id:
                entities[entity_id] = row

    derived: list[dict[str, Any]] = []
    for entity_id, row in entities.items():
        pairs = (
            ("realm_id", "within_realm"),
            ("region_id", "located_in"),
            ("location_id", "present_at"),
            ("institution_id", "affiliated_with"),
            ("parent_id", "part_of"),
        )
        for field, kind in pairs:
            target_id = str(row.get(field) or "").strip()
            if target_id:
                derived.append(_relationship(entity_id, target_id, kind))
        for field, kind in (
            ("faction_ids", "member_of"),
            ("opposes", "opposes"),
            ("allies", "allied_with"),
            ("recruits_from", "recruits_from"),
            ("worships", "worships"),
            ("controls", "controls"),
            ("knows", "knows"),
        ):
            for target_id in _strings(row.get(field)):
                derived.append(_relationship(entity_id, target_id, kind))
        for route in row.get("travel_routes") or () if isinstance(row.get("travel_routes"), list | tuple) else ():
            if not isinstance(route, Mapping):
                continue
            target_id = str(route.get("target_id") or route.get("to") or "").strip()
            if target_id:
                derived.append(
                    _relationship(
                        entity_id,
                        target_id,
                        "travel_route",
                        visibility=str(route.get("visibility") or "public"),
                        content=str(route.get("description") or "") or f"A travel route links {entity_id} and {target_id}.",
                    )
                )

    unique: dict[str, dict[str, Any]] = {}
    for row in [*explicit, *derived]:
        relationship_id = str(row.get("id") or "").strip()
        if relationship_id:
            unique.setdefault(relationship_id, row)
    return tuple(unique[key] for key in sorted(unique))
