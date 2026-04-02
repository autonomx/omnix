"""DecisionOutcome — structured result of an executed NPC action.

This module provides the feedback mechanism that allows the DecisionEngine
to learn from outcomes (success / failure) and update NPC memory, planner
heuristics, and emergence signals accordingly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class DecisionOutcome:
    """Structured result of an executed NPC action.

    Attributes:
        action: The action that was executed.
        success: Whether the action succeeded.
        effects: Optional dict of side-effects / state changes produced.
        reward: Optional float reward signal (positive = good, negative = bad).
        debug_trace: Optional debug trace from the DecisionEngine.
    """
    action: Any
    success: bool
    effects: Dict[str, Any] = field(default_factory=dict)
    reward: Optional[float] = None
    debug_trace: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict for logging / persistence."""
        return {
            "action": self.action,
            "success": self.success,
            "effects": self.effects,
            "reward": self.reward,
        }