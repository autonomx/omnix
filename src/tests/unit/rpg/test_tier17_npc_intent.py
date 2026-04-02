"""Unit Tests for Tier 17 - Dynamic NPC Intent + Opposition System.

This module contains unit tests for the NPC intent engine,
goal generator, planner, opposition engine, and strategy profiles.
"""

from __future__ import annotations

import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Add project path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "app"))

from rpg.ai.npc_actor import NPCActor
from rpg.ai.goal_generator import GoalGenerator
from rpg.ai.planner import Planner
from rpg.ai.strategy_profiles import (
    STRATEGY_PROFILES,
    get_strategy_profile,
    get_strategy_bias,
    list_strategies,
)
from rpg.ai.intent_engine import IntentEngine
from rpg.ai.opposition_engine import OppositionEngine


class TestNPCActor:
    """Unit tests for NPCActor."""

    def test_basic_creation(self):
        """Test basic NPC actor creation."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        assert npc.id == "1"
        assert npc.name == "TestNPC"
        assert npc.faction == "A"
        assert npc.goals == []
        assert npc.beliefs == {}
        assert npc.traits == {}
        assert npc.current_plan == []
        assert npc.last_action_tick == 0

    def test_add_goal(self):
        """Test adding goals to NPC."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        npc.add_goal({"type": "attack", "priority": 0.8})
        assert len(npc.goals) == 1
        assert npc.goals[0]["type"] == "attack"
        assert npc.goals[0]["priority"] == 0.8

    def test_clear_goals(self):
        """Test clearing goals."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        npc.add_goal({"type": "attack", "priority": 0.8})
        npc.clear_goals()
        assert len(npc.goals) == 0

    def test_update_belief(self):
        """Test updating beliefs."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        result = npc.update_belief("player", 0.3)
        assert result == 0.3
        assert npc.beliefs["player"] == 0.3

    def test_update_belief_delta(self):
        """Test belief delta updates."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        npc.beliefs["player"] = 0.5
        result = npc.update_belief("player", 0.2)
        assert result == 0.7

    def test_get_trait_default(self):
        """Test trait default values."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        assert npc.get_trait("aggression") == 0.5

    def test_get_trait_custom(self):
        """Test custom trait retrieval."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        npc.traits["aggression"] = 0.8
        assert npc.get_trait("aggression") == 0.8

    def test_select_highest_priority_goal(self):
        """Test selecting highest priority goal."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        npc.add_goal({"type": "defend", "priority": 0.5})
        npc.add_goal({"type": "attack", "priority": 0.8})
        npc.add_goal({"type": "flee", "priority": 0.3})

        goal = npc.select_highest_priority_goal()
        assert goal["type"] == "attack"
        assert goal["priority"] == 0.8

    def test_select_no_goals(self):
        """Test selecting goal when none exist."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        assert npc.select_highest_priority_goal() is None

    def test_repr(self):
        """Test NPC string representation."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        assert "id='1'" in repr(npc)
        assert "name='TestNPC'" in repr(npc)
        assert "faction='A'" in repr(npc)


