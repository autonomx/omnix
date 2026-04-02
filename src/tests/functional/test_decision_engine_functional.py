"""Functional tests for the DecisionEngine pipeline.

These tests verify the integrated behaviour of:
    - GOAP planner producing structured plans.
    - LLM mind evaluating plans.
    - ActionResolver selecting final actions.
    - End-to-end NPC decision cycles.
"""

from __future__ import annotations

import sys
import pathlib
import unittest
from dataclasses import dataclass
from typing import Any, Dict, List

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT / "src" / "app") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src" / "app"))

from rpg.ai.decision.decision_engine import DecisionContext, DecisionEngine
from rpg.ai.decision.resolver import ActionResolver
from rpg.ai.goap.planner import Action as GOAPAction, GOAPPlanner


@dataclass
class DummyNPC:
    """Minimal NPC entity for testing."""
    id: str = "npc_1"
    name: str = "Bob"
    hp: int = 100
    memory: Any = None


class DummyLLMMind:
    """Fake LLM mind for functional testing."""

    def __init__(self, override: bool = False, **adjustments: Any) -> None:
        self._override = override
        self._adjustments = adjustments
        self.call_log: List[Dict[str, Any]] = []

    def evaluate_plan(
        self, npc: Any, plan: Dict[str, Any], world_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        self.call_log.append({"npc": npc, "plan": plan, "world": world_state})
        return {
            "override": self._override,
            "override_action": "flee" if self._override else None,
            "new_goal": self._adjustments.get("new_goal"),
            "emotional_bias": self._adjustments.get("emotional_bias"),
            "risk_tolerance": self._adjustments.get("risk_tolerance", 0.5),
        }


class TestFunctionalDecisionEngine(unittest.TestCase):

    def setUp(self) -> None:
        self.npc = DummyNPC(id="npc_1", name="Bob", hp=80)

    def _make_planner(self) -> GOAPPlanner:
        return GOAPPlanner()

    def test_survival_plan_when_low_hp(self) -> None:
        low_hp_npc = DummyNPC(id="npc_1", hp=10)
        planner = self._make_planner()
        llm = DummyLLMMind()
        engine = DecisionEngine(planner, llm, ActionResolver())

        # World state must include low_hp=True so flee action is applicable
        world = {"safe": False, "low_hp": True}
        action, debug = engine.decide(low_hp_npc, world)

        self.assertEqual(debug["goap_plan"]["goal"], "survive")
        self.assertIsInstance(action, str)

    def test_combat_plan_when_enemies_visible(self) -> None:
        planner = self._make_planner()
        llm = DummyLLMMind()
        engine = DecisionEngine(planner, llm, ActionResolver())

        world = {"enemy_visible": True, "target_in_range": True}
        action, debug = engine.decide(self.npc, world)

        self.assertEqual(debug["goap_plan"]["goal"], "combat")

    def test_default_idle_when_no_goals(self) -> None:
        planner = self._make_planner()
        llm = DummyLLMMind()
        engine = DecisionEngine(planner, llm, ActionResolver())

        world = {}
        action, debug = engine.decide(self.npc, world)

        self.assertEqual(debug["goap_plan"]["goal"], "idle")

    def test_llm_emotion_injects_steps(self) -> None:
        planner = self._make_planner()
        llm = DummyLLMMind(emotional_bias="fear", risk_tolerance=0.3)
        engine = DecisionEngine(planner, llm, ActionResolver())

        world = {}
        npc = DummyNPC(hp=50)
        action, debug = engine.decide(npc, world)

        # Fear should inject "flee" before the default idle step
        self.assertEqual(action, "flee")

    def test_llm_override_combat_to_flee(self) -> None:
        planner = self._make_planner()
        llm = DummyLLMMind(override=True)
        engine = DecisionEngine(planner, llm, ActionResolver())

        world = {"enemy_visible": True}
        action, debug = engine.decide(self.npc, world)

        self.assertEqual(action, "flee")
        self.assertTrue(debug["llm_adjustment"]["override"])

    def test_confidence_reflects_risk(self) -> None:
        planner = self._make_planner()
        llm = DummyLLMMind(risk_tolerance=0.9)
        engine = DecisionEngine(planner, llm, ActionResolver())

        _, debug = engine.decide(self.npc, {})
        self.assertLess(debug["confidence"], 0.5)

    def test_debug_trace_contains_all_stages(self) -> None:
        planner = self._make_planner()
        llm = DummyLLMMind()
        engine = DecisionEngine(planner, llm, ActionResolver())

        _, debug = engine.decide(self.npc, {})
        self.assertIn("goap_plan", debug)
        self.assertIn("llm_adjustment", debug)
        self.assertIn("final_action", debug)
        self.assertIn("confidence", debug)

    def test_multiple_ticks_consistent(self) -> None:
        planner = self._make_planner()
        llm = DummyLLMMind(risk_tolerance=0.1)
        engine = DecisionEngine(planner, llm, ActionResolver())

        actions = set()
        for i in range(10):
            world = {"tick": i, "enemy_visible": (i % 3 == 0)}
            action, _ = engine.decide(self.npc, world)
            actions.add(action)
        self.assertGreater(len(actions), 0)


class TestFunctionalPurePlanner(unittest.TestCase):
    """Verify the GOAP planner returns structured dicts, not side effects."""

    def test_plan_returns_dict(self) -> None:
        planner = GOAPPlanner()
        npc = DummyNPC()
        result = planner.plan(npc, {})

        self.assertIsInstance(result, dict)
        self.assertIn("goal", result)
        self.assertIn("steps", result)
        self.assertIn("priority", result)
        self.assertIsInstance(result["steps"], list)

    def test_plan_no_side_effects(self) -> None:
        planner = GOAPPlanner()
        npc = DummyNPC(hp=80)
        before_hp = npc.hp

        planner.plan(npc, {})

        self.assertEqual(npc.hp, before_hp)


class TestFunctionalResolverEmotions(unittest.TestCase):
    """Test emotional step injection across all emotions."""

    EMOTION_STEPS = {
        "anger": ["attack", "intimidate"],
        "fear": ["flee", "hide", "seek_cover"],
        "joy": ["celebrate", "socialize", "trade"],
        "sadness": ["rest", "retreat", "mourn"],
        "surprise": ["observe", "investigate", "freeze"],
        "trust": ["approach", "help", "share"],
        "disgust": ["avoid", "reject", "withdraw"],
        "anticipation": ["prepare", "plan", "gather_resources"],
    }

    def test_each_emotion_injects_steps(self) -> None:
        resolver = ActionResolver()
        base_plan = {"goal": "x", "steps": ["idle"], "priority": 0.5}

        # World state that allows every emotion action to be valid
        world_state = {
            "enemy_visible": True,
            "ally_nearby": True,
            "nearby_cover": True,
            "trapped": False,
            "has_enemy": True,
        }

        for emotion, expected_steps in self.EMOTION_STEPS.items():
            adj = {"override": False, "emotional_bias": emotion}
            action = resolver.resolve(None, base_plan, adj, world_state)
            self.assertEqual(
                action, expected_steps[0], f"Emotion '{emotion}' failed"
            )

    def test_unknown_emotion_does_not_break(self) -> None:
        resolver = ActionResolver()
        base_plan = {"goal": "x", "steps": ["idle"], "priority": 0.5}
        adj = {"override": False, "emotional_bias": "confusion"}
        action = resolver.resolve(None, base_plan, adj, {})
        self.assertEqual(action, "idle")


if __name__ == "__main__":
    unittest.main()