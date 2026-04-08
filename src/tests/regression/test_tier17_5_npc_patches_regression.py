"""Regression Tests for Tier 17.5 Patches.

Ensures that the patched functionality remains stable and
doesn't break existing behavior.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))

from rpg.ai.goal_generator import GoalGenerator
from rpg.ai.intent_engine import IntentEngine
from rpg.ai.npc_actor import NPCActor, NPCGoal
from rpg.ai.opposition_engine import OppositionEngine
from rpg.ai.planner import Planner


class TestTier17_5Regression:
    """Regression tests for Tier 17.5 patches."""

    def test_dict_goals_still_work(self):
        """Regression: dict-based goals should still work."""
        npc = NPCActor(id="1", name="Dict", faction="A")
        npc.add_goal({"type": "attack", "priority": 0.8})
        assert len(npc.goals) == 1
        goal = npc.select_highest_priority_goal()
        assert goal is not None
        assert goal["type"] == "attack"

    def test_clear_goals_clears_all(self):
        """Regression: clear_goals should clear all goal types."""
        npc = NPCActor(id="1", name="Clear", faction="A")
        npc.add_goal({"type": "attack", "priority": 0.8})
        npc.add_npc_goal(NPCGoal(id="g1", type="defend", priority=0.5))
        npc.clear_goals()
        assert len(npc.goals) == 0
        assert len(npc.legacy_goals) == 0

    def test_opposition_engine_unchanged(self):
        """Regression: OppositionEngine should work with patched actions."""
        engine = OppositionEngine()
        mock_quest = MagicMock()
        mock_quest.tracker.get_active_quests.return_value = []

        npc_action = {
            "npc_id": "1",
            "action": {"type": "attack"},
        }
        world = {"global_tension": 0.3}

        result = engine.apply(npc_action, mock_quest, world)
        assert world["global_tension"] > 0.3

    def test_planner_unchanged_for_basic_goals(self):
        """Regression: Planner should work with basic goals."""
        planner = Planner()
        npc = NPCActor(id="1", name="Basic", faction="A")
        goal = {"type": "recover_power", "priority": 0.8}
        plan = planner.create_plan(npc, goal)
        assert len(plan) > 0
        assert len(plan) <= 3

    def test_goal_generator_produces_goals(self):
        """Regression: GoalGenerator should produce goals in all cases."""
        gen = GoalGenerator()
        npc = NPCActor(id="1", name="Gen", faction="A")
        goals = gen.generate(npc, {})
        assert len(goals) > 0

    def test_empty_world_still_works(self):
        """Regression: Empty world should not crash."""
        engine = IntentEngine()
        npc = NPCActor(id="1", name="Empty", faction="A")
        action = engine.update_npc(npc, {}, 0)
        # Should either return action or None, not crash
        assert action is None or isinstance(action, dict)

    def test_multiple_npcs_no_interference(self):
        """Regression: Multiple NPCs should not interfere with each other."""
        engine = IntentEngine()
        npcs = [
            NPCActor(id=str(i), name=f"NPC{i}", faction="A")
            for i in range(5)
        ]
        actions = engine.update_all_npcs(npcs, {}, 0)
        # Each NPC should produce at most one action
        assert len(actions) <= 5

    def test_npc_beliefs_are_isolated(self):
        """Regression: NPC beliefs should be isolated between NPCs."""
        npc1 = NPCActor(id="1", name="N1", faction="A")
        npc2 = NPCActor(id="2", name="N2", faction="A")
        npc1.update_belief("trust", 0.5)
        assert npc2.get_belief("trust") == 0.0

    def test_npc_relationships_are_isolated(self):
        """Regression: NPC relationships should be isolated."""
        npc1 = NPCActor(id="1", name="N1", faction="A")
        npc2 = NPCActor(id="2", name="N2", faction="A")
        npc1.update_relationship("3", 0.5)
        assert npc2.get_relationship("3") == 0.0

    def test_failure_memory_limited(self):
        """Regression: Failure memory should not grow unbounded."""
        npc = NPCActor(id="1", name="Mem", faction="A")
        for i in range(100):
            npc.record_failure({"type": "fail"}, {"tick": i})
        assert len(npc.failure_memory) <= 50

    def test_narrative_weight_bounded(self):
        """Regression: Narrative weight should be in [0.0, 1.0]."""
        engine = IntentEngine()
        for action_type in ["attack", "spy", "observe", "unknown"]:
            weight = engine.get_narrative_weight({"type": action_type}, {})
            assert 0.0 <= weight <= 1.0

    def test_long_simulation_stable(self):
        """Regression: Long simulation should not crash or drift."""
        engine = IntentEngine()
        npc = NPCActor(id="1", name="Long", faction="A")
        npc.legacy_goals = [{"type": "observe_player", "priority": 0.5}]

        for tick in range(100):
            action = engine.update_npc(npc, {}, tick)
            assert action is None or "npc_id" in action

    def test_goal_progression_clamped(self):
        """Regression: Goal progress should be clamped to [0.0, 1.0]."""
        goal = NPCGoal(id="g1", type="test", priority=0.5)
        goal.update_progress(2.0)
        assert goal.progress == 1.0

        goal2 = NPCGoal(id="g2", type="test", priority=0.5)
        goal2.update_progress(-1.0)
        assert goal2.progress == 0.0

    def test_relationship_clamped(self):
        """Regression: Relationship values clamped."""
        npc = NPCActor(id="1", name="R", faction="A")
        npc.update_relationship("other", 5.0)
        assert npc.get_relationship("other") == 1.0
        npc.update_relationship("other", -5.0)
        assert npc.get_relationship("other") == -1.0

    def test_existing_tier17_still_works(self):
        """Regression: Existing Tier 17 tests should pass with patches."""
        # Simulate the original test_npc_sabotages_quests_over_time
        enemy = NPCActor(id="1", name="Enemy", faction="Hostile")
        enemy.legacy_goals = [{"type": "undermine_player", "priority": 0.7}]
        enemy.traits["aggression"] = 0.8
        world = {"player_reputation": -0.5}

        mock_quest = MagicMock()
        mock_quest.id = "q1"
        mock_quest.arc_progress = 0.8
        mock_quest_engine = MagicMock()
        mock_quest_engine.tracker.get_active_quests.return_value = [mock_quest]

        intent_engine = IntentEngine()
        opposition_engine = OppositionEngine()

        for tick in range(10):
            enemy.current_plan = [{"type": "sabotage", "weight": 0.9}]
            action = intent_engine.update_npc(enemy, world, tick)
            if action and action["action"]["type"] == "sabotage":
                opposition_engine.apply(action, mock_quest_engine, world)

        assert mock_quest.arc_progress < 0.8