"""Phase 11.3 — Canonical world inspector state builder.

Provides deterministic, read-only, presentation-derived world UI state
for frontend world/faction/location inspector panels.

Design invariants:
- No LLM calls
- No mutation of simulation truth
- No new persistent world state
- Bounded, derived from authoritative simulation state
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple


_MAX_FACTIONS = 12
_MAX_LOCATIONS = 16
_MAX_WORLD_THREADS = 12
_MAX_FACT_MEMBERS = 8
_MAX_LOCATION_TAGS = 8
_MAX_LOCATION_ACTORS = 8
_MAX_FACTION_RELATIONSHIPS = 8


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _safe_str(value).strip()
        if text:
            return text
    return ""


def _sorted_dict_items(value: Dict[str, Any]) -> List[Tuple[str, Any]]:
    return sorted(value.items(), key=lambda item: _safe_str(item[0]))


def _normalize_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return _safe_str(value)


def _normalize_faction_relationships(raw_relationships: Any) -> List[Dict[str, Any]]:
    relationships_dict = _safe_dict(raw_relationships)
    relationships: List[Dict[str, Any]] = []
    for target_id, payload in _sorted_dict_items(relationships_dict):
        payload_dict = _safe_dict(payload)
        score = payload_dict.get("score")
        relationships.append(
            {
                "target_id": _safe_str(target_id),
                "kind": _first_non_empty(
                    payload_dict.get("kind"),
                    payload_dict.get("type"),
                    "neutral",
                ),
                "score": score if isinstance(score, (int, float)) else None,
            }
        )

    return relationships[:_MAX_FACTION_RELATIONSHIPS]


def _normalize_faction_members(raw_members: Any) -> List[str]:
    members = []
    for raw in _safe_list(raw_members):
        text = _safe_str(raw).strip()
        if text:
            members.append(text)
    members = sorted(set(members), key=lambda v: v.lower())
    return members[:_MAX_FACT_MEMBERS]


def _normalize_location_tags(raw_tags: Any) -> List[str]:
    tags = []
    for raw in _safe_list(raw_tags):
        text = _safe_str(raw).strip()
        if text:
            tags.append(text)
    tags = sorted(set(tags), key=lambda v: v.lower())
    return tags[:_MAX_LOCATION_TAGS]


def _normalize_location_actors(raw_actors: Any) -> List[str]:
    actors = []
    for raw in _safe_list(raw_actors):
        text = _safe_str(raw).strip()
        if text:
            actors.append(text)
    actors = sorted(set(actors), key=lambda v: v.lower())
    return actors[:_MAX_LOCATION_ACTORS]


def _normalize_world_threads(raw_threads: Any) -> List[Dict[str, Any]]:
    threads = []
    for raw in _safe_list(raw_threads):
        item = _safe_dict(raw)
        thread_id = _first_non_empty(item.get("id"), item.get("thread_id"))
        if not thread_id:
            continue
        threads.append(
            {
                "id": thread_id,
                "title": _first_non_empty(item.get("title"), item.get("name"), thread_id),
                "status": _first_non_empty(item.get("status"), "open"),
                "pressure": item.get("pressure") if isinstance(item.get("pressure"), (int, float)) else None,
            }
        )

    threads = sorted(
        threads,
        key=lambda item: (
            _safe_str(item.get("title")).lower(),
            _safe_str(item.get("id")),
        ),
    )
    return threads[:_MAX_WORLD_THREADS]


def build_faction_inspector_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Build canonical faction inspector state from simulation state."""
    simulation_state = _safe_dict(simulation_state)
    faction_state = _safe_dict(simulation_state.get("faction_state"))
    factions_raw = faction_state.get("factions")

    if isinstance(factions_raw, dict):
        source_items = [
            {"id": faction_id, **_safe_dict(payload)}
            for faction_id, payload in _sorted_dict_items(factions_raw)
        ]
    else:
        source_items = _safe_list(factions_raw)

    factions: List[Dict[str, Any]] = []
    for raw in source_items:
        item = _safe_dict(raw)
        faction_id = _first_non_empty(item.get("id"), item.get("faction_id"))
        if not faction_id:
            continue

        factions.append(
            {
                "id": faction_id,
                "name": _first_non_empty(item.get("name"), item.get("title"), faction_id),
                "kind": "faction",
                "description": _safe_str(item.get("description")).strip(),
                "status": _first_non_empty(item.get("status"), "active"),
                "influence": item.get("influence") if isinstance(item.get("influence"), (int, float)) else None,
                "members": _normalize_faction_members(item.get("members")),
                "relationships": _normalize_faction_relationships(item.get("relationships")),
                "meta": {
                    "source": "faction_state",
                },
            }
        )

    factions = sorted(
        factions,
        key=lambda item: (
            _safe_str(item.get("name")).lower(),
            _safe_str(item.get("id")),
        ),
    )[:_MAX_FACTIONS]

    return {
        "factions": factions,
        "count": len(factions),
    }


def build_location_inspector_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Build canonical location inspector state from simulation state."""
    simulation_state = _safe_dict(simulation_state)
    world_state = _safe_dict(simulation_state.get("world_state"))
    locations_raw = world_state.get("locations")

    if isinstance(locations_raw, dict):
        source_items = [
            {"id": location_id, **_safe_dict(payload)}
            for location_id, payload in _sorted_dict_items(locations_raw)
        ]
    else:
        source_items = _safe_list(locations_raw)

    locations: List[Dict[str, Any]] = []
    for raw in source_items:
        item = _safe_dict(raw)
        location_id = _first_non_empty(item.get("id"), item.get("location_id"))
        if not location_id:
            continue

        locations.append(
            {
                "id": location_id,
                "name": _first_non_empty(item.get("name"), item.get("title"), location_id),
                "kind": "location",
                "description": _safe_str(item.get("description")).strip(),
                "tags": _normalize_location_tags(item.get("tags")),
                "actors": _normalize_location_actors(item.get("actors")),
                "danger_level": item.get("danger_level") if isinstance(item.get("danger_level"), (int, float)) else None,
                "meta": {
                    "source": "world_state",
                },
            }
        )

    locations = sorted(
        locations,
        key=lambda item: (
            _safe_str(item.get("name")).lower(),
            _safe_str(item.get("id")),
        ),
    )[:_MAX_LOCATIONS]

    return {
        "locations": locations,
        "count": len(locations),
    }


def build_world_inspector_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Build complete canonical world inspector state from simulation state."""
    simulation_state = _safe_dict(simulation_state)
    world_state = _safe_dict(simulation_state.get("world_state"))

    threads = _normalize_world_threads(world_state.get("threads"))

    summary = {
        "current_location": _safe_str(world_state.get("current_location")).strip(),
        "current_region": _safe_str(world_state.get("current_region")).strip(),
        "threat_level": world_state.get("threat_level") if isinstance(world_state.get("threat_level"), (int, float)) else None,
    }

    return {
        "summary": summary,
        "threads": threads,
        "thread_count": len(threads),
        "factions": build_faction_inspector_state(simulation_state),
        "locations": build_location_inspector_state(simulation_state),
    }