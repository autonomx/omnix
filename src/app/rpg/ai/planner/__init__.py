"""PHASE 4.5 — NPC Decision Loop Integration

Simulation-based planning for NPCs. NPCs simulate 3-5 futures,
score them with AI/heuristics, and choose the best action.

This module provides:
- NPCPlanner: Chooses actions via simulation + scoring
- CandidateGenerator: Creates candidate action sequences
- PlanningConfig: Configuration for planning behavior
- Planner: Original planner (from planner.py for compatibility)

Integration with Core:
- Hooks into GameLoop NPC phase
- Uses EventBus for event emission
- NEVER mutates real game state during planning
"""

import os

# Re-export original Planner for backward compatibility
import sys

from .candidate_generator import CandidateGenerator
from .npc_planner import NPCPlanner, PlanningConfig

_planner_py_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "planner.py")
if os.path.exists(_planner_py_path):
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "app.rpg.ai.planner_module", _planner_py_path
    )
    _module = importlib.util.module_from_spec(_spec)
    sys.modules["app.rpg.ai.planner_module"] = _module
    _spec.loader.exec_module(_module)
    Planner = _module.Planner

__all__ = [
    "NPCPlanner",
    "PlanningConfig",
    "CandidateGenerator",
    "Planner",
]
