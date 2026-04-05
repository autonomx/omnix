"""Phase 7 — Creator / GM Debug Tools.

Collect compact inspector/debug views from simulation state
and provide explainability surfaces.

Rules:
- Avoid putting this logic inside routes
- Bounded outputs for debug payloads
- Deterministic ordering everywhere
"""

from __future__ import annotations

from typing import Any, Dict, List

_MAX_ITEMS = 12


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return list(v) if isinstance(v, list) else []


def _sorted_dict_items(d: Dict[str, Any]):
    return sorted((d or {}).items(), key=lambda item: str(item[0]))


def summarize_npc_minds(simulation_state: Dict[str, Any], limit: int = _MAX_ITEMS) -> List[Dict[str, Any]]:
    """Summarize NPC minds from the simulation state.

    Returns a bounded, deterministic list of NPC mind summaries.
    """
    simulation_state = simulation_state or {}
    npc_index = _safe_dict(simulation_state.get("npc_index"))
    npc_minds = _safe_dict(simulation_state.get("npc_minds"))

    out: List[Dict[str, Any]] = []
    for npc_id, mind in _sorted_dict_items(npc_minds):
        npc = _safe_dict(npc_index.get(npc_id))
        beliefs = _safe_dict(mind.get("beliefs"))
        goals = _safe_list(mind.get("goals"))
        memory = _safe_dict(mind.get("memory"))

        out.append({
            "npc_id": npc_id,
            "name": _safe_str(npc.get("name")) or npc_id,
            "role": _safe_str(npc.get("role")),
            "faction_id": _safe_str(npc.get("faction_id")),
            "location_id": _safe_str(npc.get("location_id")),
            "beliefs": beliefs,
            "top_goals": goals[:3],
            "memory_count": len(_safe_list(memory.get("entries"))),
            "last_decision": _safe_dict(mind.get("last_decision")),
        })

    out.sort(key=lambda item: (item["faction_id"], item["name"], item["npc_id"]))
    return out[:max(0, limit)]


def summarize_social_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize social state: alliances, rumors, group positions, reputation."""
    simulation_state = simulation_state or {}
    social_state = _safe_dict(simulation_state.get("social_state"))

    alliances = _safe_list(social_state.get("alliances"))
    rumors = _safe_list(social_state.get("rumors"))
    group_positions = _safe_dict(social_state.get("group_positions"))
    reputation = _safe_dict(social_state.get("reputation"))

    active_alliances = [
        dict(item) for item in alliances if _safe_str(item.get("status")) == "active"
    ][:_MAX_ITEMS]
    active_rumors = [
        dict(item) for item in _safe_list(simulation_state.get("active_rumors"))
    ][:_MAX_ITEMS]

    return {
        "active_alliances": active_alliances,
        "active_rumors": active_rumors,
        "group_positions": {
            key: dict(value)
            for key, value in _sorted_dict_items(group_positions)
        },
        "reputation_sources": len(reputation),
    }


def summarize_world_pressures(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize world pressures from threads, factions, and locations."""
    simulation_state = simulation_state or {}

    def _top(bucket_name: str) -> List[Dict[str, Any]]:
        bucket = _safe_dict(simulation_state.get(bucket_name))
        items = []
        for item_id, item in _sorted_dict_items(bucket):
            if not isinstance(item, dict):
                continue
            items.append({
                "id": item_id,
                "pressure": int(item.get("pressure", 0) or 0),
                "heat": int(item.get("heat", 0) or 0),
                "status": _safe_str(item.get("status")),
            })
        items.sort(key=lambda x: (-x["pressure"], -x["heat"], x["id"]))
        return items[:_MAX_ITEMS]

    return {
        "threads": _top("threads"),
        "factions": _top("factions"),
        "locations": _top("locations"),
    }


def explain_npc(simulation_state: Dict[str, Any], npc_id: str) -> Dict[str, Any]:
    """Provide an explanation of why an NPC made their last decision."""
    simulation_state = simulation_state or {}
    npc_id = _safe_str(npc_id)
    npc_index = _safe_dict(simulation_state.get("npc_index"))
    npc_minds = _safe_dict(simulation_state.get("npc_minds"))

    npc = _safe_dict(npc_index.get(npc_id))
    mind = _safe_dict(npc_minds.get(npc_id))

    memory = _safe_dict(mind.get("memory"))
    beliefs = _safe_dict(mind.get("beliefs"))
    goals = _safe_list(mind.get("goals"))
    last_decision = _safe_dict(mind.get("last_decision"))

    return {
        "npc": {
            "npc_id": npc_id,
            "name": _safe_str(npc.get("name")) or npc_id,
            "role": _safe_str(npc.get("role")),
            "faction_id": _safe_str(npc.get("faction_id")),
            "location_id": _safe_str(npc.get("location_id")),
        },
        "beliefs": beliefs,
        "goals": goals[:5],
        "recent_memories": _safe_list(memory.get("entries"))[:8],
        "last_decision": last_decision,
        "explanation": {
            "top_goal": goals[0] if goals else {},
            "decision_reason": _safe_str(last_decision.get("reason")),
            "player_beliefs": _safe_dict(beliefs.get("player")),
        },
    }


def explain_faction(simulation_state: Dict[str, Any], faction_id: str) -> Dict[str, Any]:
    """Explain a faction's current stance, members, and alliances."""
    simulation_state = simulation_state or {}
    faction_id = _safe_str(faction_id)

    npc_index = _safe_dict(simulation_state.get("npc_index"))
    npc_minds = _safe_dict(simulation_state.get("npc_minds"))
    social_state = _safe_dict(simulation_state.get("social_state"))

    members = []
    for npc_id, npc in _sorted_dict_items(npc_index):
        if _safe_str(_safe_dict(npc).get("faction_id")) != faction_id:
            continue
        mind = _safe_dict(npc_minds.get(npc_id))
        members.append({
            "npc_id": npc_id,
            "name": _safe_str(_safe_dict(npc).get("name")) or npc_id,
            "beliefs": _safe_dict(mind.get("beliefs")).get("player", {}),
            "last_decision": _safe_dict(mind.get("last_decision")),
        })

    members.sort(key=lambda item: (item["name"], item["npc_id"]))

    group_positions = _safe_dict(social_state.get("group_positions"))
    alliances = _safe_list(social_state.get("alliances"))
    faction_alliances = [
        dict(item) for item in alliances
        if faction_id in (_safe_list(item.get("member_ids")))
    ][:8]

    return {
        "faction_id": faction_id,
        "group_position": _safe_dict(group_positions.get(faction_id)),
        "members": members[:12],
        "alliances": faction_alliances,
    }


def summarize_tick_changes(before_state: Dict[str, Any], after_state: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize what changed between two simulation states."""
    before_state = before_state or {}
    after_state = after_state or {}

    before_events = _safe_list(before_state.get("events"))
    after_events = _safe_list(after_state.get("events"))
    before_consequences = _safe_list(before_state.get("consequences"))
    after_consequences = _safe_list(after_state.get("consequences"))

    new_events = after_events[len(before_events):]
    new_consequences = after_consequences[len(before_consequences):]

    return {
        "tick_before": int(before_state.get("tick", 0) or 0),
        "tick_after": int(after_state.get("tick", 0) or 0),
        "new_events": [dict(item) for item in new_events[:12] if isinstance(item, dict)],
        "new_consequences": [dict(item) for item in new_consequences[:12] if isinstance(item, dict)],
    }