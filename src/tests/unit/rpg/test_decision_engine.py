"""Unit tests for the DecisionEngine pipeline.

Tests:
    DecisionContext: serialisation and default values.
    DecisionEngine: end-to-end pipeline with mocks.
    ActionResolver: override, adjustment, and fallback paths.
"""

from __future__ import annotations

import sys
import pathlib
import unittest
from copy import deepcopy
from unittest.mock import MagicMock

# Ensure the project root is on sys.path
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT / "src" / "app") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src" / "app"))

from rpg.ai.decision.decision_engine import DecisionContext, DecisionEngine
from rpg.ai.decision.resolver import ActionResolver


class TestDecisionContext(unittest.TestCase):
    """Test DecisionContext default state and serialisation."""

    def test_defaults(self) -> None:
        npc = MagicMock()
        world = {"tick": 0}
        ctx = DecisionContext(npc, world)

        self.assertIs(ctx.plan, None)
        self.assertIs(ctx.llm_adjustment, None)
        self.assertIs(ctx.final_action, None)
        self.assertEqual(ctx.confidence, 0.5)
        self.assertEqual(ctx.debug_trace, {})
        self.assertIs(ctx.npc, npc)
        self.assertIs(ctx.world_state, world)

    def test_to_dict(self) -> None:
        ctx = DecisionContext({}, {})
        ctx.plan = {"goal": "survive", "steps": ["flee"], "priority": 0.9}
        ctx.llm_adjustment = {"override": False, "risk_tolerance": 0.3}
        ctx.final_action = "flee"
        ctx.confidence = 0.63

        result = ctx.to_dict()
        self.assertEqual(result["goap_plan"]["goal"], "survive")
        self.assertFalse(result["llm_adjustment"]["override"])
        self.assertEqual(result["final_action"], "flee")
        self.assertAlmostEqual(result["confidence"], 0.63)


class TestActionResolver(unittest.TestCase):
    """Test ActionResolver resolution logic."""

    def setUp(self) -> None:
        self.resolver = ActionResolver()

    def test_no_plan_returns_idle(self) -> None:
        self.assertEqual(self.resolver.resolve(None, None, None, {}), "idle")

    def test_plan_with_steps_returns_first_step(self) -> None:
        plan = {"goal": "combat", "steps": ["approach", "attack"], "priority": 0.8}
        self.assertEqual(self.resolver.resolve(None, plan, None, {}), "approach")

    def test_empty_steps_returns_idle(self) -> None:
        plan = {"goal": "idle", "steps": [], "priority": 0.1}
        self.assertEqual(self.resolver.resolve(None, plan, None, {}), "idle")

    def test_llm_override_forces_action(self) -> None:
        plan = {"goal": "combat", "steps": ["attack"], "priority": 0.8}
        adj = {"override": True, "override_action": "flee"}
        self.assertEqual(self.resolver.resolve(None, plan, adj, {}), "flee")

    def test_llm_new_goal_replaces_goal(self) -> None:
        plan = {"goal": "explore", "steps": ["walk"], "priority": 0.3}
        adj = {"override": False, "new_goal": "survive", "risk_tolerance": 0.2}
        action = self.resolver.resolve(None, plan, adj, {})
        self.assertEqual(action, "walk")

    def test_emotion_bias_prepends_steps(self) -> None:
        plan = {"goal": "combat", "steps": ["attack"], "priority": 0.8}
        adj = {"override": False, "emotional_bias": "fear"}
        action = self.resolver.resolve(None, plan, adj, {})
        self.assertEqual(action, "flee")


class TestDecisionEngine(unittest.TestCase):
    """Test DecisionEngine orchestration."""

    def test_full_pipeline(self) -> None:
        goap = MagicMock()
        goap.plan.return_value = {
            "goal": "combat",
            "steps": ["approach", "attack"],
            "priority": 0.8,
        }

        llm = MagicMock()
        llm.evaluate_plan.return_value = {
            "override": False,
            "new_goal": None,
            "emotional_bias": None,
            "risk_tolerance": 0.2,
        }

        resolver = ActionResolver()
        engine = DecisionEngine(goap, llm, resolver)

        npc = MagicMock()
        world = {"tick": 1}
        action, debug = engine.decide(npc, world)

        goap.plan.assert_called_once_with(npc, world)
        llm.evaluate_plan.assert_called_once()
        self.assertIn("goap_plan", debug)
        self.assertIn("llm_adjustment", debug)
        self.assertIn("final_action", debug)
        self.assertIn("confidence", debug)
        self.assertEqual(action, "approach")

    def test_llm_override_via_engine(self) -> None:
        goap = MagicMock()
        goap.plan.return_value = {
            "goal": "combat",
            "steps": ["attack"],
            "priority": 0.8,
        }
        llm = MagicMock()
        llm.evaluate_plan.return_value = {
            "override": True,
            "override_action": "flee",
            "risk_tolerance": 0.5,
        }
        resolver = ActionResolver()
        engine = DecisionEngine(goap, llm, resolver)

        action, _ = engine.decide(MagicMock(), {})
        self.assertEqual(action, "flee")

    def test_no_plan_idle(self) -> None:
        goap = MagicMock()
        goap.plan.return_value = {}
        llm = MagicMock()
        llm.evaluate_plan.return_value = {}
        resolver = ActionResolver()
        engine = DecisionEngine(goap, llm, resolver)

        action, debug = engine.decide(MagicMock(), {})
        self.assertEqual(action, "idle")