class TestGoalGenerator:
    """Unit tests for GoalGenerator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.generator = GoalGenerator()

    def test_generate_empty_world(self):
        """Test goal generation with empty world."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        goals = self.generator.generate(npc, {})
        assert len(goals) > 0

    def test_generate_faction_power_low(self):
        """Test goal generation when faction power is low."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        world = {
            "factions": {
                "A": {"power": 0.5},
            },
        }
        goals = self.generator.generate(npc, world)
        goal_types = [g["type"] for g in goals]
        assert "recover_power" in goal_types

    def test_generate_faction_power_high(self):
        """Test goal generation when faction power is high."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        world = {
            "factions": {
                "A": {"power": 0.95},
            },
        }
        goals = self.generator.generate(npc, world)
        goal_types = [g["type"] for g in goals]
        assert "maintain_dominance" in goal_types

    def test_generate_player_reputation_high(self):
        """Test goal generation with high player reputation."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        world = {"player_reputation": 0.8}
        goals = self.generator.generate(npc, world)
        goal_types = [g["type"] for g in goals]
        assert "ally_player" in goal_types

    def test_generate_player_reputation_low(self):
        """Test goal generation with low player reputation."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        world = {"player_reputation": -0.5}
        goals = self.generator.generate(npc, world)
        goal_types = [g["type"] for g in goals]
        assert "undermine_player" in goal_types

    def test_generate_world_tension_high(self):
        """Test goal generation with high world tension."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        world = {"global_tension": 0.8}
        goals = self.generator.generate(npc, world)
        goal_types = [g["type"] for g in goals]
        assert "survive" in goal_types

    def test_generate_high_aggression_npc(self):
        """Test goal generation with aggressive NPC."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        npc.traits["aggression"] = 0.9
        goals = self.generator.generate(npc, {})
        goal_types = [g["type"] for g in goals]
        assert "aggressive_expansion" in goal_types

    def test_generate_high_curiosity_npc(self):
        """Test goal generation with curious NPC."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        npc.traits["curiosity"] = 0.9
        goals = self.generator.generate(npc, {})
        goal_types = [g["type"] for g in goals]
        assert "explore" in goal_types

    def test_generate_emergency_goals_high_threat(self):
        """Test emergency goal generation with high threat."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        goals = self.generator.generate_emergency_goals(npc, 0.9)
        assert len(goals) == 1
        assert goals[0]["type"] == "flee"

    def test_generate_emergency_goals_medium_threat(self):
        """Test emergency goal generation with medium threat."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        goals = self.generator.generate_emergency_goals(npc, 0.6)
        assert len(goals) == 1
        assert goals[0]["type"] == "defend"

    def test_generate_emergency_goals_low_threat(self):
        """Test emergency goal generation with low threat."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        goals = self.generator.generate_emergency_goals(npc, 0.3)
        assert len(goals) == 0


