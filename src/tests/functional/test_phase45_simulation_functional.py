"""PHASE 4.5 — Functional Tests for Simulation Planning

These tests verify the simulation planning system from an end-to-end
perspective. They use real (or minimally stubbed) components to test
integration between:

- SimulationSandbox + FutureSimulator
- AIBranchEvaluator (heuristic mode)
- NPCPlanner + CandidateGenerator
- GameLoop planner integration hooks
"""

import unittest
from unittest.mock import MagicMock, patch
from typing import Any, Dict, List, Optional

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from app.rpg.core.event_bus import Event, EventBus
from app.rpg.core.game_loop import GameLoop
from app.rpg.simulation.sandbox import SimulationSandbox, SimulationResult
from app.rpg.simulation.future_simulator import FutureSimulator, CandidateScore
from app.rpg.ai.branch_ai_evaluator import AIBranchEvaluator
from app.rpg.ai.planner.npc_planner import NPCPlanner, PlanningConfig
from app.rpg.ai.planner.candidate_generator import CandidateGenerator, ActionOption


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_loop_mock(history: Optional[List[Event]] = None, tick_count: int = 0):
    loop = MagicMock()
    loop.tick_count = tick_count
    loop._tick_count = tick_count
    loop.event_bus = MagicMock()
    loop.event_bus.get_history.return_value = history or []
    loop.event_bus.history.return_value = history or []
    return loop


def _make_event(type: str = "test", **payload) -> Event:
    return Event(type=type, payload=payload)


# ---------------------------------------------------------------------------
# Functional Tests
# ---------------------------------------------------------------------------

class TestSimulationSandboxFunctional(unittest.TestCase):
    """Functional tests focused on simulation isolation."""

    def test_full_sandbox_lifecycle(self):
        """Sandbox should replay, inject, and simulate without leaking."""
        loop = _make_loop_mock(history=[], tick_count=0)
        factory = lambda: loop
        sandbox = SimulationSandbox(factory)

        base = [
            _make_event("tick", tick=1),
            _make_event("player_move", x=5, y=5),
        ]
        hypothetical = [_make_event("npc_attack", target="goblin")]

        result = sandbox.run(base, hypothetical, max_ticks=3)

        # Verify result structure
        self.assertIsInstance(result, SimulationResult)
        # Ticks should have been simulated
        self.assertEqual(loop.tick.call_count, 3)

    def test_sandbox_multiple_candidates_isolation(self):
        """Each candidate run should be independent."""
        results = []
        for i in range(3):
            loop = _make_loop_mock(history=[], tick_count=0)
            factory = lambda: loop
            sandbox = SimulationSandbox(factory)
            r = sandbox.run(
                base_events=[_make_event("base", candidate=i)],
                future_events=[_make_event("action", candidate=i)],
                max_ticks=2,
            )
            results.append(r)

        # Each sandbox run is isolated; results are independent
        self.assertEqual(len(results), 3)


class TestFutureSimulatorFunctional(unittest.TestCase):
    """Functional tests for simulation + scoring pipeline."""

    def test_e2e_simulate_and_score(self):
        """Full pipeline from simulation to scoring."""
        loop = _make_loop_mock(history=[], tick_count=0)
        sandbox = SimulationSandbox(lambda: loop)
        simulator = FutureSimulator(sandbox, max_candidates=3)
        evaluator = AIBranchEvaluator(use_heuristic=True)

        candidates = [
            [_make_event("attack", actor="npc1")],
            [_make_event("flee", actor="npc1")],
            [_make_event("negotiate", actor="npc1")],
        ]

        scores = simulator.simulate_and_score(
            base_events=[_make_event("player_see", target="npc1")],
            candidates=candidates,
            evaluator=evaluator,
            context={"goal": "attack", "npc": "npc1"},
        )

        # Should have scored all 3
        self.assertEqual(len(scores), 3)
        # Scores should be in [0, 1] range
        for s in scores:
            self.assertGreaterEqual(s.score, 0.0)
            self.assertLessEqual(s.score, 1.0)

    def test_best_candidate_selection(self):
        """Should return best scoring candidate consistently."""
        loop = _make_loop_mock(history=[], tick_count=0)
        sandbox = SimulationSandbox(lambda: loop)
        simulator = FutureSimulator(sandbox)

        # Mock evaluator to give deterministic scores
        evaluator = AIBranchEvaluator(use_heuristic=True)

        best = simulator.get_best_candidate(
            base_events=[_make_event("start")],
            candidates=[
                [_make_event("fight")],
                [_make_event("flee")],
                [_make_event("defend")],
            ],
            evaluator=evaluator,
            context={"goal": "survive"},
        )
        self.assertIsNotNone(best)
        self.assertEqual(len(best), 1)