class TestDecisionEngineConfidence(unittest.TestCase):
    """Verify confidence scoring formula."""

    def test_confidence_formula(self) -> None:
        goap = MagicMock()
        goap.plan.return_value = {"goal": "x", "steps": ["a"], "priority": 0.8}
        llm = MagicMock()
        llm.evaluate_plan.return_value = {"risk_tolerance": 0.25}
        engine = DecisionEngine(goap, llm, ActionResolver())

        _, debug = engine.decide(MagicMock(), {})
        # validity=1.0 (action "a" is valid by default), risk=0.25, priority=0.8
        expected = 0.8 * (1 - 0.25) * 1.0
        self.assertAlmostEqual(debug["confidence"], expected, places=4)


class TestResolverValidityChecks(unittest.TestCase):
    """Test state-aware step selection and validation."""

    def test_selects_first_valid_step(self) -> None:
        resolver = ActionResolver()
        # "find_cover" is invalid (no nearby_cover), "attack" is valid (enemy_visible)
        plan = {"goal": "x", "steps": ["find_cover", "attack", "idle"], "priority": 0.5}
        world = {"enemy_visible": True, "nearby_cover": False}
        action = resolver.resolve(None, plan, {}, world)
        self.assertEqual(action, "attack")

    def test_returns_idle_when_all_steps_invalid(self) -> None:
        resolver = ActionResolver()
        plan = {"goal": "x", "steps": ["find_cover", "flee"], "priority": 0.5}
        world = {"nearby_cover": False, "trapped": True}
        action = resolver.resolve(None, plan, {}, world)
        self.assertEqual(action, "idle")

    def test_custom_validity_checks(self) -> None:
        def allow_swim(npc, ws):
            return ws.get("has_water", False)

        resolver = ActionResolver(validity_checks={"swim": allow_swim})
        plan = {"goal": "x", "steps": ["swim", "idle"], "priority": 0.5}
        self.assertEqual(resolver.resolve(None, plan, {}, {"has_water": True}), "swim")
        self.assertEqual(resolver.resolve(None, plan, {}, {"has_water": False}), "idle")

    def test_plan_not_mutated(self) -> None:
        resolver = ActionResolver()
        plan = {"goal": "x", "steps": ["idle"], "priority": 0.5}
        original = deepcopy(plan)
        resolver.resolve(None, plan, {"emotional_bias": "anger"}, {})
        self.assertEqual(plan, original)

    def test_override_validated(self) -> None:
        """LLM override action must still pass validation."""
        resolver = ActionResolver()
        plan = {"goal": "x", "steps": ["idle"], "priority": 0.5}
        adj = {"override": True, "override_action": "find_cover"}
        # find_cover requires nearby_cover
        action = resolver.resolve(None, plan, adj, {"nearby_cover": False})
        self.assertEqual(action, "idle")

    def test_override_valid_when_conditions_met(self) -> None:
        resolver = ActionResolver()
        plan = {"goal": "x", "steps": ["idle"], "priority": 0.5}
        adj = {"override": True, "override_action": "find_cover"}
        action = resolver.resolve(None, plan, adj, {"nearby_cover": True})
        self.assertEqual(action, "find_cover")


class TestImprovedConfidence(unittest.TestCase):
    """Test the improved confidence formula."""

    def test_zero_confidence_when_invalid_idle(self) -> None:
        goap = MagicMock()
        goap.plan.return_value = {"goal": "x", "steps": ["find_cover"], "priority": 0.8}
        llm = MagicMock()
        llm.evaluate_plan.return_value = {"risk_tolerance": 0.0}
        engine = DecisionEngine(goap, llm, ActionResolver())
        _, debug = engine.decide(MagicMock(), {"nearby_cover": False})
        # idle → validity=0.3, risk=0 → 0.8 * 1.0 * 0.3 = 0.24
        self.assertAlmostEqual(debug["confidence"], 0.24, places=4)

    def test_full_confidence_when_valid(self) -> None:
        goap = MagicMock()
        goap.plan.return_value = {"goal": "x", "steps": ["idle"], "priority": 1.0}
        llm = MagicMock()
        llm.evaluate_plan.return_value = {"risk_tolerance": 0.0}
        engine = DecisionEngine(goap, llm, ActionResolver())
        _, debug = engine.decide(MagicMock(), {})
        # idle is valid (default) → validity=1.0, risk=0 → 1.0 * 1.0 * 1.0 = 1.0
        self.assertAlmostEqual(debug["confidence"], 1.0, places=4)

    def test_reasoning_metadata_present(self) -> None:
        goap = MagicMock()
        goap.plan.return_value = {"goal": "x", "steps": ["find_cover", "idle"], "priority": 0.5}
        llm = MagicMock()
        llm.evaluate_plan.return_value = {"risk_tolerance": 0.2}
        engine = DecisionEngine(goap, llm, ActionResolver())
        _, debug = engine.decide(MagicMock(), {"nearby_cover": False})
        self.assertIn("reasoning", debug)
        self.assertIn("selected_step", debug["reasoning"])
        self.assertIn("rejected_steps", debug["reasoning"])
        self.assertIn("action_valid", debug["reasoning"])


if __name__ == "__main__":
    unittest.main()
