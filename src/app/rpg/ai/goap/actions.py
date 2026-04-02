"""GOAP Action utilities — legacy compatibility module.

All core logic lives in planner.py.  This module simply re-exports
the implementations so that existing import paths continue to work.

Usage:
    from rpg.ai.goap.actions import (
        Action,
        build_memory_based_state,
        move_to_target,
        default_actions,
    )
"""

from __future__ import annotations

# Re-export everything from planner.py — no circular import because
# planner.py does NOT import this module.
from .planner import (
    Action,
    build_memory_based_state,
    default_actions,
    move_to_target,
)

__all__ = [
    "Action",
    "build_memory_based_state",
    "default_actions",
    "move_to_target",
]