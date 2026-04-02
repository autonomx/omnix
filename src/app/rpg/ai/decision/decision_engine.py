"""Core decision engine — the ONLY entry point for NPC decisions.

This module introduces the authoritative decision pipeline that collapses
GOAP planning, LLM cognitive modulation, and action resolution into a
single, debuggable flow.

Classes:
    DecisionContext: Holds the state of a single decision cycle, including
        the GOAP plan, LLM adjustments, final action, debug trace, and
        reasoning metadata.
    DecisionEngine: Orchestrates the three-phase decision pipeline.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


class DecisionContext:
    """Context object for a single decision cycle.

    Populated incrementally as the DecisionEngine processes a decision.
    Exposed after ``decide()`` returns for debugging and telemetry.
    """

    def __init__(self, npc: Any, world_state: Dict[str, Any]) -> None:
        self.npc = npc
        self.world_state = world_state
        self.plan: Optional[Dict[str, Any]] = None
        self.llm_adjustment: Optional[Dict[str, Any]] = None
        self.final_action: Optional[Any] = None
        self.confidence: float = 0.5
        self.debug_trace: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the context for debugging / logging.

        Returns:
            Dict containing goap_plan, llm_adjustment, final_action,
            confidence, and reasoning.
        """
        return {
            "goap_plan": self.plan,
            "llm_adjustment": self.llm_adjustment,
            "final_action": self.final_action,
            "confidence": self.confidence,
            "reasoning": self.debug_trace.get("reasoning", {}),
        }


class DecisionEngine:
    """The single, authoritative NPC decision pipeline.

    Workflow:
        1. GOAP planner generates a structured plan (deterministic backbone).
        2. LLM evaluates and optionally modulates the plan (expressive layer).
        3. ActionResolver picks the first *valid* action from the adjusted plan.

    Usage:
        engine = DecisionEngine(goap_planner, llm_mind, resolver)
        action, debug = engine.decide(npc, world_state)
    """

    def __init__(
        self,
        goap_planner: Any,
        llm_mind: Any,
        resolver: Any,
    ) -> None:
        """Initialise the decision engine.

        Args:
            goap_planner: Must expose ``plan(npc, world_state)`` returning
                a structured plan dict (goal, steps, priority).
            llm_mind: Must expose ``evaluate_plan(npc, plan, world_state)``
                returning an adjustment dict (override, new_goal, emotion,
                risk_tolerance, …).
            resolver: Must expose ``resolve(npc, plan, llm_adjustment,
                world_state)`` returning the final action.
        """
        self.goap_planner = goap_planner
        self.llm_mind = llm_mind
        self.resolver = resolver

    def decide(
        self,
        npc: Any,
        world_state: Dict[str, Any],
    ) -> Tuple[Any, Dict[str, Any]]:
        """Run the full decision pipeline for *npc*.

        Args:
            npc: The NPC entity to decide for.
            world_state: Current world state dict.

        Returns:
            A tuple of ``(final_action, debug_trace)``.  ``final_action``
            is whatever the resolver returns (typically an action name or
            action object).  ``debug_trace`` contains the intermediate
            outputs of each pipeline stage, including a ``"reasoning"``
            block that explains why a particular action was chosen.
        """
        ctx = DecisionContext(npc, world_state)

        # ------------------------------------------------------------------
        # Phase 1 – Structured plan (deterministic backbone)
        # ------------------------------------------------------------------
        ctx.plan = self.goap_planner.plan(npc, world_state)

        # ------------------------------------------------------------------
        # Phase 2 – LLM cognitive modulation
        # ------------------------------------------------------------------
        ctx.llm_adjustment = self.llm_mind.evaluate_plan(
            npc=npc,
            plan=ctx.plan,
            world_state=world_state,
        )

        # ------------------------------------------------------------------
        # Phase 3 – Final resolution (single authority)
        # ------------------------------------------------------------------
        ctx.final_action = self.resolver.resolve(
            npc=npc,
            plan=ctx.plan,
            llm_adjustment=ctx.llm_adjustment,
            world_state=world_state,
        )

        # ------------------------------------------------------------------
        # Debug & reasoning metadata
        # ------------------------------------------------------------------
        rejected = ctx.plan.get("rejected_steps", []) if ctx.plan else []
        is_override = bool(
            ctx.llm_adjustment and ctx.llm_adjustment.get("override")
        )

        ctx.debug_trace["goap_plan"] = ctx.plan
        ctx.debug_trace["llm_adjustment"] = ctx.llm_adjustment
        ctx.debug_trace["final_action"] = ctx.final_action

        ctx.debug_trace["reasoning"] = {
            "selected_step": ctx.final_action,
            "rejected_steps": rejected,
            "llm_override_used": is_override,
            "llm_influence": ctx.llm_adjustment,
            "plan_score": (
                ctx.plan.get("score", None)
                if isinstance(ctx.plan, dict)
                else None
            ),
            "action_valid": ctx.final_action != "idle",
        }

        # ------------------------------------------------------------------
        # Improved confidence scoring
        # ------------------------------------------------------------------
        priority = (
            ctx.plan.get("priority", 0.5)
            if isinstance(ctx.plan, dict)
            else 0.5
        )
        risk = (
            ctx.llm_adjustment.get("risk_tolerance", 0.5)
            if isinstance(ctx.llm_adjustment, dict)
            else 0.5
        )
        validity = 1.0 if ctx.final_action != "idle" else 0.3
        ctx.confidence = priority * (1 - risk) * validity
        ctx.debug_trace["confidence"] = ctx.confidence

        return ctx.final_action, ctx.debug_trace