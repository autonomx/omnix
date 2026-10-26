"""A world written as lore plays from its lore (RQ-2.0; roadmap §4.4).

A world compiled from lore topics (Vesper-9) keeps its people, places, regions and threats as the canon's entities,
not as the sections a launch reads (``characters``, ``regions``, ``bestiary``), and its topology lists its places by
id alone, with no roads between them. Launch reads the authored section where the world has one, and otherwise
these: each section taken from the entities of its kinds, each place from its entity, and, where the world names no
roads, roads derived from its regions (every place reaches the others of its region, and the regions are joined in
the order the world lists them, through their first places). A world whose roads leave a place unreached has that
place joined to them (``joined_routes``). Pure: it reads the canon and returns rows.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

_KINDS = {
    "characters": frozenset({"npc", "actor", "person", "character"}),
    "regions": frozenset({"region"}),
    "bestiary": frozenset({"creature", "monster", "beast", "threat"}),
    "items": frozenset({"item", "equipment", "gear", "weapon", "armor", "armour", "consumable", "augmentation"}),
    "quests": frozenset({"quest"}),
}
_PLACE_KINDS = frozenset({"location", "place", "settlement", "site"})
DERIVED_TRAVEL_TIME = "30 minutes"
DERIVED_JOURNEY_TIME = "3 hours"  # a road the launch adds between two regions


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _texts(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return [_text(item) for item in value or () if _text(item)]


def _entities(canon: Mapping[str, Any]) -> list[dict[str, Any]]:
    entities = canon.get("entities")
    rows = entities.values() if isinstance(entities, Mapping) else entities or ()
    return [dict(row) for row in rows if isinstance(row, Mapping) and _text(row.get("id"))]


def _of_kind(kind: str, kinds: frozenset[str]) -> bool:
    kind = kind.casefold()
    return kind in kinds or any(kind.endswith(f"_{suffix}") for suffix in kinds)


def _role(entity: Mapping[str, Any]) -> str:
    """What someone does, in a few words: their role as written, else the start of their summary."""
    written = _text(entity.get("role") or entity.get("occupation"))
    if written:
        return written
    summary = _text(entity.get("short_summary") or entity.get("description"))
    head = summary.split(".")[0].split(",")[0]
    for article in ("A ", "An ", "The "):
        head = head.removeprefix(article)
    return " ".join(head.split()[:6])


def _character(entity: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _text(entity.get("id")), "name": _text(entity.get("name")), "role": _role(entity),
        "biography": _text(entity.get("description") or entity.get("short_summary")),
        "location_id": _text(entity.get("location_id")), "speech_style": _text(entity.get("speech_style")),
        "goals": _texts(entity.get("goals") or entity.get("goal")),
        "secrets": _texts(entity.get("secrets") or entity.get("hidden_truth")),
        "personality": _texts(entity.get("personality")),
    }


def _region(entity: Mapping[str, Any]) -> dict[str, Any]:
    return {"id": _text(entity.get("id")), "name": _text(entity.get("name")),
            "summary": _text(entity.get("short_summary") or entity.get("description"))}


def _creature(entity: Mapping[str, Any]) -> dict[str, Any]:
    return {"id": _text(entity.get("id")), "name": _text(entity.get("name")),
            "threat": _text(entity.get("threat_level") or entity.get("threat")) or "medium",
            "traits": _texts(entity.get("traits") or entity.get("capabilities")),
            "weakness": ", ".join(_texts(entity.get("weaknesses") or entity.get("weakness")))}


def _item(entity: Mapping[str, Any]) -> dict[str, Any]:
    return {"id": _text(entity.get("id")), "name": _text(entity.get("name")),
            "type": _text(entity.get("item_type") or entity.get("category") or entity.get("kind")),
            "rarity": _text(entity.get("rarity")),
            "effect": _text(entity.get("effect") or entity.get("short_summary") or entity.get("description"))}


def _quest(entity: Mapping[str, Any]) -> dict[str, Any]:
    return {"id": _text(entity.get("id")), "name": _text(entity.get("name") or entity.get("title")),
            "summary": _text(entity.get("short_summary") or entity.get("description"))}


_SHAPES = {"characters": _character, "regions": _region, "bestiary": _creature, "items": _item, "quests": _quest}


def lore_rows(canon: Mapping[str, Any], section: str) -> list[dict[str, Any]]:
    """The world's ``section`` (``characters``, ``regions``, ``bestiary``, ``items`` or ``quests``): as authored,
    else from its lore."""
    authored = [dict(row) for row in canon.get(section) or () if isinstance(row, Mapping)]
    if authored:
        return authored
    return [_SHAPES[section](entity) for entity in _entities(canon) if _of_kind(_text(entity.get("kind")), _KINDS[section])]


def lore_location_rows(canon: Mapping[str, Any], topology: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The world's places as rows: the topology's (a bare id filled in from its entity), else its place entities."""
    places = {_text(entity.get("id")): entity for entity in _entities(canon)
              if _of_kind(_text(entity.get("kind")), _PLACE_KINDS)}
    listed = list(_mapping(topology).get("locations") or ()) or list(places)
    rows: list[dict[str, Any]] = []
    for row in listed:
        row = dict(row) if isinstance(row, Mapping) else {"id": _text(row)}
        entity = places.get(_text(row.get("id")), {})
        filled = {key: value for key, value in {
            "name": _text(entity.get("name")), "region_id": _text(entity.get("region_id")),
            "description": _text(entity.get("description") or entity.get("short_summary")),
        }.items() if value and not _text(row.get(key))}
        if _text(row.get("id")):
            rows.append({**row, **filled})
    return rows


