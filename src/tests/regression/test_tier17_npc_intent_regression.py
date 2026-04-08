"""Regression Tests for Tier 17 - Dynamic NPC Intent + Opposition System.

This module contains regression tests to ensure that changes
to the NPC intent system do not break existing functionality.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

# Add project path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))

from rpg.ai.goal_generator import GoalGenerator
from rpg.ai.intent_engine import IntentEngine
from rpg.ai.npc_actor import NPCActor
from rpg.ai.opposition_engine import OppositionEngine
from rpg.ai.planner import Planner
from rpg.ai.strategy_profiles import (
    STRATEGY_PROFILES,
    get_strategy_profile,
    list_strategies,
)


class TestNPCActorRegression:
    """Regression tests for NPCActor to ensure API stability."""

    def test_npc_actor_dataclass_fields(self):
        npc = NPCActor(id="1", name="Test", faction="A")
        assert hasattr(npc, "id")
        assert hasattr(npc, "name")
        assert hasattr(npc, "faction")
        assert hasattr(npc, "goals")
        assert hasattr(npc, "beliefs")
        assert hasattr(npc, "traits")
        assert hasattr(npc, "current_plan")
        assert hasattr(npc, "last_action_tick")

    def test_npc_actor_methods_exist(self):
        npc = NPCActor(id="1", name="Test", faction="A")
        assert hasattr(npc, "add_goal")
        assert hasattr(npc, "clear_goals")
        assert hasattr(npc, "clear_plan")
        assert hasattr(npc, "update_belief")
        assert hasattr(npc, "get_trait")
        assert hasattr(npc, "select_highest_priority_goal")

    def test_npc_actor_defaults_mutable(self):
        npc1 = NPCActor(id="1", name="Test1", faction="A")
        npc2 = NPCActor(id="2", name="Test2", faction="A")
        npc1.add_goal({"type": "attack", "priority": 0.8})
        assert len(npc1.goals) == 1
        assert len(npc2.goals) == 0


class TestGoalGeneratorRegression:
    """Regression tests for GoalGenerator."""

    def test_goal_generator_api_stable(self):
        gg = GoalGenerator()
        npc = NPCActor(id="1", name="Test", faction="A")
        goals = gg.generate(npc, {})
        assert isinstance(goals, list)

    def test_emergency_goals_api(self):
        gg = GoalGenerator()
        npc = NPCActor(id="1", name="Test", faction="A")
        goals = gg.generate_emergency_goals(npc, 0.9)
        assert isinstance(goals, list)


class TestPlannerRegression:
    """Regression tests for Planner."""

    def test_planner_api_stable(self):
        planner = Planner()
        npc = NPCActor(id="1", name="Test", faction="A")
        plan = planner.create_plan(npc, {"type": "attack", "priority": 0.8})
        assert isinstance(plan, list)

    def test_planner_action_format(self):
        planner = Planner()
        npc = NPCActor(id="1", name="Test", faction="A")
        plan = planner.create_plan(npc, {"type": "recruit", "priority": 0.8})
        for action in plan:
            assert "type" in action


class TestStrategyProfilesRegression:
    """Regression tests for Strategy Profiles."""

    def test_required_profiles_exist(self):
        required = ["aggressive", "diplomatic", "chaotic"]
        for profile_name in required:
            assert profile_name in STRATEGY_PROFILES

    def test_list_strategies_returns_list(self):
        strategies = list_strategies()
        assert isinstance(strategies, list)
        assert len(strategies) > 0


class TestIntentEngineRegression:
    """Regression tests for IntentEngine."""

    def test_intent_engine_api_stable(self):
        engine = IntentEngine()
        npc = NPCActor(id="1", name="Test", faction="A")
        result = engine.update_npc(npc, {"player_reputation": 0.0}, tick=0)
        assert result is None or isinstance(result, dict)

    def test_intent_engine_update_all_npcs(self):
        engine = IntentEngine()
        npcs = [NPCActor(id="1", name="NPC1", faction="A")]
        results = engine.update_all_npcs(npcs, {}, tick=0)
        assert isinstance(results, list)

    def test_intent_engine_force_regeneration(self):
        engine = IntentEngine()
        npc = NPCActor(id="1", name="Test", faction="A")
        engine.force_regeneration(npc, {})

    def test_intent_engine_summary(self):
        engine = IntentEngine()
        npc = NPCActor(id="1", name="Test", faction="A")
        summary = engine.get_npc_intent_summary(npc)
        assert isinstance(summary, dict)


class TestOppositionEngineRegression:
    """Regression tests for OppositionEngine."""

    def test_opposition_engine_api_stable(self):
        engine = OppositionEngine()
        mock_quest = MagicMock()
        mock_quest.tracker.get_active_quests.return_value = []
        result = engine.apply({"npc_id": "1", "action": {"type": "sabotage"}}, mock_quest, {})
        assert isinstance(result, dict)

    def test_opposition_engine_action_effects(self):
        engine = OppositionEngine()
        assert len(engine.ACTION_EFFECTS) > 0
        assert "sabotage" in engine.ACTION_EFFECTS
        assert "assist" in engine.ACTION_EFFECTS
        assert "attack" in engine.ACTION_EFFECTS


class TestIntegrationRegression:
    """Integration regression tests."""

    def test_npc_opposition_changes_outcome(self):
        engine = IntentEngine()
        opposition = OppositionEngine()
        npc = NPCActor(id="1", name="Enemy", faction="A")
        world = {"global_tension": 0.0}
        mock_quest = MagicMock()
        mock_quest.tracker.get_active_quests.return_value = []

        for tick in range(20):
            action = engine.update_npc(npc, world, tick)
            if action:
                action["action"] = {"type": "attack", "weight": 0.9}
                opposition.apply(action, mock_quest, world)

        assert world["global_tension"] != 0.0 or npc.current_plan == []

    def test_npc_belief_updates(self):
        npc = NPCActor(id="1", name="Test", faction="A")
        new_belief = npc.update_belief("player", 0.5)
        assert new_belief == 0.5
        assert npc.beliefs["player"] == 0.5


class TestBackwardsCompatibility:
    """Tests for backwards compatibility with existing RPG systems."""

    def test_npc_actor_compatible_with_mock_quest(self):
        npc = NPCActor(id="1", name="Test", faction="A")
        npc.beliefs["player"] = 0.5
        npc.goals.append({"type": "observe_player", "priority": 0.5})

        mock_quest_engine = MagicMock()
        mock_quest_engine.tracker.get_active_quests.return_value = []
        opposition = OppositionEngine()
        result = opposition.apply({"npc_id": npc.id, "action": {"type": "spy"}}, mock_quest_engine, {})
        assert result["type"] == "npc_action"

    def test_strategy_profiles_importable(self):
        from rpg.ai.strategy_profiles import STRATEGY_PROFILES
        assert isinstance(STRATEGY_PROFILES, dict)

    def test_intent_engine_importable(self):
        from rpg.ai.intent_engine import IntentEngine
        assert IntentEngine is not None

    def test_opposition_engine_importable(self):
        from rpg.ai.opposition_engine import OppositionEngine
        assert OppositionEngine is not None