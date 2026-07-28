"""Shared canonical derivation for Release 6 starter-bubble certification."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .starter_bubble import StarterBubblePlan, build_starter_bubble


def mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def rows(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(dict(row) for row in value if isinstance(row, Mapping))


def candidate(row: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("candidate", "content"):
        if isinstance(row.get(key), Mapping):
            return dict(row[key])
    return dict(row)


def entities(
    topic_rows: Sequence[Mapping[str, Any]],
) -> tuple[tuple[str, int, dict[str, Any]], ...]:
    values: list[tuple[str, int, dict[str, Any]]] = []
    for topic_index, raw in enumerate(topic_rows, 1):
        topic = mapping(raw)
        value = candidate(topic)
        topic_id = str(topic.get("topic_id") or value.get("topic_id") or f"topic:{topic_index}")
        values.extend((topic_id, index, row) for index, row in enumerate(rows(value.get("entities"))))
    return tuple(values)


def normalise(value: Any) -> str:
    rendered = str(value or "").strip().casefold()
    if ":" in rendered:
        rendered = rendered.split(":", 1)[-1]
    return "_".join(
        "".join(character if character.isalnum() else " " for character in rendered).split()
    )


def starter_bubble_contract_enabled(topic_graph: Mapping[str, Any] | None) -> bool:
    graph = mapping(topic_graph)
    contract = mapping(mapping(graph.get("metadata")).get("starter_bubble_contract"))
    if contract.get("required") or contract.get("domain_ids"):
        return True
    actor_vendor = False
    place_routes = False
    for node in rows(graph.get("nodes")):
        field_ids = {
            str(row.get("field_id") or "")
            for row in rows(mapping(node.get("metadata")).get("field_definitions"))
        }
        actor_vendor = actor_vendor or "vendor_inventory_item_ids" in field_ids
        place_routes = place_routes or "connected_place_ids" in field_ids
    return actor_vendor and place_routes


def canonical_places(
    topic_rows: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("id") or ""): row
        for topic_id, _index, row in entities(topic_rows)
        if topic_id == "places" and str(row.get("id") or "")
    }


def resolve_starting_place(
    places: Mapping[str, Mapping[str, Any]],
    topic_graph: Mapping[str, Any] | None,
) -> str:
    requested = normalise(mapping(mapping(topic_graph).get("metadata")).get("starting_location"))
    if not requested:
        return sorted(places)[0] if places else ""
    matches = [
        place_id
        for place_id, place in sorted(places.items())
        if requested in {normalise(place_id), normalise(place.get("name"))}
    ]
    return matches[0] if len(matches) == 1 else ""


def resolve_neighboring_place(
    starting_place_id: str,
    places: Mapping[str, Mapping[str, Any]],
) -> str:
    starting = mapping(places.get(starting_place_id))
    raw = starting.get("connected_place_ids")
    candidates = (
        sorted({str(value).strip() for value in raw if str(value).strip()})
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes))
        else []
    )
    return next(
        (
            value for value in candidates
            if value in places and value != starting_place_id
        ),
        "",
    )


def derive_starter_bubble(
    topic_rows: Sequence[Mapping[str, Any]],
    topic_graph: Mapping[str, Any] | None,
) -> dict[str, Any]:
    enabled = starter_bubble_contract_enabled(topic_graph)
    places = canonical_places(topic_rows)
    start = resolve_starting_place(places, topic_graph) if enabled else ""
    neighbor = resolve_neighboring_place(start, places) if start else ""
    metadata = mapping(mapping(topic_graph).get("metadata"))
    plan: StarterBubblePlan | None = None
    if enabled and start and neighbor:
        plan = build_starter_bubble(
            world_id=str(metadata.get("world_id") or "world:generated"),
            source_world_revision=max(1, int(metadata.get("world_revision") or 1)),
            starting_location_id=start,
            neighboring_location_id=neighbor,
        )
    return {
        "contract_enabled": enabled,
        "place_ids": tuple(sorted(places)),
        "starting_place_id": start,
        "neighboring_place_id": neighbor,
        "plan": plan,
    }


__all__ = [
    "canonical_places",
    "derive_starter_bubble",
    "entities",
    "mapping",
    "normalise",
    "resolve_neighboring_place",
    "resolve_starting_place",
    "rows",
    "starter_bubble_contract_enabled",
]