def lore_routes(locations: Iterable[Mapping[str, Any]], regions: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Roads for a world that names none: within a region every place reaches the others, and the regions are joined
    in the order the world lists them, through their first places."""
    by_region: dict[str, list[str]] = {}
    for row in locations:
        by_region.setdefault(_text(row.get("region_id")), []).append(_text(row.get("id")))
    routes: list[dict[str, Any]] = []
    for region, places in by_region.items():
        for index, origin in enumerate(places):
            for target in places[index + 1:]:
                routes.append({"id": f"route:lore:{origin}:{target}", "from": origin, "to": target,
                               "travel_time": DERIVED_TRAVEL_TIME})
    order = [_text(row.get("id")) for row in regions if _text(row.get("id")) in by_region]
    order += [region for region in by_region if region not in order]
    hubs = [by_region[region][0] for region in order if by_region[region]]
    for origin, target in zip(hubs, hubs[1:]):
        routes.append({"id": f"route:lore:{origin}:{target}", "from": origin, "to": target,
                       "travel_time": DERIVED_TRAVEL_TIME})
    return routes


def joined_routes(routes: Iterable[Mapping[str, Any]], locations: Iterable[Mapping[str, Any]],
                  regions: Iterable[Mapping[str, Any]], *, start: str = "") -> list[dict[str, Any]]:
    """The world's roads, and one more to each place they leave unreached from ``start`` (by default its first place):
    from a reached place of its own region, else of the nearest region in the order the world lists them, that
    region's capital when reached (a road leaves a town, not the wilds by it), else its first reached place (the
    playtest: Aurelia's four roads never reached Valecourt or the Hollow Meridian, where two of its quests, the finale
    one, are done)."""
    routes = [dict(route) for route in routes]
    rows = [row for row in locations if _text(row.get("id"))]
    region_of = {_text(row.get("id")): _text(row.get("region_id")) for row in rows}
    regions = list(regions)
    capitals = {_text(row.get("id")): _text(row.get("capital")) for row in regions}
    order = [_text(row.get("id")) for row in regions]
    order += [region for region in dict.fromkeys(region_of.values()) if region not in order]
    neighbours: dict[str, set[str]] = {place: set() for place in region_of}
    for route in routes:
        origin, target = _text(route.get("from")), _text(route.get("to"))
        if origin in neighbours and target in neighbours:
            neighbours[origin].add(target)
            neighbours[target].add(origin)

    def reach(first: str) -> list[str]:
        seen, queue = [first], [first]
        while queue:
            for place in sorted(neighbours[queue.pop(0)]):
                if place not in seen:
                    seen.append(place)
                    queue.append(place)
        return seen

    first = start if start in region_of else next(iter(region_of), "")
    reached = reach(first) if first else []
    for place in region_of:
        if place in reached:
            continue
        own = [known for known in reached if region_of[known] == region_of[place]]
        if own:
            region, time = region_of[place], DERIVED_TRAVEL_TIME
        else:
            index = order.index(region_of[place])
            region = region_of[min(reached, key=lambda known: (abs(order.index(region_of[known]) - index),
                                                                reached.index(known)))]
            time = DERIVED_JOURNEY_TIME
        candidates = [known for known in reached if region_of[known] == region]
        origin = capitals.get(region) if capitals.get(region) in candidates else candidates[0]
        routes.append({"id": f"route:joined:{origin}:{place}", "from": origin, "to": place, "travel_time": time})
        neighbours[origin].add(place)
        neighbours[place].add(origin)
        reached += [found for found in reach(place) if found not in reached]
    return routes


__all__ = ["DERIVED_JOURNEY_TIME", "DERIVED_TRAVEL_TIME", "joined_routes", "lore_location_rows", "lore_routes",
           "lore_rows"]
