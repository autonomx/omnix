"""NPC Mind -- Unified decision engine for LLM-driven NPCs.

Patches implemented:
- Patch 5: Spatial Awareness (visible entities, location filtering)
- Patch 6: LLM Load Control (urgency-based thinking skip)
- Patch 7: Multi-NPC Interaction Logic (interaction intent priority)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .memory import NPCMemory
from .goal_engine import GoalEngine
from .prompt_builder import build_context, build_npc_prompt
from .response_parser import NPCDecision, NPCResponseParser


class NPCMind:
    """Complete LLM-driven NPC mind with all patches.

    Usage:
        mind = NPCMind(llm_client, npc_id="1", ...)
        decision = mind.decide(world_state)
    """

    def __init__(
        self,
        llm_client=None,
        npc_id: str = "",
        npc_name: str = "NPC",
        npc_role: str = "villager",
        personality: Optional[Dict[str, float]] = None,
    ):
        """Initialize the NPC mind.

        Args:
            llm_client: LLM client for generation (can be None for testing).
            npc_id: Unique identifier.
            npc_name: Display name.
            npc_role: Role/occupation.
            personality: Trait dict (aggression, honor, greed).
        """
        self.llm_client = llm_client
        self.npc_id = npc_id
        self.npc_name = npc_name
        self.npc_role = npc_role

        # Patch 3: Personality traits
        self.personality = personality or {
            "aggression": 0.5,
            "honor": 0.5,
            "greed": 0.5,
        }

        # Patch 1: Memory with salience+decay
        self.memory = NPCMemory()

        # Patch 2: Goal lifecycle engine
        self.goals = GoalEngine(npc_id=npc_id)

        # Patch 4: Robust parser
        self.parser = NPCResponseParser()

        # Patch 6: Load control state
        self.last_decision: Optional[NPCDecision] = None
        self.last_tick: int = 0

    def decide(self, world: Dict[str, Any], tick: int = 0) -> NPCDecision:
        """Make a decision based on world state.

        Implements:
        - Patch 5: Spatial filtering of visible entities
        - Patch 6: Urgency-based LLM skip
        - Patch 7: Interaction intent priority

        Args:
            world: World state dict.
            tick: Current game tick.

        Returns:
            NPCDecision from LLM or fallback.
        """
        # Patch 5: Filter visible entities
        visible_entities = self._get_visible_entities(world)

        # Patch 6: Compute urgency for load control
        urgency = self._compute_urgency()

        # Skip LLM if nothing urgent and we have a recent decision
        if urgency < 0.3 and self.last_decision and (tick - self.last_tick) < 5:
            return self.last_decision

        # Patch 7: Build context with interaction priority
        intent_priority = len(visible_entities) > 0

        context = build_context(
            npc={"name": self.npc_name, "role": self.npc_role},
            personality=self.personality,
            memory=self.memory.summarize(),
            goals=[g.to_dict() for g in self.goals.active_goals],
            world={
                "visible_entities": visible_entities,
                "location": world.get("location", "unknown"),
            },
            recent_events=self.memory.get_raw_events(limit=5),
            intent_priority=intent_priority,
        )

        prompt = build_npc_prompt(context)

        # Call LLM if available
        if self.llm_client:
            try:
                raw = self.llm_client.generate(prompt)
                decision = self.parser.parse(raw)
            except Exception:
                decision = NPCDecision.fallback()
        else:
            decision = NPCDecision.fallback()

        # Remember the decision as an event
        event = {
            "type": "decision",
            "actor": self.npc_id,
            "intent": decision.intent,
            "target": decision.target,
            "tick": tick,
        }
        self.memory.remember(event)

        # Patch 2: Update goal progress from decision
        if decision.target:
            goal_event = {
                "type": decision.intent,
                "target": decision.target,
                "actor": self.npc_id,
            }
            self.goals.update_progress(goal_event)

        # Patch 6: Cache decision
        self.last_decision = decision
        self.last_tick = tick

        return decision

    def remember_event(self, event: Dict[str, Any]) -> None:
        """Record an external event into memory.

        Args:
            event: Event dict.
        """
        self.memory.remember(event)

        # Patch 2: Update goal progress
        self.goals.update_progress(event)

    def add_goal(self, goal: Dict[str, Any]) -> None:
        """Add a goal.

        Args:
            goal: Goal dict.
        """
        self.goals.add_goal(goal)

    def _get_visible_entities(self, world: Dict[str, Any]) -> List[Any]:
        """Patch 5: Filter entities by spatial awareness.

        Uses distance and location to determine visibility.

        Args:
            world: World state.

        Returns:
            List of visible entity dicts.
        """
        my_location = world.get("location", "")
        my_pos = world.get("position", (0, 0))
        entities = world.get("entities", [])
        vision_range = world.get("vision_range", 10.0)

        visible: List[Any] = []
        for e in entities:
            if isinstance(e, dict):
                # Skip self
                if e.get("id") == self.npc_id:
                    continue
                e_loc = e.get("location", "")
                e_pos = e.get("position")

                # Same location check
                if my_location and e_loc and my_location == e_loc:
                    visible.append(e)
                    continue

                # Distance check
                if e_pos and my_pos:
                    dist = self._distance(my_pos, e_pos)
                    if dist <= vision_range:
                        e_copy = dict(e)
                        e_copy["distance"] = dist
                        visible.append(e_copy)
            else:
                visible.append(e)

        return visible

    @staticmethod
    def _distance(p1: tuple, p2: tuple) -> float:
        """Euclidean distance between two points.

        Args:
            p1: First point (x, y).
            p2: Second point (x, y).

        Returns:
            Distance value.
        """
        import math
        return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

    def _compute_urgency(self) -> float:
        """Patch 6: Compute urgency for LLM load control.

        High urgency means the NPC needs to think right now.
        Low urgency means we can reuse the last decision.

        Returns:
            Urgency value between 0.0 and 1.0.
        """
        summary = self.memory.summarize()
        for mem in summary:
            t = mem.get("type", "") if isinstance(mem, dict) else ""
            if t in ("attack", "betrayal", "combat", "death", "damage"):
                return 1.0

        # Check goals for urgency
        for g in self.goals.active_goals:
            if g.priority > 0.8:
                return 0.9
            if g.goal_type in ("survive", "flee", "defend"):
                return 1.0

        return 0.2

    def evaluate_plan(
        self,
        npc: Any,
        plan: Dict[str, Any],
        world_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Evaluate and optionally adjust a GOAP plan.

        Instead of deciding the action directly, the LLM reviews the
        structured plan and returns adjustments:
            - ``override``: Whether the LLM wants to veto the plan.
            - ``override_action``: The forced action name when overriding.
            - ``new_goal``: Alternative goal the LLM suggests.
            - ``emotional_bias``: Emotion string to inject behavior.
            - ``risk_tolerance``: Float 0.0–1.0 for risk adjustment.

        This method is designed to be called by the DecisionEngine,
        replacing the old ``decide_action`` pattern.

        Args:
            npc: The NPC entity.
            plan: Structured GOAP plan dict (goal, steps, priority).
            world_state: The current world state.

        Returns:
            Adjustment dict with keys: override, new_goal,
            emotional_bias, risk_tolerance.
        """
        urgency = self._compute_urgency()
        personality_str = ", ".join(
            f"{k}={v}" for k, v in self.personality.items()
        )

        # Build a prompt that asks the LLM to evaluate the plan
        prompt = (
            f"You are {self.npc_name} ({self.npc_role}).\n"
            f"Personality: {personality_str}\n\n"
            f"Current GOAP plan:\n"
            f"  Goal: {plan.get('goal', 'unknown')}\n"
            f"  Steps: {plan.get('steps', [])}\n"
            f"  Priority: {plan.get('priority', 0.5)}\n\n"
            f"World state summary: {world_state}\n\n"
            f"Urgency level: {urgency:.2f}\n\n"
            f"Respond with a JSON object containing:\n"
            f"  - override (bool): Should this plan be overridden?\n"
            f"  - override_action (str|null): Action to force instead.\n"
            f"  - new_goal (str|null): Better goal to pursue.\n"
            f"  - emotion (str|null): Current emotion (anger,fear,joy,sadness,surprise,trust,disgust,anticipation).\n"
            f"  - risk (float 0-1): Risk tolerance.\n"
        )

        if self.llm_client:
            try:
                raw = self.llm_client.generate(prompt)
                return self._parse_plan_evaluation(raw)
            except Exception:
                pass

        # Fallback: no adjustment needed
        return {
            "override": False,
            "override_action": None,
            "new_goal": None,
            "emotion": None,
            "risk_tolerance": urgency * 0.5,
        }

    def _parse_plan_evaluation(
        self, raw_response: str
    ) -> Dict[str, Any]:
        """Parse an LLM plan evaluation response.

        Args:
            raw_response: Raw text from the LLM.

        Returns:
            Parsed adjustment dict.
        """
        result: Dict[str, Any] = {
            "override": False,
            "override_action": None,
            "new_goal": None,
            "emotion": None,
            "risk_tolerance": 0.5,
        }

        # Very simple JSON-ish parsing (production should use proper JSON extraction)
        text = raw_response.strip().strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()

        try:
            import json
            parsed = json.loads(text)
            result["override"] = bool(parsed.get("override", False))
            result["override_action"] = parsed.get("override_action")
            result["new_goal"] = parsed.get("new_goal")
            result["emotion"] = parsed.get("emotion")
            result["risk_tolerance"] = float(parsed.get("risk", 0.5))
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        return result

    def reset(self) -> None:
        """Reset all state."""
        self.memory.clear()
        self.goals.reset()
        self.last_decision = None
        self.last_tick = 0

    def __repr__(self) -> str:
        return (
            f"NPCMind(id='{self.npc_id}', name='{self.npc_name}', "
            f"role='{self.npc_role}', "
            f"mem_events={len(self.memory)}, "
            f"active_goals={len(self.goals.active_goals)})"
        )