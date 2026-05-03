from __future__ import annotations

from typing import Any, Dict

from app.rpg.npc_evolution.conditions import evaluate_all_npc_evolution_conditions
from app.rpg.npc_evolution.state import (
    apply_npc_evolution_delta,
    complete_npc_arc,
    set_npc_arc_flag,
    start_npc_arc,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def apply_npc_evolution_transition(
    simulation_state: Dict[str, Any],
    transition: Dict[str, Any],
    *,
    turn_index: int = 0,
) -> Dict[str, Any]:
    transition = _safe_dict(transition)
    action = str(transition.get("action") or "")
    npc_id = str(transition.get("npc_id") or "")
    conditions = [
        row
        for row in transition.get("conditions") or []
        if isinstance(row, dict)
    ]
    condition_result = evaluate_all_npc_evolution_conditions(simulation_state, conditions)
    if not condition_result.get("ok"):
        return {
            "ok": False,
            "kind": "npc_evolution_transition",
            "action": action,
            "npc_id": npc_id,
            "reason": "conditions_failed",
            "conditions": condition_result,
        }

    if action == "start_arc":
        return dict(
            start_npc_arc(
                simulation_state,
                npc_id,
                str(transition.get("arc_id") or ""),
                motivation=str(transition.get("motivation") or ""),
                role=str(transition.get("role") or ""),
                profession=str(transition.get("profession") or ""),
                turn_index=turn_index,
            ),
            action=action,
            conditions=condition_result,
        )

    if action == "complete_arc":
        return dict(
            complete_npc_arc(
                simulation_state,
                npc_id,
                str(transition.get("arc_id") or ""),
                turn_index=turn_index,
            ),
            action=action,
            conditions=condition_result,
        )

    if action == "evolve":
        return dict(
            apply_npc_evolution_delta(
                simulation_state,
                npc_id,
                profession=str(transition.get("profession") or ""),
                role=str(transition.get("role") or ""),
                motivation=str(transition.get("motivation") or ""),
                personality_deltas=_safe_dict(transition.get("personality_deltas")),
                companion_eligible=transition.get("companion_eligible") if "companion_eligible" in transition else None,
                companion_offered=transition.get("companion_offered") if "companion_offered" in transition else None,
                flags=_safe_dict(transition.get("flags")),
                source_event_id=str(transition.get("source_event_id") or ""),
                turn_index=turn_index,
            ),
            action=action,
            conditions=condition_result,
        )

    if action == "set_flag":
        return dict(
            set_npc_arc_flag(
                simulation_state,
                npc_id,
                str(transition.get("flag") or ""),
                transition.get("value", True),
                turn_index=turn_index,
            ),
            action=action,
            conditions=condition_result,
        )

    return {
        "ok": False,
        "kind": "npc_evolution_transition",
        "action": action,
        "npc_id": npc_id,
        "reason": f"unknown_npc_evolution_action:{action}",
        "conditions": condition_result,
    }