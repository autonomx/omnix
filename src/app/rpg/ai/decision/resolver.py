"""ActionResolver — the single authority for selecting final NPC actions.

Takes a structured GOAP plan and optional LLM adjustments and produces
the definitive action for the NPC to execute.

Rules (never violate):
    - No side effects inside this resolver.
    - LLM override is rare and must be explicit AND validated.
    - When no plan is available, returns a safe fallback ("idle").
    - Plan is NEVER mutated — always copy.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional


class ActionResolver:
    """Resolves a GOAP plan + LLM adjustments into a final action."""

    def __init__(self, validity_checks: Optional[Dict[str, Any]] = None) -> None:
        """Initialise the resolver.

        Args:
            validity_checks: Optional mapping of action names to
                callables ``(npc, world_state) -> bool`` that decide
                whether an action is currently viable.  If ``None``,
                all actions are considered valid.
        """
        self._validity_checks: Dict[str, Any] = validity_checks or {}

    def resolve(
        self,
        npc: Any,
        plan: Optional[Dict[str, Any]],
        llm_adjustment: Optional[Dict[str, Any]],
        world_state: Dict[str, Any],
    ) -> Any:
        """Pick the action the NPC should execute this tick.

        Returns the first *valid* step from the adjusted plan.
        If no step is valid, returns ``"idle"``.

        Args:
            npc: The NPC entity.
            plan: Structured GOAP plan dict (goal, steps, priority).
            llm_adjustment: Adjustment dict from the LLM mind, or None.
            world_state: Current world state.

        Returns:
            The action to execute (typically a string action name or
            an action object).  Returns ``"idle"`` when no action
            is available or valid.
        """
        llm_adj = llm_adjustment or {}

        # LLM override (rare — must still pass validation)
        if llm_adj.get("override"):
            action = self._handle_override(npc, llm_adj)
            if self._is_valid(action, npc, world_state):
                return action
            return "idle"

        # No plan → safe fallback
        if not plan:
            return "idle"

        # Adjust plan based on LLM emotion / risk / new_goal (never mutates original)
        adjusted_plan = self._apply_adjustments(plan, llm_adj)

        # Select the final action from the adjusted plan
        return self._select_action(adjusted_plan, npc, world_state)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _handle_override(self, npc: Any, adj: Dict[str, Any]) -> Any:
        """Handle explicit LLM override.

        The LLM can supply an ``override_action`` key to force a
        specific action regardless of the GOAP plan.

        Args:
            npc: The NPC entity.
            adj: LLM adjustment dict with ``override`` set to True.

        Returns:
            The override action string, or ``"idle"`` as fallback.
        """
        override_action = adj.get("override_action")
        if override_action:
            return override_action
        # If no explicit action, try to derive from new_goal
        new_goal = adj.get("new_goal")
        if new_goal:
            return new_goal
        return "idle"

    def _apply_adjustments(
        self,
        plan: Dict[str, Any],
        adj: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply LLM adjustments to the GOAP plan.

        Modifications supported:
            - ``new_goal``: Replaces the plan's goal field.
            - ``emotional_bias``: Can prepend emotion-driven steps.
            - ``risk_tolerance``: Can adjust the plan priority.

        WARNING: This method ALWAYS RETURNS A NEW dict and a new
        ``steps`` list.  The original ``plan`` is never mutated.

        Args:
            plan: The original GOAP plan.
            adj: LLM adjustment dict.

        Returns:
            A brand-new modified plan dict.
        """
        # Deep-copy to protect against downstream mutation of steps
        new_plan: Dict[str, Any] = {
            k: v if k != "steps" else list(v)
            for k, v in plan.items()
        }
        # Ensure steps exists even if original had none
        new_plan.setdefault("steps", [])

        # Replace goal if LLM suggests a new one
        new_goal = adj.get("new_goal")
        if new_goal:
            new_plan["goal"] = new_goal

        # Adjust priority based on risk tolerance
        risk = adj.get("risk_tolerance")
        if risk is not None and "priority" in new_plan:
            # Higher risk → lower confidence in the plan
            new_plan["priority"] = new_plan["priority"] * (1 - risk * 0.5)

        # Emotional bias: prepend an emotion-driven step
        emotion = adj.get("emotional_bias")
        if emotion and new_plan.get("steps"):
            emotion_steps = _EMOTION_STEP_MAP.get(emotion, [])
            if emotion_steps:
                new_plan["steps"] = emotion_steps + new_plan["steps"]

        return new_plan

    def _select_action(
        self,
        plan: Dict[str, Any],
        npc: Any,
        world_state: Dict[str, Any],
    ) -> Any:
        """Select the next *valid* action from an adjusted plan.

        Iterates through all steps and returns the first one that
        passes the ``_is_valid`` check.  Rejected steps are recorded
        in the plan metadata for diagnostic purposes.

        Args:
            plan: The adjusted plan dict.
            npc: The NPC entity (used for context-aware validation).
            world_state: Current world state.

        Returns:
            The first valid action string, or ``"idle"`` if none match.
        """
        rejected: List[str] = []
        for step in plan.get("steps", []):
            if self._is_valid(step, npc, world_state):
                plan["selected_action"] = step
                plan["rejected_steps"] = rejected
                return step
            rejected.append(step)

        plan["rejected_steps"] = rejected
        return "idle"

    def _is_valid(
        self,
        action: Any,
        npc: Any,
        world_state: Dict[str, Any],
    ) -> bool:
        """Determine whether *action* is currently viable.

        Uses the ``_validity_checks`` mapping provided at
        construction time, plus built-in safety rules:

        - ``None`` or empty strings are always invalid.
        - Known actions without a registered checker are considered
          valid (allowing graceful degradation).

        Args:
            action: Candidate action name or object.
            npc: The NPC entity.
            world_state: Current world state.

        Returns:
            ``True`` if the action should be executed.
        """
        if action in (None, ""):
            return False

        # Convert action to string key for lookup
        key = action if isinstance(action, str) else getattr(action, "name", str(action))

        # Custom validity checker registered for this action
        checker = self._validity_checks.get(key)
        if checker is not None:
            return bool(checker(npc, world_state))

        # Built-in safety heuristics (extend as needed)
        if key == "find_cover":
            return bool(world_state.get("nearby_cover", False))
        if key == "attack":
            return world_state.get("enemy_visible", False)
        if key == "flee":
            return not world_state.get("trapped", False)
        if key in ("celebrate", "socialize", "trade"):
            return bool(world_state.get("ally_nearby", True))

        # Default: unknown actions are assumed valid
        return True


# ------------------------------------------------------------------
# Emotion-driven step injection table
# ------------------------------------------------------------------
# When the LLM injects an emotional bias, these steps are prepended
# to the plan to express the emotion as concrete behaviour.
# ------------------------------------------------------------------

_EMOTION_STEP_MAP: Dict[str, List[str]] = {
    "anger": ["attack", "intimidate"],
    "fear": ["flee", "hide", "seek_cover"],
    "joy": ["celebrate", "socialize", "trade"],
    "sadness": ["rest", "retreat", "mourn"],
    "surprise": ["observe", "investigate", "freeze"],
    "trust": ["approach", "help", "share"],
    "disgust": ["avoid", "reject", "withdraw"],
    "anticipation": ["prepare", "plan", "gather_resources"],
}