class TestPlanner:
    """Unit tests for Planner."""

    def setup_method(self):
        """Set up test fixtures."""
        self.planner = Planner()

    def test_create_plan_recover_power(self):
        """Test plan creation for recover_power goal."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        goal = {"type": "recover_power", "priority": 0.8}
        plan = self.planner.create_plan(npc, goal)
        assert len(plan) > 0
        assert len(plan) <= 3  # Max 3 actions

    def test_create_plan_undermine_player(self):
        """Test plan creation for undermine_player goal."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        npc.traits["strategy"] = "diplomatic"
        goal = {"type": "undermine_player", "priority": 0.7}
        plan = self.planner.create_plan(npc, goal)
        assert len(plan) > 0
        action_types = [a["type"] for a in plan]
        assert "spy" in action_types or "sabotage" in action_types

    def test_create_plan_ally_player(self):
        """Test plan creation for ally_player goal."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        goal = {"type": "ally_player", "priority": 0.6}
        plan = self.planner.create_plan(npc, goal)
        assert len(plan) > 0
        action_types = [a["type"] for a in plan]
        assert "assist" in action_types or "gift" in action_types

    def test_create_plan_unknown_goal(self):
        """Test plan creation for unknown goal type."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        goal = {"type": "unknown_type", "priority": 0.5}
        plan = self.planner.create_plan(npc, goal)
        assert len(plan) > 0
        assert plan[0]["type"] == "observe"

    def test_create_plan_aggressive_strategy(self):
        """Test plan creation with aggressive strategy."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        npc.traits["strategy"] = "aggressive"
        npc.traits["aggression"] = 0.9
        goal = {"type": "aggressive_expansion", "priority": 0.7}
        plan = self.planner.create_plan(npc, goal)
        action_types = [a["type"] for a in plan]
        assert any(a in action_types for a in ["attack", "conquer", "raze"])

    def test_create_plan_diplomatic_strategy(self):
        """Test plan creation with diplomatic strategy."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        npc.traits["strategy"] = "diplomatic"
        goal = {"type": "ally_player", "priority": 0.7}
        plan = self.planner.create_plan(npc, goal)
        assert len(plan) > 0

    def test_create_plan_target_faction_set(self):
        """Test plan actions have target faction set."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        goal = {"type": "recover_power", "priority": 0.8}
        plan = self.planner.create_plan(npc, goal)
        for action in plan:
            assert action.get("target_faction") == "A"


class TestStrategyProfiles:
    """Unit tests for Strategy Profiles."""

    def test_aggressive_profile(self):
        """Test aggressive strategy profile."""
        profile = get_strategy_profile("aggressive")
        assert profile["attack_bias"] == 1.5
        assert profile["diplomacy_bias"] == 0.5

    def test_diplomatic_profile(self):
        """Test diplomatic strategy profile."""
        profile = get_strategy_profile("diplomatic")
        assert profile["attack_bias"] == 0.5
        assert profile["diplomacy_bias"] == 1.5

    def test_chaotic_profile(self):
        """Test chaotic strategy profile."""
        profile = get_strategy_profile("chaotic")
        assert profile["randomness"] == 0.5

    def test_unknown_profile_returns_default(self):
        """Test unknown strategy returns diplomatic default."""
        profile = get_strategy_profile("unknown")
        assert profile == get_strategy_profile("diplomatic")

    def test_get_strategy_bias(self):
        """Test get_strategy_bias function."""
        bias = get_strategy_bias("aggressive")
        assert bias["attack_bias"] == 1.5

    def test_list_strategies(self):
        """Test listing all strategies."""
        strategies = list_strategies()
        assert "aggressive" in strategies
        assert "diplomatic" in strategies
        assert "chaotic" in strategies


class TestIntentEngine:
    """Unit tests for IntentEngine."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = IntentEngine()

    def test_update_npc_basic(self):
        """Test basic NPC update."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        world = {"player_reputation": -0.5}
        result = self.engine.update_npc(npc, world, tick=0)
        assert result is not None
        assert result["npc_id"] == "1"
        assert "action" in result
        assert "goal" in result

    def test_update_npc_no_change_tick(self):
        """Test NPC update with same tick."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        world = {}
        result1 = self.engine.update_npc(npc, world, tick=1)
        result2 = self.engine.update_npc(npc, world, tick=1)
        assert result2 is not None

    def test_update_npc_goal_regeneration(self):
        """Test goal regeneration after interval."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        world = {}
        result1 = self.engine.update_npc(npc, world, tick=0)
        for _ in range(5):
            npc.current_plan = []
            self.engine.update_npc(npc, world, tick=100)
        assert len(npc.goals) > 0

    def test_update_all_npcs(self):
        """Test updating multiple NPCs."""
        npc1 = NPCActor(id="1", name="NPC1", faction="A")
        npc2 = NPCActor(id="2", name="NPC2", faction="B")
        world = {"player_reputation": -0.5}
        results = self.engine.update_all_npcs([npc1, npc2], world, tick=0)
        assert len(results) == 2

    def test_get_npc_intent_summary(self):
        """Test intent summary generation."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        npc.add_goal({"type": "attack", "priority": 0.8})
        summary = self.engine.get_npc_intent_summary(npc)
        assert summary["npc_id"] == "1"
        assert summary["npc_name"] == "TestNPC"
        assert summary["faction"] == "A"
        assert summary["goal_count"] == 1

    def test_force_regeneration(self):
        """Test forced goal regeneration."""
        npc = NPCActor(id="1", name="TestNPC", faction="A")
        npc.goals = [{"type": "old", "priority": 0.1}]
        world = {"player_reputation": -0.5}
        self.engine.force_regeneration(npc, world)
        assert len(npc.goals) > 0


