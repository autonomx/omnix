from __future__ import annotations

from typing import Any, Dict

from app.rpg.memory.causal_retrieval import retrieve_causal_memories
from app.rpg.quests.state import get_quest
from app.rpg.social.reputation import get_relationship
from app.rpg.spatial.graph import get_entity_area


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _inventory_has_item(simulation_state: Dict[str, Any], item_id: str) -> bool:
    inventory = _safe_dict(simulation_state.get("inventory"))
    items = inventory.get("items")
    if isinstance(items, dict):
        return item_id in items and bool(items[item_id])
    if isinstance(items, list):
        for row in items:
            if isinstance(row, dict) and row.get("item_id") == item_id:
                return True
            if row == item_id:
                return True
    # Manual/test convenience path.
    manual_items = simulation_state.get("manual_inventory_items")
    if isinstance(manual_items, list):
        return item_id in manual_items
    return False


def evaluate_quest_condition(
    simulation_state: Dict[str, Any],
    condition: Dict[str, Any],
) -> Dict[str, Any]:
    condition = _safe_dict(condition)
    condition_type = str(condition.get("type") or "")

    if condition_type == "always":
        return {"ok": True, "type": condition_type, "reason": "always"}

    if condition_type == "has_item":
        item_id = str(condition.get("item_id") or "")
        ok = _inventory_has_item(simulation_state, item_id)
        return {
            "ok": ok,
            "type": condition_type,
            "item_id": item_id,
            "reason": "item_present" if ok else "item_missing",
        }

    if condition_type == "social_trust_at_least":
        npc_id = str(condition.get("npc_id") or "")
        minimum = int(condition.get("minimum") or 0)
        relationship = get_relationship(simulation_state, npc_id)
        actual = int(relationship.get("trust") or 0)
        return {
            "ok": actual >= minimum,
            "type": condition_type,
            "npc_id": npc_id,
            "minimum": minimum,
            "actual": actual,
            "reason": "trust_sufficient" if actual >= minimum else "trust_too_low",
        }

    if condition_type == "npc_knows_memory":
        npc_id = str(condition.get("npc_id") or "")
        event_id = str(condition.get("event_id") or "")
        rows = retrieve_causal_memories(
            simulation_state,
            npc_id,
            actor_id=condition.get("actor_id"),
            target_id=condition.get("target_id"),
            tags=condition.get("tags") or [],
            max_items=20,
        )
        ok = any(row.get("event_id") == event_id for row in rows)
        return {
            "ok": ok,
            "type": condition_type,
            "npc_id": npc_id,
            "event_id": event_id,
            "actual_event_ids": [row.get("event_id") for row in rows],
            "reason": "memory_known" if ok else "memory_missing",
        }

    if condition_type == "entity_in_area":
        graph = _safe_dict(simulation_state.get("spatial_graph"))
        entity_id = str(condition.get("entity_id") or "player")
        area_id = str(condition.get("area_id") or "")
        actual = get_entity_area(graph, entity_id)
        return {
            "ok": actual == area_id,
            "type": condition_type,
            "entity_id": entity_id,
            "area_id": area_id,
            "actual_area_id": actual,
            "reason": "entity_in_area" if actual == area_id else "entity_elsewhere",
        }

    if condition_type == "quest_stage":
        quest_id = str(condition.get("quest_id") or "")
        expected_stage = str(condition.get("stage") or "")
        quest = get_quest(simulation_state, quest_id)
        actual_stage = str((quest or {}).get("stage") or "")
        return {
            "ok": actual_stage == expected_stage,
            "type": condition_type,
            "quest_id": quest_id,
            "stage": expected_stage,
            "actual_stage": actual_stage,
            "reason": "stage_matches" if actual_stage == expected_stage else "stage_mismatch",
        }

    if condition_type == "puzzle_flag":
        puzzle_id = str(condition.get("puzzle_id") or "")
        flag = str(condition.get("flag") or "")
        expected = condition.get("expected", True)
        puzzle_state = _safe_dict(simulation_state.get("puzzle_state"))
        puzzles = _safe_dict(puzzle_state.get("puzzles"))
        puzzle = _safe_dict(puzzles.get(puzzle_id))
        flags = _safe_dict(puzzle.get("flags"))
        actual = flags.get(flag)
        return {
            "ok": actual == expected,
            "type": condition_type,
            "puzzle_id": puzzle_id,
            "flag": flag,
            "expected": expected,
            "actual": actual,
            "puzzle_state_exists": bool(puzzle_state),
            "puzzle_exists": bool(puzzle),
            "available_puzzle_ids": sorted(str(key) for key in puzzles.keys()),
            "available_flags": sorted(str(key) for key in flags.keys()),
            "reason": "flag_matches" if actual == expected else "flag_mismatch",
        }

    return {
        "ok": False,
        "type": condition_type,
        "reason": f"unknown_condition_type:{condition_type}",
    }


def evaluate_all_quest_conditions(
    simulation_state: Dict[str, Any],
    conditions: list[Dict[str, Any]],
) -> Dict[str, Any]:
    results = [
        evaluate_quest_condition(simulation_state, condition)
        for condition in conditions
    ]
    ok = all(row.get("ok") for row in results)
    return {
        "ok": ok,
        "results": results,
        "failed": [row for row in results if not row.get("ok")],
    }