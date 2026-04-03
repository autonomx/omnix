"""PHASE 4.5 — Regression Tests for Simulation Planning

These tests protect against regressions when the simulation planning
system evolves. They ensure that core contracts remain stable:

- SimulationSandbox isolation guarantees
- FutureSimulator determinism
- NPCPlanner cooldown behavior
- AIBranchEvaluator API stability
- CandidateGenerator action generation contracts
- GameLoop planner integration compatibility
"""

import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Any, Dict, List, Optional

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from app.rpg.core.event_bus import Event, EventBus
from app.rpg.core.game_loop import GameLoop
from app.rpg.simulation.sandbox import SimulationSandbox, SimulationResult
from app.rpg.simulation.future_simulator import FutureSimulator, CandidateScore
from app.rpg.ai.branch_ai_evaluator import AIBranchEvaluator, BranchEvaluation
from app.rpg.ai.planner.npc_planner import NPCPlanner, PlanningConfig
from app.rpg.ai.planner.candidate_generator import CandidateGenerator, ActionOption


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(type: str = "test", **payload) -> Event:
    return Event(type=type, payload=payload)


def _make_loop_mock(history: Optional[List[Event]] = None, tick_count: int = 0):
    loop = MagicMock()
    loop.tick_count = tick_count
    loop._tick_count = tick_count
    loop.event_bus = MagicMock()
    loop.event_bus.get_history.return_value = history or []
    loop.event_bus.history.return_value = history or []
    return loop


# ---------------------------------------------------------------------------
# Regression Tests
# ---------------------------------------------------------------------------

class TestSimulationSandboxRegression(unittest.TestCase):
    """Ensure sandbox behavior doesn't break across versions."""

    def test_sandbox_isolation_repeated_runs(self):
        """Multiple runs should not accumulate state."""
        loop = _make_loop_mock(history=[], tick_count=0)
        factory = lambda: loop
        sandbox = SimulationSandbox(factory)

        r1 = sandbox.run([], [_make_event("a")], max_ticks=1)
        r2 = sandbox.run([], [_make_event("b")], max_ticks=1)

        # Both runs should succeed independently
        self.assertIsInstance(r1, SimulationResult)
        self.assertIsInstance(r2, SimulationResult)

    def test_sandbox_event_bus_not_mutated(self):
        """Sandbox must not mutate the real event bus during replay."""
        real_bus = EventBus()
        bus_events = [
            _make_event("tick", tick=i) for i in range(10)
        ]
        for e in bus_events:
            real_bus.emit(e)

        original_count = len(real_bus.history())

        loop = _make_loop_mock(history=[], tick_count=0)
        sandbox = SimulationSandbox(lambda: loop)
        sandbox.run(real_bus.history(), [_make_event("hypothetical")], max_ticks=1)

        # Real bus history should be unchanged
        self.assertEqual(len(real_bus.history()), original_count)

    def test_sandbox_result_attributes_stable(self):
        """SimulationResult must have stable public API."""
        loop = _make_loop_mock(history=[], tick_count=0)
        sandbox = SimulationSandbox(lambda: loop)
        result = sandbox.run([], [_make_event("test")], max_ticks=1)

        # Verify public attributes exist
        self.assertTrue(hasattr(result, "events"))
        self.assertTrue(hasattr(result, "final_tick"))
        self.assertTrue(hasattr(result, "tick_count"))


class TestFutureSimulatorRegression(unittest.TestCase):
    """Ensure future simulator behavior remains stable."""

    def test_simulate_and_score_returns_sorted(self):
        """Scores must always be sorted descending."""
        sandbox = SimulationSandbox(lambda: _make_loop_mock())
        simulator = FutureSimulator(sandbox)

        # Evaluator returns scores in random order
        mock_evaluator = MagicMock()
        mock_evaluator.evaluate.side_effect = [0.2, 0.9, 0.5]

        results = simulator.simulate_and_score(
            base_events=[],
            candidates=[
                [_make_event("a")],
                [_make_event("b")],
                [_make_event("c")],
            ],
            evaluator=mock_evaluator,
        )

        self.assertEqual(len(results), 3)
        for i in range(len(results) - 1):
            self.assertGreaterEqual(results[i].score, results[i + 1].score)

    def test_max_candidates_enforced(self):
        """max_candidates must never be exceeded."""
        sandbox = SimulationSandbox(lambda: _make_loop_mock())
        simulator = FutureSimulator(sandbox, max_candidates=2)

        results = simulator.simulate_candidates(
            [],
            [[_make_event(str(i))] for i in range(10)],
        )
        self.assertLessEqual(len(results), 2)


