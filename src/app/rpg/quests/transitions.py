from __future__ import annotations

from typing import Any, Dict

from app.rpg.quests.conditions import evaluate_all_quest_conditions
from app.rpg.quests.rewards import build_reward_payload
from app.rpg.quests.state import (
    complete_objective,
    get_quest,
    set_quest_stage,
    start_quest,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def apply_quest_transition(
    simulation_state: Dict[str, Any],
    transition: Dict[str, Any],
    *,
    turn_index: int = 0,
) -> Dict[str, Any]:
    transition = _safe_dict(transition)
    action = str(transition.get("action") or "")
    quest_id = str(transition.get("quest_id") or "")

    conditions = transition.get("conditions") or []
    condition_result = evaluate_all_quest_conditions(simulation_state, conditions)
    if not condition_result.get("ok"):
        return {
            "ok": False,
            "kind": "quest_transition",
            "action": action,
            "quest_id": quest_id,
            "reason": "conditions_failed",
            "conditions": condition_result,
        }

    if action == "start":
        return dict(
            start_quest(
                simulation_state,
                quest_id,
                title=str(transition.get("title") or quest_id),
                stage=str(transition.get("stage") or "started"),
                objectives=transition.get("objectives") or {},
                turn_index=turn_index,
            ),
            conditions=condition_result,
        )

    if action == "set_stage":
        return dict(
            set_quest_stage(
                simulation_state,
                quest_id,
                str(transition.get("stage") or ""),
                status=transition.get("status"),
                turn_index=turn_index,
            ),
            conditions=condition_result,
        )

    if action == "complete_objective":
        return dict(
            complete_objective(
                simulation_state,
                quest_id,
                str(transition.get("objective_id") or ""),
                turn_index=turn_index,
            ),
            conditions=condition_result,
        )

    if action == "complete_quest":
        result = set_quest_stage(
            simulation_state,
            quest_id,
            str(transition.get("stage") or "completed"),
            status="completed",
            turn_index=turn_index,
        )
        reward_payload = {}
        if transition.get("rewards"):
            reward_payload = build_reward_payload(
                simulation_state,
                quest_id,
                transition.get("rewards") or [],
            )
        return dict(
            result,
            kind="quest_complete",
            conditions=condition_result,
            reward_payload=reward_payload,
        )

    quest = get_quest(simulation_state, quest_id)
    return {
        "ok": False,
        "kind": "quest_transition",
        "action": action,
        "quest_id": quest_id,
        "reason": f"unknown_action:{action}",
        "quest": quest,
        "conditions": condition_result,
    }