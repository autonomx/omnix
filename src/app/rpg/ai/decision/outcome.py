"""OutcomeRecorder — records action outcomes into NPC memory and planner.

This module provides the failure / success feedback loop that allows:
    - NPCs to remember which actions failed or succeeded in certain contexts.
    - The planner to dynamically penalise or prefer actions based on outcomes.
    - Emotion adjustment based on success/failure (frustration, confidence).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from .feedback import DecisionOutcome


class OutcomeRecorder:
    """Records decision outcomes into NPC memory and adjusts emotion."""

    def record(
        self,
        npc: Any,
        outcome: "DecisionOutcome",
        plan: Optional[Dict[str, Any]] = None,
        llm_adjustment: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record the outcome of an executed action.

        Side-effects:
            - Updates ``npc.memory["action_outcomes"]`` with result.
            - Adjusts NPC emotion if they have an ``emotion`` system.
                - success → +0.1 confidence
                - failure → +0.2 frustration

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

        # Adjust emotion based on outcome (high impact, connects
        # action → emotion → next decision)
        self._adjust_emotion(npc, outcome)

        return {
            "success": outcome.success,
            "action": action_name,
            "memory_updated": True,
            "penalty_applied": not outcome.success,
        }

    @staticmethod
    def _adjust_emotion(npc: Any, outcome: "DecisionOutcome") -> None:
        """Adjust NPC emotion based on action outcome.

        - success → +0.1 confidence
        - failure → +0.2 frustration

        If the NPC doesn't have an emotion system this is a no-op.
        """
        emotion = getattr(npc, "emotion", None)
        if emotion is None:
            return

        if outcome.success:
            adjust_fn = getattr(emotion, "adjust", None)
            if callable(adjust_fn):
                adjust_fn("confidence", +0.1)
        else:
            adjust_fn = getattr(emotion, "adjust", None)
            if callable(adjust_fn):
                adjust_fn("frustration", +0.2)