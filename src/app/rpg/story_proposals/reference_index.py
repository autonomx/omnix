from __future__ import annotations

from typing import Any, Dict, Set


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _keys(value: Any) -> Set[str]:
    return {str(key) for key in _safe_dict(value).keys() if str(key)}


def build_story_reference_index(
    simulation_state: Dict[str, Any],
    proposal: Dict[str, Any],
) -> Dict[str, Set[str]]:
    lore_ids = _keys(_safe_dict(simulation_state.get("lore_state")).get("entries"))
    arc_ids = _keys(_safe_dict(simulation_state.get("story_arc_state")).get("arcs"))
    quest_ids = _keys(_safe_dict(simulation_state.get("quest_state")).get("quests"))
    puzzle_ids = _keys(_safe_dict(simulation_state.get("puzzle_state")).get("puzzles"))

    for entry in proposal.get("lore_entries") or []:
        if isinstance(entry, dict) and entry.get("lore_id"):
            lore_ids.add(str(entry["lore_id"]))
    for arc in proposal.get("story_arcs") or []:
        if isinstance(arc, dict) and arc.get("arc_id"):
            arc_ids.add(str(arc["arc_id"]))

    # Conservative location/entity discovery from existing spatial graph.
    spatial_graph = _safe_dict(simulation_state.get("spatial_graph"))
    area_ids = _keys(spatial_graph.get("areas"))
    entity_ids = _keys(spatial_graph.get("entities"))

    # Manual scenarios and older fixtures sometimes use these shapes.
    entity_locations = _safe_dict(spatial_graph.get("entity_locations"))
    entity_ids.update(str(key) for key in entity_locations.keys() if str(key))
    area_ids.update(str(value) for value in entity_locations.values() if str(value))

    return {
        "lore_ids": lore_ids,
        "arc_ids": arc_ids,
        "quest_ids": quest_ids,
        "puzzle_ids": puzzle_ids,
        "location_ids": area_ids,
        "entity_ids": entity_ids,
    }