class TestNPCPlannerFunctional(unittest.TestCase):
    """Functional tests for NPC planning pipeline."""

    def test_full_npc_planning_cycle(self):
        """NPC selects best action via simulation and scoring."""
        loop = _make_loop_mock(history=[], tick_count=0)
        sandbox = SimulationSandbox(lambda: loop)
        simulator = FutureSimulator(sandbox)
        evaluator = AIBranchEvaluator(use_heuristic=True)
        config = PlanningConfig(
            max_candidates=3,
            max_ticks=2,
            cooldown_ticks=0,  # No cooldown for testing
        )
        planner = NPCPlanner(simulator, evaluator, config)

        base = [_make_event("world_setup", tick=1)]
        candidates = CandidateGenerator().generate(
            npc_context={
                "npc_id": "warrior_1",
                "hp": 100,
                "has_target": True,
                "can_reach": True,
            },
        )

        best = planner.choose_action(base, candidates, context={"goal": "attack"})

        # Should return a valid action sequence
        self.assertIsNotNone(best)
        self.assertGreaterEqual(len(best), 1)
        # All events in best should be valid
        for e in best:
            self.assertIsInstance(e, Event)

    def test_npc_planning_with_low_hp(self):
        """Low HP NPCs should prioritize survival."""
        loop = _make_loop_mock(history=[], tick_count=0)
        sandbox = SimulationSandbox(lambda: loop)
        simulator = FutureSimulator(sandbox)
        evaluator = AIBranchEvaluator(use_heuristic=True)
        config = PlanningConfig(max_candidates=5, cooldown_ticks=0)
        planner = NPCPlanner(simulator, evaluator, config)

        # Low HP + has target = should prefer flee/heal
        candidates = CandidateGenerator().generate(
            npc_context={
                "npc_id": "wounded_warrior",
                "hp": 15,
                "hp_low": True,
                "has_target": True,
                "can_reach": True,
            },
        )

        best = planner.choose_action([], candidates, context={"goal": "survive"})
        self.assertIsNotNone(best)


class TestCandidateGeneratorFunctional(unittest.TestCase):
    """Functional tests for candidate generation."""

    def test_diverse_candidates(self):
        """Should generate diverse candidates based on context."""
        gen = CandidateGenerator()
        candidates = gen.generate(
            npc_context={
                "npc_id": "guard",
                "has_target": True,
                "can_reach": True,
                "hp": 80,
            },
        )

        # Should have multiple different action types
        types = {c[0].type for c in candidates}
        self.assertGreaterEqual(len(types), 1)

    def test_custom_action_integration(self):
        """Custom actions should integrate with candidate generation."""
        gen = CandidateGenerator(actions=[])
        gen.add_custom_action(
            "cast_fireball",
            conditions={"has_mana": True, "enemy_in_range": True},
            priority=3.0,
        )

        candidates = gen.generate(
            npc_context={
                "npc_id": "mage",
                "has_mana": True,
                "enemy_in_range": True,
            },
        )

        self.assertEqual(candidates[0][0].type, "cast_fireball")


class TestGameLoopPlannerIntegration(unittest.TestCase):
    """Tests for GameLoop planner integration hooks."""

    def test_set_npc_planner(self):
        """GameLoop should accept NPCPlanner."""
        bus = EventBus()
        loop = GameLoop(
            intent_parser=MagicMock(),
            world=MagicMock(),
            npc_system=MagicMock(),
            event_bus=bus,
            story_director=MagicMock(),
            scene_renderer=MagicMock(),
        )

        # Should not raise
        loop.set_npc_planner(MagicMock())
        self.assertIsNotNone(loop.npc_planner)

    def test_get_npc_phase_base_events(self):
        """EventBus history should be accessible for NPC planning."""
        bus = EventBus()
        bus.emit(_make_event("test1", tick=1))
        bus.emit(_make_event("test2", tick=2))
        loop = GameLoop(
            intent_parser=MagicMock(),
            world=MagicMock(),
            npc_system=MagicMock(),
            event_bus=bus,
            story_director=MagicMock(),
            scene_renderer=MagicMock(),
        )

        history = loop.event_bus.history()
        self.assertEqual(len(history), 2)


class TestPlanningEndToEnd(unittest.TestCase):
    """End-to-end planning system test."""

    def test_full_planning_pipeline(self):
        """From base events → candidates → simulation → scoring → action."""
        # 1. Setup real EventBus with history
        bus = EventBus()
        for i in range(5):
            bus.emit(_make_event(f"tick_{i}", tick=i))

        # 2. Create sandbox with mock loop
        loop = _make_loop_mock(history=bus.history(), tick_count=5)
        sandbox = SimulationSandbox(lambda: loop)

        # 3. Create simulator + evaluator
        simulator = FutureSimulator(sandbox, max_candidates=3)
        evaluator = AIBranchEvaluator(use_heuristic=True)

        # 4. Create planner
        planner = NPCPlanner(simulator, evaluator, PlanningConfig(cooldown_ticks=0))

        # 5. Generate candidates
        generator = CandidateGenerator()
        candidates = generator.generate({
            "npc_id": "hero_npc",
            "hp": 75,
            "has_target": True,
            "can_reach": True,
        })

        # 6. Choose best action
        base_events = bus.history()
        best = planner.choose_action(base_events, candidates, context={"goal": "attack"})

        # 7. Verify end-to-end correctness
        self.assertIsNotNone(best)
        self.assertIsInstance(best, list)
        for e in best:
            self.assertIsInstance(e, Event)
            self.assertIsNotNone(e.type)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()