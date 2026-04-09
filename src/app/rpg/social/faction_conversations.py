from __future__ import annotations

from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def build_faction_topic_candidates(simulation_state: Dict[str, Any], faction_id: str) -> List[Dict[str, Any]]:
    """Generate conversation topic candidates from faction state.

    Produces topics based on faction pressure, alliances, and recent events.
    Higher-pressure factions generate more urgent topics.
    """
    simulation_state = _safe_dict(simulation_state)
    factions = _safe_dict(simulation_state.get("factions"))
    faction = _safe_dict(factions.get(faction_id))
    faction_id = _safe_str(faction_id)
    pressure = int(faction.get("pressure", 0) or 0)
    faction_name = _safe_str(faction.get("name")) or faction_id

    topics: List[Dict[str, Any]] = []

    # Always generate a base "faction internal discussion" topic
    topics.append({
        "type": "faction_tension",
        "anchor": f"faction:{faction_id}",
        "summary": f"{faction_name} members debate their next move.",
        "stance": "plan",
        "priority": 0.80,
    })

    # High-pressure factions generate urgency topics
    if pressure >= 3:
        topics.append({
            "type": "faction_tension",
            "anchor": f"faction:{faction_id}:urgency",
            "summary": f"{faction_name} grows restless under mounting pressure.",
            "stance": "urgent",
            "priority": 0.90,
        })

    # Check for rival factions at the same locations
    social_state = _safe_dict(simulation_state.get("social_state"))
    alliances = _safe_dict(social_state.get("alliances"))
    rivals = _safe_list(alliances.get(f"rivals:{faction_id}"))
    for rival_id in rivals[:2]:
        rival_id = _safe_str(rival_id)
        if rival_id:
            rival_name = _safe_str(_safe_dict(factions.get(rival_id)).get("name")) or rival_id
            topics.append({
                "type": "faction_tension",
                "anchor": f"faction:{faction_id}:rival:{rival_id}",
                "summary": f"{faction_name} members discuss their rivalry with {rival_name}.",
                "stance": "hostile",
                "priority": 0.85,
            })

    return topics[:4]
