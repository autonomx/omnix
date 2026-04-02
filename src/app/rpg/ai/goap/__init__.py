"""GOAP (Goal-Oriented Action Planning) package.

This package provides a pure GOAP planner that returns structured
plan dicts for use in the DecisionEngine pipeline.

Classes:
    Action: A GOAP action with name, cost, preconditions, and effects.
    GOAPPlanner: Planner that computes structured plans for NPCs.

Functions:
    plan: Classic A* GOAP planner function (returns action lists).
    build_memory_based_state: Build GOAP state from NPC memories.
    move_to_target: Helper to move an NPC toward a target.
    default_actions: Return default action list.
"""

# Import from planner.py — single source of truth.
from .planner import Action, GOAPPlanner, plan

# Lazy wrappers to avoid circular imports at module load time.

def build_memory_based_state(npc, context=None):
    """Build GOAP state dict from NPC memories and relationships."""
    from .planner import build_memory_based_state as _fn
    return _fn(npc, context)


def move_to_target(npc, target):
    """Move NPC toward target using directional movement."""
    from .planner import move_to_target as _fn
    return _fn(npc, target)


def default_actions():
    """Return default GOAP actions for NPCs."""
    from .planner import _default_actions
    return _default_actions()


__all__ = [
    "Action",
    "GOAPPlanner",
    "plan",
    "build_memory_based_state",
    "move_to_target",
    "default_actions",
]