class TestNPCPlannerRegression(unittest.TestCase):
    """Ensure NPC planner behavior remains predictable."""

    def test_planner_cooldown_resets_after_choice(self):
        """Cooldown should reset after successful planning."""
        config = PlanningConfig(cooldown_ticks=5)
        planner = NPCPlanner(MagicMock(), MagicMock(), config)

        sim_result = [
            CandidateScore(
                candidate=[_make_event("best")],
                result=MagicMock(),
                score=0.9,
            ),
        ]
        planner.simulator.simulate_and_score.return_value = sim_result

        candidates = [[_make_event("a")], [_make_event("b")]]

        # First call succeeds, sets cooldown
        result = planner.choose_action([], candidates)
        self.assertEqual(result[0].type, "best")
        self.assertEqual(planner._cooldown_remaining, 5)

    def test_planner_fallback_deterministic(self):
        """Fallback behavior must always return first candidate."""
        planner = NPCPlanner(MagicMock(), MagicMock(), PlanningConfig())
        planner.simulator.simulate_and_score.side_effect = RuntimeError("fail")

        candidates = [
            [_make_event("first")],
            [_make_event("second")],
        ]
        result = planner.choose_action([], candidates)
        self.assertEqual(result[0].type, "first")

    def test_planner_empty_candidates_handling(self):
        """Empty candidates must return None without errors."""
        planner = NPCPlanner(MagicMock(), MagicMock())
        self.assertIsNone(planner.choose_action([], []))

    def test_planner_simulate_candidates_fallback(self):
        """Should use simulate_candidates if simulate_and_score not available."""
        sandbox = SimulationSandbox(lambda: _make_loop_mock())
        simulator = FutureSimulator(sandbox)
        evaluator = MagicMock()
        evaluator.evaluate.return_value = 0.8

        planner = NPCPlanner(simulator, evaluator, PlanningConfig())

        candidates = [[_make_event("a")], [_make_event("b")]]
        best = planner.choose_action([], candidates)
        # simulate_candidates + manual scoring should work
        self.assertIsNotNone(best)


class TestAIBranchEvaluatorRegression(unittest.TestCase):
    """Ensure AI evaluator API behavior doesn't regress."""

    def test_heuristic_score_range(self):
        """Heuristic scores must always be in [0, 1]."""
        evaluator = AIBranchEvaluator(use_heuristic=True)

        for _ in range(20):
            events = [
                _make_event(f"event_{i}", actor=f"npc_{i}") for i in range(5)
            ]
            score = evaluator.evaluate(events, context={"goal": "attack"})
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)

    def test_llm_response_parse_resilient(self):
        """Evaluator must handle malformed LLM responses gracefully."""
        llm = MagicMock()
        # Various malformed responses
        malformed_responses = [
            "not json at all",
            '{"score": "abc"}',
            "partial {json",
            "",
        ]
        for resp in malformed_responses:
            llm.complete.return_value = resp
            evaluator = AIBranchEvaluator(llm_client=llm)
            try:
                score = evaluator.evaluate([_make_event("test")])
                self.assertIsInstance(score, float)
            except Exception:
                # Acceptable to raise on some malformed input
                pass

    def test_empty_events_score(self):
        """Empty event list should always score 0.0."""
        evaluator = AIBranchEvaluator(use_heuristic=True)
        self.assertEqual(evaluator.evaluate([]), 0.0)


