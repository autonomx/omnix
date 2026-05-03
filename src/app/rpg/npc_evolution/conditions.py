from __future__ import annotations

from typing import Any, Dict

from app.rpg.memory.causal_retrieval import retrieve_causal_memories
from app.rpg.npc_evolution.state import get_npc_evolution
from app.rpg.social.reputation import get_relationship
from app.rpg.story_arcs.state import get_story_arc


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def evaluate_npc_evolution_condition(
    simulation_state: Dict[str, Any],
    condition: Dict[str, Any],
) -> Dict[str, Any]:
    condition = _safe_dict(condition)
    condition_type = str(condition.get("type") or "")
    npc_id = str(condition.get("npc_id") or "")

    if condition_type == "npc_arc_active":
        arc_id = str(condition.get("arc_id") or "")
        evolution = get_npc_evolution(simulation_state, npc_id)
        active = list((evolution or {}).get("active_arcs") or [])
        return {
            "ok": arc_id in active,
            "type": condition_type,
            "npc_id": npc_id,
            "arc_id": arc_id,
            "actual_active_arcs": active,
            "reason": "npc_arc_active" if arc_id in active else "npc_arc_not_active",
        }

    if condition_type == "npc_arc_completed":
        arc_id = str(condition.get("arc_id") or "")
        evolution = get_npc_evolution(simulation_state, npc_id)
        completed = list((evolution or {}).get("completed_arcs") or [])
        return {
            "ok": arc_id in completed,
            "type": condition_type,
            "npc_id": npc_id,
            "arc_id": arc_id,
            "actual_completed_arcs": completed,
            "reason": "npc_arc_completed" if arc_id in completed else "npc_arc_not_completed",
        }

    if condition_type == "npc_flag":
        flag = str(condition.get("flag") or "")
        expected = condition.get("expected", True)
        evolution = get_npc_evolution(simulation_state, npc_id)
        flags = _safe_dict((evolution or {}).get("flags"))
        actual = flags.get(flag)
        return {
            "ok": actual == expected,
            "type": condition_type,
            "npc_id": npc_id,
            "flag": flag,
            "expected": expected,
            "actual": actual,
            "available_flags": sorted(str(key) for key in flags.keys()),
            "reason": "flag_matches" if actual == expected else "flag_mismatch",
        }

    if condition_type == "relationship_at_least":
        field = str(condition.get("field") or "")
        minimum = int(condition.get("minimum") or 0)
        relationship = get_relationship(simulation_state, npc_id)
        actual = int(relationship.get(field) or 0)
        return {
            "ok": actual >= minimum,
            "type": condition_type,
            "npc_id": npc_id,
            "field": field,
            "minimum": minimum,
            "actual": actual,
            "reason": "relationship_sufficient" if actual >= minimum else "relationship_too_low",
        }

    if condition_type == "relationship_below":
        field = str(condition.get("field") or "")
        maximum = int(condition.get("maximum") or 0)
        relationship = get_relationship(simulation_state, npc_id)
        actual = int(relationship.get(field) or 0)
        return {
            "ok": actual < maximum,
            "type": condition_type,
            "npc_id": npc_id,
            "field": field,
            "maximum": maximum,
            "actual": actual,
            "reason": "relationship_below" if actual < maximum else "relationship_too_high",
        }

    if condition_type == "story_arc_stage":
        arc_id = str(condition.get("arc_id") or "")
        expected = str(condition.get("stage") or "")
        arc = get_story_arc(simulation_state, arc_id)
        actual = str((arc or {}).get("stage") or "")
        return {
            "ok": actual == expected,
            "type": condition_type,
            "npc_id": npc_id,
            "arc_id": arc_id,
            "expected": expected,
            "actual": actual,
            "reason": "stage_matches" if actual == expected else "stage_mismatch",
        }

    if condition_type == "npc_knows_memory":
        event_id = str(condition.get("event_id") or "")
        rows = retrieve_causal_memories(
            simulation_state,
            npc_id,
            tags=condition.get("tags") or [],
            max_items=20,
        )
        event_ids = [row.get("event_id") for row in rows]
        return {
            "ok": event_id in event_ids,
            "type": condition_type,
            "npc_id": npc_id,
            "event_id": event_id,
            "actual_event_ids": event_ids,
            "reason": "memory_known" if event_id in event_ids else "memory_missing",
        }

    return {
        "ok": False,
        "type": condition_type,
        "npc_id": npc_id,
        "reason": f"unknown_npc_evolution_condition_type:{condition_type}",
    }


def evaluate_all_npc_evolution_conditions(
    simulation_state: Dict[str, Any],
    conditions: list[Dict[str, Any]],
) -> Dict[str, Any]:
    results = [
        evaluate_npc_evolution_condition(simulation_state, condition)
        for condition in conditions
    ]
    ok = all(row.get("ok") for row in results)
    return {
        "ok": ok,
        "results": results,
        "failed": [row for row in results if not row.get("ok")],
    }