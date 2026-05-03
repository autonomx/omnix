from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.lore.state import get_lore_entry
from app.rpg.puzzles.state import get_puzzle
from app.rpg.quests.state import get_quest
from app.rpg.story_arcs.conditions import evaluate_story_arc_condition
from app.rpg.story_arcs.state import get_story_arc

ALLOWED_STORY_EVENT_EFFECT_TYPES = {
    "arc_pressure_delta",
    "arc_stage_set",
    "arc_flag_set",
    "lore_reveal",
    "lore_truth_status_set",
    "lore_known_by_add",
    "lore_tag_add",
    "quest_transition",
    "puzzle_transition",
    "memory_event",
    "social_delta",
    "npc_evolution",
    "world_event_emit",
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def validate_story_event_effect(
    simulation_state: Dict[str, Any],
    effect: Dict[str, Any],
) -> Dict[str, Any]:
    effect = _safe_dict(effect)
    effect_type = str(effect.get("type") or "")
    if effect_type not in ALLOWED_STORY_EVENT_EFFECT_TYPES:
        return {
            "ok": False,
            "reason": "unknown_effect_type",
            "effect_type": effect_type,
            "allowed_effect_types": sorted(ALLOWED_STORY_EVENT_EFFECT_TYPES),
        }

    if effect_type in {"arc_pressure_delta", "arc_stage_set", "arc_flag_set"}:
        arc_id = str(effect.get("arc_id") or "")
        if not get_story_arc(simulation_state, arc_id):
            return {
                "ok": False,
                "reason": "arc_missing",
                "effect_type": effect_type,
                "arc_id": arc_id,
            }
        if effect_type == "arc_pressure_delta":
            delta = int(effect.get("delta") or 0)
            if delta < -100 or delta > 100:
                return {
                    "ok": False,
                    "reason": "pressure_delta_out_of_bounds",
                    "effect_type": effect_type,
                    "arc_id": arc_id,
                    "delta": delta,
                }

    if effect_type in {"lore_reveal", "lore_truth_status_set", "lore_known_by_add", "lore_tag_add"}:
        lore_id = str(effect.get("lore_id") or "")
        if not get_lore_entry(simulation_state, lore_id):
            return {
                "ok": False,
                "reason": "lore_missing",
                "effect_type": effect_type,
                "lore_id": lore_id,
            }

    if effect_type == "quest_transition":
        transition = _safe_dict(effect.get("transition"))
        quest_id = str(transition.get("quest_id") or effect.get("quest_id") or "")
        # Starting a quest may create it; other actions should reference existing quest.
        if transition.get("action") != "start" and quest_id and not get_quest(simulation_state, quest_id):
            return {
                "ok": False,
                "reason": "quest_missing",
                "effect_type": effect_type,
                "quest_id": quest_id,
            }

    if effect_type == "puzzle_transition":
        transition = _safe_dict(effect.get("transition"))
        puzzle_id = str(transition.get("puzzle_id") or effect.get("puzzle_id") or "")
        if transition.get("action") != "start" and puzzle_id and not get_puzzle(simulation_state, puzzle_id):
            return {
                "ok": False,
                "reason": "puzzle_missing",
                "effect_type": effect_type,
                "puzzle_id": puzzle_id,
            }

    if effect_type == "social_delta":
        npc_id = str(effect.get("npc_id") or "")
        if not npc_id:
            return {
                "ok": False,
                "reason": "missing_npc_id",
                "effect_type": effect_type,
            }
        for key in ("trust", "fear", "respect", "hostility", "reputation"):
            if key in effect:
                value = int(effect.get(key) or 0)
                if value < -100 or value > 100:
                    return {
                        "ok": False,
                        "reason": "social_delta_out_of_bounds",
                        "effect_type": effect_type,
                        "npc_id": npc_id,
                        "field": key,
                        "value": value,
                    }

    if effect_type == "npc_evolution":
        npc_id = str(effect.get("npc_id") or "")
        if not npc_id:
            return {
                "ok": False,
                "reason": "missing_npc_id",
                "effect_type": effect_type,
            }
        personality_deltas = _safe_dict(effect.get("personality_deltas"))
        for key, value in personality_deltas.items():
            value = int(value or 0)
            if value < -100 or value > 100:
                return {
                    "ok": False,
                    "reason": "personality_delta_out_of_bounds",
                    "effect_type": effect_type,
                    "npc_id": npc_id,
                    "field": str(key),
                    "value": value,
                }

    return {
        "ok": True,
        "reason": "valid_effect",
        "effect_type": effect_type,
    }


def validate_story_event(
    simulation_state: Dict[str, Any],
    event: Dict[str, Any],
) -> Dict[str, Any]:
    event = _safe_dict(event)
    errors: List[Dict[str, Any]] = []

    event_id = _safe_str(event.get("event_id"))
    if not event_id:
        errors.append({"reason": "missing_event_id"})

    arc_id = _safe_str(event.get("arc_id"))
    if arc_id and not get_story_arc(simulation_state, arc_id):
        errors.append({"reason": "arc_missing", "arc_id": arc_id})

    location_id = _safe_str(event.get("location_id"))
    if event.get("require_location", False) and not location_id:
        errors.append({"reason": "location_missing"})

    effects = _safe_list(event.get("effects"))
    if len(effects) > 25:
        errors.append({"reason": "too_many_effects", "count": len(effects), "max": 25})

    preconditions = _safe_list(event.get("preconditions"))
    precondition_results = [
        evaluate_story_arc_condition(simulation_state, condition)
        for condition in preconditions
        if isinstance(condition, dict)
    ]
    for result in precondition_results:
        if not result.get("ok"):
            errors.append(
                {
                    "reason": "precondition_failed",
                    "condition_result": result,
                }
            )

    effect_results = [
        validate_story_event_effect(simulation_state, effect)
        for effect in effects
        if isinstance(effect, dict)
    ]
    for result in effect_results:
        if not result.get("ok"):
            errors.append(
                {
                    "reason": "effect_invalid",
                    "effect_result": result,
                }
            )

    return {
        "ok": not errors,
        "event_id": event_id,
        "arc_id": arc_id,
        "errors": errors,
        "precondition_results": precondition_results,
        "effect_validation_results": effect_results,
    }