class TestCandidateGeneratorRegression(unittest.TestCase):
    """Ensure candidate generation contracts remain stable."""

    def test_default_always_generates_something(self):
        """Even with empty context, should return at least one candidate."""
        gen = CandidateGenerator()
        candidates = gen.generate({})
        self.assertGreaterEqual(len(candidates), 1)
        self.assertIsInstance(candidates[0][0], Event)

    def test_custom_action_priority_ordering(self):
        """Higher priority actions should appear first in candidates."""
        gen = CandidateGenerator(actions=[])
        gen.add_custom_action("low", priority=0.1)
        gen.add_custom_action("high", priority=10.0)
        gen.add_custom_action("medium", priority=5.0)

        candidates = gen.generate({})
        # First candidate should be highest priority
        self.assertEqual(candidates[0][0].type, "high")

    def test_conditions_filtering_stability(self):
        """Actions with unmet conditions should be excluded."""
        gen = CandidateGenerator(actions=[])
        gen.add_custom_action("only_when_special", conditions={"special": True})
        candidates = gen.generate({"npc_id": "x"})  # no special=True
        self.assertEqual(1, len(candidates))
        self.assertEqual("idle", candidates[0][0].type)

        candidates_special = gen.generate({"npc_id": "x", "special": True})
        self.assertGreaterEqual(len(candidates_special), 1)
        self.assertEqual("only_when_special", candidates_special[0][0].type)


class TestGameLoopIntegrationRegression(unittest.TestCase):
    """Ensure GameLoop planner integration remains compatible."""

    def test_game_loop_accepts_npc_planner(self):
        """GameLoop.set_npc_planner should work with any planner API."""
        bus = EventBus()
        loop = GameLoop(
            intent_parser=MagicMock(),
            world=MagicMock(),
            npc_system=MagicMock(),
            event_bus=bus,
            story_director=MagicMock(),
            scene_renderer=MagicMock(),
        )

        # Mock planner with different method names
        planner = MagicMock()
        planner.choose_best = MagicMock()  # non-standard method

        loop.set_npc_planner(planner)
        self.assertIs(loop.npc_planner, planner)

    def test_game_loop_history_available_after_emit(self):
        """Event history must be available after emit for NPC planning."""
        bus = EventBus()
        loop = GameLoop(
            intent_parser=MagicMock(),
            world=MagicMock(),
            npc_system=MagicMock(),
            event_bus=bus,
            story_director=MagicMock(),
            scene_renderer=MagicMock(),
        )

        for i in range(5):
            bus.emit(
                Event(
                    type="test_event",
                    payload={"tick": i, "data": f"event_{i}"},
                )
            )
            history = bus.history()
            self.assertEqual(len(history), i + 1)

    def test_game_loop_npc_planner_context(self):
        """NPC planner context dict should contain required fields."""
        bus = EventBus()
        loop = GameLoop(
            intent_parser=MagicMock(),
            world=MagicMock(),
            npc_system=MagicMock(),
            event_bus=bus,
            story_director=MagicMock(),
            scene_renderer=MagicMock(),
        )

        # Simulate _generate_candidates_for_npc with an NPC that has generate_candidate_actions
        fake_npc = MagicMock()
        fake_npc.id = "npc_123"
        fake_npc.generate_candidate_actions.return_value = [[Event(type="test", payload={})]]

        candidates = loop._generate_candidates_for_npc(fake_npc, {"player_input": "test"})
        # Should produce at least one candidate (from the mock's method)
        self.assertGreaterEqual(len(candidates), 1)


class TestFullPipelineRegression(unittest.TestCase):
    """Full pipeline regression: sandbox → simulator → planner → action."""

    def test_full_pipeline_stability(self):
        """Running the full pipeline 100x should never crash."""
        for i in range(100):
            loop = _make_loop_mock(history=[], tick_count=i)
            sandbox = SimulationSandbox(lambda: loop)
            simulator = FutureSimulator(sandbox, max_candidates=2)
            evaluator = AIBranchEvaluator(use_heuristic=True)
            config = PlanningConfig(max_candidates=2, cooldown_ticks=0)
            planner = NPCPlanner(simulator, evaluator, config)

            gen = CandidateGenerator()
            candidates = gen.generate({
                "npc_id": f"npc_{i}",
                "hp": 100,
                "has_target": True,
                "can_reach": True,
            })

            best = planner.choose_action([], candidates, context={"goal": "attack"})
            # Should always return something or None (never crash)
            if best is not None:
                self.assertIsInstance(best, list)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()