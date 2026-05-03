"""Deterministic NPC arc/evolution helpers."""

from app.rpg.npc_evolution.conditions import evaluate_npc_evolution_condition
from app.rpg.npc_evolution.state import (
    apply_npc_evolution_delta,
    ensure_npc_evolution_state,
    get_npc_evolution,
    normalize_npc_evolution_state,
    set_npc_arc_flag,
    start_npc_arc,
)
from app.rpg.npc_evolution.transitions import apply_npc_evolution_transition

__all__ = [
    "apply_npc_evolution_delta",
    "apply_npc_evolution_transition",
    "ensure_npc_evolution_state",
    "evaluate_npc_evolution_condition",
    "get_npc_evolution",
    "normalize_npc_evolution_state",
    "set_npc_arc_flag",
    "start_npc_arc",
]