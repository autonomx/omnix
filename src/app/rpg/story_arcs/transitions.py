from __future__ import annotations

from typing import Any, Dict

from app.rpg.lore.transitions import apply_lore_transition
from app.rpg.story_arcs.conditions import evaluate_all_story_arc_conditions
from app.rpg.story_arcs.state import (
    apply_story_arc_pressure_delta,
    link_story_arc,
    set_story_arc_flag,
    set_story_arc_stage,
    start_story_arc,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def apply_story_arc_transition(
    simulation_state: Dict[str, Any],
    transition: Dict[str, Any],
    *,
    turn_index: int = 0,
) -> Dict[str, Any]:
    transition = _safe_dict(transition)
    action = str(transition.get("action") or "")
    arc_id = str(transition.get("arc_id") or "")

    conditions = transition.get("conditions") or []
    condition_result = evaluate_all_story_arc_conditions(simulation_state, conditions)
    if not condition_result.get("ok"):
        return {
            "ok": False,
            "kind": "story_arc_transition",
            "action": action,
            "arc_id": arc_id,
            "reason": "conditions_failed",
            "conditions": condition_result,
        }

    if action == "start":
        return dict(
            start_story_arc(
                simulation_state,
                arc_id,
                title=str(transition.get("title") or arc_id),
                stage=str(transition.get("stage") or "started"),
                pressure=int(transition.get("pressure") or 0),
                links=transition.get("links") or {},
                turn_index=turn_index,
            ),
            action=action,
            conditions=condition_result,
        )

    if action == "set_stage":
        return dict(
            set_story_arc_stage(
                simulation_state,
                arc_id,
                str(transition.get("stage") or ""),
                status=transition.get("status"),
                turn_index=turn_index,
            ),
            action=action,
            conditions=condition_result,
        )

    if action == "pressure_delta":
        return dict(
            apply_story_arc_pressure_delta(
                simulation_state,
                arc_id,
                int(transition.get("delta") or 0),
                turn_index=turn_index,
            ),
            action=action,
            conditions=condition_result,
        )

    if action == "set_flag":
        return dict(
            set_story_arc_flag(
                simulation_state,
                arc_id,
                str(transition.get("flag") or ""),
                transition.get("value", True),
            ),
            action=action,
            conditions=condition_result,
        )

    if action.startswith("link_"):
        kind = action.replace("link_", "", 1)
        return dict(
            link_story_arc(
                simulation_state,
                arc_id,
                kind,
                str(transition.get("target_id") or ""),
            ),
            action=action,
            conditions=condition_result,
        )

    if action == "reveal_lore":
        return dict(
            apply_lore_transition(
                simulation_state,
                {
                    "action": "reveal_to_player",
                    "lore_id": str(transition.get("lore_id") or ""),
                },
                turn_index=turn_index,
            ),
            kind="story_arc_lore_reveal",
            action=action,
            arc_id=arc_id,
            conditions=condition_result,
        )

    if action == "resolve":
        return dict(
            set_story_arc_stage(
                simulation_state,
                arc_id,
                str(transition.get("stage") or "resolved"),
                status="resolved",
                turn_index=turn_index,
            ),
            action=action,
            conditions=condition_result,
        )

    if action == "fail":
        return dict(
            set_story_arc_stage(
                simulation_state,
                arc_id,
                str(transition.get("stage") or "failed"),
                status="failed",
                turn_index=turn_index,
            ),
            action=action,
            conditions=condition_result,
        )

    return {
        "ok": False,
        "kind": "story_arc_transition",
        "action": action,
        "arc_id": arc_id,
        "reason": f"unknown_story_arc_action:{action}",
        "conditions": condition_result,
    }