class TestOppositionEngine:
    """Unit tests for OppositionEngine."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = OppositionEngine()

    def test_apply_sabotage(self):
        """Test sabotage action application."""
        mock_quest = MagicMock()
        mock_quest.tracker = MagicMock()
        mock_quest.tracker.get_active_quests.return_value = []

        npc_action = {
            "npc_id": "1",
            "action": {"type": "sabotage"},
        }
        world = {}

        result = self.engine.apply(npc_action, mock_quest, world)
        assert result["type"] == "npc_action"
        assert result["action"] == "sabotage"

    def test_apply_assist(self):
        """Test assistance action application."""
        mock_quest = MagicMock()
        mock_quest.tracker = MagicMock()
        mock_quest.tracker.get_active_quests.return_value = []

        npc_action = {
            "npc_id": "1",
            "action": {"type": "assist"},
        }
        world = {}

        result = self.engine.apply(npc_action, mock_quest, world)
        assert result["action"] == "assist"

    def test_apply_attack_increases_tension(self):
        """Test attack action increases tension."""
        mock_quest = MagicMock()
        mock_quest.tracker = MagicMock()
        mock_quest.tracker.get_active_quests.return_value = []

        npc_action = {
            "npc_id": "1",
            "action": {"type": "attack"},
        }
        world = {"global_tension": 0.3}

        result = self.engine.apply(npc_action, mock_quest, world)
        assert world["global_tension"] > 0.3

    def test_apply_gift_improves_reputation(self):
        """Test gift action improves reputation."""
        mock_quest = MagicMock()
        mock_quest.tracker = MagicMock()
        mock_quest.tracker.get_active_quests.return_value = []

        npc_action = {
            "npc_id": "1",
            "action": {"type": "gift"},
        }
        world = {"player_reputation": 0.2}

        result = self.engine.apply(npc_action, mock_quest, world)
        assert world["player_reputation"] > 0.2

    def test_apply_frame_player_damages_reputation(self):
        """Test frame_player damages reputation."""
        mock_quest = MagicMock()
        mock_quest.tracker = MagicMock()
        mock_quest.tracker.get_active_quests.return_value = []

        npc_action = {
            "npc_id": "1",
            "action": {"type": "frame_player"},
        }
        world = {"player_reputation": 0.3}

        result = self.engine.apply(npc_action, mock_quest, world)
        assert world["player_reputation"] < 0.3

    def test_apply_spread_rumors(self):
        """Test spread rumors action."""
        mock_quest = MagicMock()
        mock_quest.tracker = MagicMock()
        mock_quest.tracker.get_active_quests.return_value = []

        npc_action = {
            "npc_id": "1",
            "action": {"type": "spread_rumors"},
        }
        world = {"global_tension": 0.3, "player_reputation": 0.3}

        result = self.engine.apply(npc_action, mock_quest, world)
        assert world["global_tension"] >= 0.3
        assert world["player_reputation"] <= 0.3

    def test_apply_unknown_action(self):
        """Test applying unknown action."""
        mock_quest = MagicMock()
        mock_quest.tracker = MagicMock()
        mock_quest.tracker.get_active_quests.return_value = []

        npc_action = {
            "npc_id": "1",
            "action": {"type": "unknown_action"},
        }
        world = {}

        result = self.engine.apply(npc_action, mock_quest, world)
        assert result["action"] == "unknown_action"

    def test_sabotage_quest_progress(self):
        """Test sabotage reduces quest progress."""
        mock_quest = MagicMock()
        mock_quest.id = "q1"
        mock_quest.arc_progress = 0.5

        mock_quest2 = MagicMock()
        mock_quest2.id = "q2"
        mock_quest2.arc_progress = 0.3

        mock_engine = MagicMock()
        mock_engine.tracker.get_active_quests.return_value = [mock_quest, mock_quest2]

        npc_action = {
            "npc_id": "1",
            "action": {"type": "sabotage"},
        }
        world = {}

        self.engine.apply(npc_action, mock_engine, world)
        assert mock_quest.arc_progress < 0.5
        assert mock_quest2.arc_progress < 0.3

    def test_assist_quest_progress(self):
        """Test assistance increases quest progress."""
        mock_quest = MagicMock()
        mock_quest.id = "q1"
        mock_quest.arc_progress = 0.5

        mock_engine = MagicMock()
        mock_engine.tracker.get_active_quests.return_value = [mock_quest]

        npc_action = {
            "npc_id": "1",
            "action": {"type": "assist"},
        }
        world = {}

        self.engine.apply(npc_action, mock_engine, world)
        assert mock_quest.arc_progress > 0.5

    def test_tension_capped_at_1(self):
        """Test tension doesn't exceed 1.0."""
        mock_quest = MagicMock()
        mock_quest.tracker.get_active_quests.return_value = []

        npc_action = {
            "npc_id": "1",
            "action": {"type": "attack"},
        }
        world = {"global_tension": 0.95}

        self.engine.apply(npc_action, mock_quest, world)
        assert world["global_tension"] <= 1.0

    def test_reputation_capped_at_bounds(self):
        """Test reputation stays within [-1, 1]."""
        mock_quest = MagicMock()
        mock_quest.tracker.get_active_quests.return_value = []

        npc_action = {
            "npc_id": "1",
            "action": {"type": "gift"},
        }
        world = {"player_reputation": 0.95}

        self.engine.apply(npc_action, mock_quest, world)
        assert world["player_reputation"] <= 1.0