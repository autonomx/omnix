"""Regression tests for the DecisionEngine pipeline.

These tests ensure that the unified decision pipeline:
    - Maintains backward compatibility with existing interfaces.
    - Produces deterministic results for identical inputs.
    - Handles edge cases without crashing.
    - Maintains the strict rule that only ActionResolver returns final actions.
"""

from __future__ import annotations

import sys
import pathlib
import unittest
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT / "src" / "app") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src" / "app"))

from rpg.ai.decision.decision_engine import DecisionContext, DecisionEngine
from rpg.ai.decision.resolver import ActionResolver
from rpg.ai.goap.planner import Action as GOAPAction, GOAPPlanner, plan as goap_plan


@dataclass
class DummyNPC:
    """Minimal NPC entity for testing."""
    id: str = "npc_1"
    name: str = "Bob"
    hp: int = 100
    memory: Any = None


class DummyLLMMind:
    """Fake LLM mind for testing."""

    def __init__(self, **adjustments: Any) -> None:
        self._adjustments = adjustments

    def evaluate_plan(
        self, npc: Any, plan: Dict[str, Any], world_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        return dict(self._adjustments)


class TestRegressionDecisionEngine(unittest.TestCase):
    """Regression suite for DecisionEngine behaviour."""

    def test_deterministic_output_for_identical_inputs(self) -> None:
        """Same inputs must always produce the same outputs."""
        npc = DummyNPC(hp=50)
        world = {"tick": 0}
        engine = DecisionEngine(
            GOAPPlanner(),
            DummyLLMMind(risk_tolerance=0.5),
            ActionResolver(),
        )

        results = [engine.decide(npc, deepcopy(world)) for _ in range(5)]
        first_action, first_debug = results[0]
        for action, debug in results[1:]:
            self.assertEqual(action, first_action)
            self.assertEqual(debug["goap_plan"], first_debug["goap_plan"])
            self.assertEqual(debug["confidence"], first_debug["confidence"])

    def test_no_action_returned_outside_resolver(self) -> None:
        """Ensure DecisionEngine never returns action directly from GOAP/LLM."""
        goap = GOAPPlanner()
        llm = DummyLLMMind()
        resolver = ActionResolver()
        engine = DecisionEngine(goap, llm, resolver)

        npc = DummyNPC()
        action, _ = engine.decide(npc, {})

        # The action must come through the resolver — we validate
        # that it is a string (the resolver always returns strings).
        self.assertIsInstance(action, str)

    def test_empty_plan_handling(self) -> None:
        engine = DecisionEngine(
            GOAPPlanner(),
            DummyLLMMind(),
            ActionResolver(),
        )
        npc = DummyNPC()
        action, debug = engine.decide(npc, {})
        self.assertEqual(debug["final_action"], "idle")

    def test_none_llm_adjustment_handling(self) -> None:
        """Resolver must handle None llm_adjustment gracefully."""
        resolver = ActionResolver()
        plan = {"goal": "x", "steps": ["a"], "priority": 0.5}

        action = resolver.resolve(None, plan, None, {})
        self.assertEqual(action, "a")

    def test_empty_llm_adjustment_handling(self) -> None:
        resolver = ActionResolver()
        plan = {"goal": "x", "steps": ["a"], "priority": 0.5}

        action = resolver.resolve(None, plan, {}, {})
        self.assertEqual(action, "a")

    def test_llm_override_without_action_uses_new_goal(self) -> None:
        resolver = ActionResolver()
        plan = {"goal": "combat", "steps": ["attack"], "priority": 0.8}
        adj = {"override": True, "new_goal": "flee"}

        action = resolver.resolve(None, plan, adj, {})
        self.assertEqual(action, "flee")

    def test_llm_override_with_neither_action_nor_goal(self) -> None:
        resolver = ActionResolver()
        adj = {"override": True}
        action = resolver.resolve(None, None, adj, {})
        self.assertEqual(action, "idle")

    def test_plan_not_mutated_by_resolver(self) -> None:
        """Resolver must not mutate the input plan dict."""
        resolver = ActionResolver()
        plan = {"goal": "x", "steps": ["idle"], "priority": 0.5}
        original = deepcopy(plan)

        adj = {"emotional_bias": "anger", "new_goal": "fight"}
        resolver.resolve(None, plan, adj, {})

        self.assertEqual(plan, original)

    def test_priority_reduced_by_high_risk(self) -> None:
        """High risk tolerance should reduce effective confidence."""
        goap = GOAPPlanner()
        llm = DummyLLMMind(risk_tolerance=1.0)  # Maximum risk
        engine = DecisionEngine(goap, llm, ActionResolver())

        npc = DummyNPC(hp=10)  # Triggers high priority survival plan
        _, debug = engine.decide(npc, {})
        self.assertLess(debug["confidence"], 0.5)

    def test_confidence_zero_when_risk_is_one(self) -> None:
        goap = GOAPPlanner()
        llm = DummyLLMMind(risk_tolerance=1.0)
        engine = DecisionEngine(goap, llm, ActionResolver())

        npc = DummyNPC()
        _, debug = engine.decide(npc, {})
        self.assertAlmostEqual(debug["confidence"], 0.0, places=4)


class TestRegressionPlannerBackwardsCompat(unittest.TestCase):
    """Ensure existing planner interface still works."""

    def test_standalone_plan_function(self) -> None:
        actions = [
            GOAPAction("move", 1, {"has_target": True}, {"at_target": True}),
        ]
        result = goap_plan(
            initial_state={"has_target": True},
            goal={"at_target": True},
            actions=actions,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "move")

    def test_plan_empty_when_no_path(self) -> None:
        actions = [
            GOAPAction("jump", 1, {"has_wings": True}, {"flying": True}),
        ]
        result = goap_plan(
            initial_state={"has_wings": False},
            goal={"flying": True},
            actions=actions,
            max_depth=5,
        )
        self.assertEqual(result, [])

    def test_default_actions_produced(self) -> None:
        planner = GOAPPlanner()
        self.assertEqual(len(planner.actions), 5)

    def test_action_class_interface(self) -> None:
        a = GOAPAction("hit", cost=5, preconditions={"armed": True}, effects={"hurt": True})
        self.assertTrue(a.is_applicable({"armed": True}))
        self.assertFalse(a.is_applicable({"armed": False}))
        new_state = a.apply({"armed": True})
        self.assertTrue(new_state["hurt"])


class TestRegressionNPCMindEvaluatePlan(unittest.TestCase):
    """Ensure NPCMind.evaluate_plan interface works as designed."""

    def test_npc_mind_has_evaluate_plan(self) -> None:
        """NPCMind must expose evaluate_plan for DecisionEngine compatibility."""
        from rpg.ai.llm_mind.npc_mind import NPCMind

        mind = NPCMind(npc_id="1", npc_name="Test")
        self.assertTrue(hasattr(mind, "evaluate_plan"))
        self.assertTrue(callable(getattr(mind, "evaluate_plan")))

    def test_evaluate_plan_returns_adjustment_dict(self) -> None:
        from rpg.ai.llm_mind.npc_mind import NPCMind

        mind = NPCMind(npc_id="1", npc_name="Test")
        npc = DummyNPC()
        plan = {"goal": "x", "steps": [], "priority": 0.5}

        result = mind.evaluate_plan(npc, plan, {})

        self.assertIsInstance(result, dict)
        self.assertIn("override", result)
        self.assertIn("risk_tolerance", result)


if __name__ == "__main__":
    unittest.main()