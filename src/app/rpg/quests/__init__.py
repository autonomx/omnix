"""Deterministic RPG quest state machine helpers."""

from app.rpg.quests.conditions import evaluate_quest_condition
from app.rpg.quests.objectives import (
    complete_objective_lifecycle,
    create_objective,
    derive_quest_lifecycle,
    fail_objective,
    objective_from_template,
    update_objective_progress,
)
from app.rpg.quests.rewards import build_reward_payload, mark_reward_claimed
from app.rpg.quests.state import (
    complete_objective,
    ensure_quest_state,
    get_quest,
    normalize_quest_state,
    set_quest_stage,
    start_quest,
)
from app.rpg.quests.transitions import apply_quest_transition

__all__ = [
    "apply_quest_transition",
    "build_reward_payload",
    "complete_objective",
    "complete_objective_lifecycle",
    "create_objective",
    "derive_quest_lifecycle",
    "ensure_quest_state",
    "evaluate_quest_condition",
    "fail_objective",
    "get_quest",
    "mark_reward_claimed",
    "normalize_quest_state",
    "objective_from_template",
    "set_quest_stage",
    "start_quest",
    "update_objective_progress",
]
