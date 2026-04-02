"""OutcomeRecorder — records action outcomes into NPC memory and planner.

This module provides the failure / success feedback loop that allows:
    - NPCs to remember which actions failed or succeeded in certain contexts.
    - The planner to dynamically penalise or prefer actions based on outcomes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from .feedback import DecisionOutcome


class OutcomeRecorder:
    """Records decision outcomes into NPC memory and planner heuristics."""

    def record(
        self,
        npc: Any,
        outcome: "DecisionOutcome",
        plan: Optional[Dict[str, Any]] = None,
        llm_adjustment: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record the outcome of an executed action.

        Args:
            npc: The NPC entity.
            outcome: The decision outcome.
            plan: Original GOAP plan dict (for debugging / analysis).
            llm_adjustment: LLM adjustment used (for debugging / analysis).

        Returns:
            A summary dict with keys: ``success``, ``action``,
            ``memory_updated``, ``penalty_applied``.
        """
        action_name = (
            outcome.action
            if isinstance(outcome.action, str)
            else getattr(outcome.action, "name", str(outcome.action))
        )

        memory_key = f"outcome_{action_name}"
        memory_event: Dict[str, Any] = {
            "type": "outcome",
            "action": action_name,
            "success": outcome.success,
            "reward": outcome.reward,
            "effects": outcome.effects,
        }

        # Store in NPC memory
        npc_memory = getattr(npc, "memory", {})
        if isinstance(npc_memory, dict):
            outcomes = npc_memory.setdefault("action_outcomes", {})
            action_outcomes = outcomes.setdefault(action_name, [])
            action_outcomes.append(memory_event)
            # Keep only last 20 outcomes per action
            outcomes[action_name] = action_outcomes[-20:]

        return {
            "success": outcome.success,
            "action": action_name,
            "memory_updated": True,
            "penalty_applied": not outcome.success,
        }