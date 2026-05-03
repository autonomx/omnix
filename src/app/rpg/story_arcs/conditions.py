from __future__ import annotations

from typing import Any, Dict

from app.rpg.lore.conditions import evaluate_lore_condition
from app.rpg.memory.causal_retrieval import retrieve_causal_memories
from app.rpg.puzzles.state import get_puzzle
from app.rpg.quests.state import get_quest
from app.rpg.story_arcs.state import get_story_arc


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def evaluate_story_arc_condition(
    simulation_state: Dict[str, Any],
    condition: Dict[str, Any],
) -> Dict[str, Any]:
    condition = _safe_dict(condition)
    condition_type = str(condition.get("type") or "")
    arc_id = str(condition.get("arc_id") or "")

    if condition_type == "arc_exists":
        arc = get_story_arc(simulation_state, arc_id)
        return {
            "ok": bool(arc),
            "type": condition_type,
            "arc_id": arc_id,
            "reason": "arc_exists" if arc else "arc_missing",
        }

    if condition_type == "arc_status":
        expected = str(condition.get("status") or "")
        arc = get_story_arc(simulation_state, arc_id)
        actual = str((arc or {}).get("status") or "")
        return {
            "ok": actual == expected,
            "type": condition_type,
            "arc_id": arc_id,
            "expected": expected,
            "actual": actual,
            "reason": "status_matches" if actual == expected else "status_mismatch",
        }

    if condition_type == "arc_stage":
        expected = str(condition.get("stage") or "")
        arc = get_story_arc(simulation_state, arc_id)
        actual = str((arc or {}).get("stage") or "")
        return {
            "ok": actual == expected,
            "type": condition_type,
            "arc_id": arc_id,
            "expected": expected,
            "actual": actual,
            "reason": "stage_matches" if actual == expected else "stage_mismatch",
        }

    if condition_type == "arc_pressure_at_least":
        minimum = int(condition.get("minimum") or 0)
        arc = get_story_arc(simulation_state, arc_id)
        actual = int((arc or {}).get("pressure") or 0)
        return {
            "ok": actual >= minimum,
            "type": condition_type,
            "arc_id": arc_id,
            "minimum": minimum,
            "actual": actual,
            "reason": "pressure_sufficient" if actual >= minimum else "pressure_too_low",
        }

    if condition_type == "arc_pressure_below":
        maximum = int(condition.get("maximum") or 0)
        arc = get_story_arc(simulation_state, arc_id)
        actual = int((arc or {}).get("pressure") or 0)
        return {
            "ok": actual < maximum,
            "type": condition_type,
            "arc_id": arc_id,
            "maximum": maximum,
            "actual": actual,
            "reason": "pressure_below" if actual < maximum else "pressure_too_high",
        }

    if condition_type == "arc_flag":
        flag = str(condition.get("flag") or "")
        expected = condition.get("expected", True)
        arc = get_story_arc(simulation_state, arc_id)
        flags = _safe_dict((arc or {}).get("flags"))
        actual = flags.get(flag)
        return {
            "ok": actual == expected,
            "type": condition_type,
            "arc_id": arc_id,
            "flag": flag,
            "expected": expected,
            "actual": actual,
            "available_flags": sorted(str(key) for key in flags.keys()),
            "reason": "flag_matches" if actual == expected else "flag_mismatch",
        }

    if condition_type in {
        "lore_revealed_to_player",
        "lore_known_by",
        "lore_truth_status",
        "lore_has_tag",
        "lore_exists",
    }:
        return dict(
            evaluate_lore_condition(simulation_state, condition),
            delegated_from="story_arc_condition",
        )

    if condition_type == "quest_stage":
        quest_id = str(condition.get("quest_id") or "")
        expected = str(condition.get("stage") or "")
        quest = get_quest(simulation_state, quest_id)
        actual = str((quest or {}).get("stage") or "")
        actual_status = str((quest or {}).get("status") or "")
        quest_state = _safe_dict(simulation_state.get("quest_state"))
        quests = _safe_dict(quest_state.get("quests"))
        available_quest_ids = sorted(quests.keys())
        return {
            "ok": actual == expected,
            "type": condition_type,
            "quest_id": quest_id,
            "expected": expected,
            "actual": actual,
            "actual_status": actual_status,
            "quest_exists": bool(quest),
            "quest_state_exists": bool(quest_state),
            "available_quest_ids": available_quest_ids,
            "reason": "quest_stage_matches" if actual == expected else "quest_stage_mismatch",
        }

    if condition_type == "quest_status":
        quest_id = str(condition.get("quest_id") or "")
        expected = str(condition.get("status") or "")
        quest = get_quest(simulation_state, quest_id)
        actual = str((quest or {}).get("status") or "")
        return {
            "ok": actual == expected,
            "type": condition_type,
            "quest_id": quest_id,
            "expected": expected,
            "actual": actual,
            "reason": "quest_status_matches" if actual == expected else "quest_status_mismatch",
        }

    if condition_type == "puzzle_flag":
        puzzle_id = str(condition.get("puzzle_id") or "")
        flag = str(condition.get("flag") or "")
        expected = condition.get("expected", True)
        puzzle = get_puzzle(simulation_state, puzzle_id)
        flags = _safe_dict((puzzle or {}).get("flags"))
        actual = flags.get(flag)
        return {
            "ok": actual == expected,
            "type": condition_type,
            "puzzle_id": puzzle_id,
            "flag": flag,
            "expected": expected,
            "actual": actual,
            "available_flags": sorted(str(key) for key in flags.keys()),
            "reason": "puzzle_flag_matches" if actual == expected else "puzzle_flag_mismatch",
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
        actual_event_ids = [row.get("event_id") for row in rows]
        ok = event_id in actual_event_ids
        return {
            "ok": ok,
            "type": condition_type,
            "npc_id": npc_id,
            "event_id": event_id,
            "actual_event_ids": actual_event_ids,
            "reason": "memory_known" if ok else "memory_missing",
        }

    return {
        "ok": False,
        "type": condition_type,
        "arc_id": arc_id,
        "reason": f"unknown_story_arc_condition_type:{condition_type}",
    }


def evaluate_all_story_arc_conditions(
    simulation_state: Dict[str, Any],
    conditions: list[Dict[str, Any]],
) -> Dict[str, Any]:
    results = [
        evaluate_story_arc_condition(simulation_state, condition)
        for condition in conditions
    ]
    ok = all(row.get("ok") for row in results)
    return {
        "ok": ok,
        "results": results,
        "failed": [row for row in results if not row.get("ok")],
    }