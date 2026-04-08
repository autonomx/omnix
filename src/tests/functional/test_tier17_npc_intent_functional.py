"""Functional Tests for Tier 17 - Dynamic NPC Intent + Opposition System.

This module contains functional tests that verify the integration
of all Tier 17 components working together.
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
from rpg.ai.strategy_profiles import STRATEGY_PROFILES


class TestNPCIntentFunctional:
    """Functional tests for NPC Intent System."""

    def setup_method(self):
        """Set up test fixtures."""
        self.intent_engine = IntentEngine()
        self.opposition_engine = OppositionEngine()
        self.goal_generator = GoalGenerator()
        self.planner = Planner()

    def test_npc_sabotages_quests_over_time(self):
        """Test that NPCs can sabotage quest progress over time."""
        enemy = NPCActor(id="1", name="Enemy", faction="Hostile")
        enemy.traits["aggression"] = 0.8
        world = {"player_reputation": -0.5}

        mock_quest = MagicMock()
        mock_quest.id = "q1"
        mock_quest.arc_progress = 0.8
        mock_quest_engine = MagicMock()
        mock_quest_engine.tracker.get_active_quests.return_value = [mock_quest]

        for tick in range(10):
            enemy.current_plan = [{"type": "sabotage", "weight": 0.9}]
            action = self.intent_engine.update_npc(enemy, world, tick)
            if action and action["action"]["type"] == "sabotage":
                self.opposition_engine.apply(action, mock_quest_engine, world)

        assert mock_quest.arc_progress < 0.8

    def test_npc_allies_with_player(self):
        """Test that friendly NPCs assist the player."""
        ally = NPCActor(id="2", name="Ally", faction="Friendly")
        ally.traits["strategy"] = "diplomatic"
        world = {"player_reputation": 0.8}

        mock_quest = MagicMock()
        mock_quest.id = "q1"
        mock_quest.arc_progress = 0.3
        mock_quest_engine = MagicMock()
        mock_quest_engine.tracker.get_active_quests.return_value = [mock_quest]

        for tick in range(5):
            ally.current_plan = [{"type": "assist", "weight": 0.9}]
            action = self.intent_engine.update_npc(ally, world, tick)
            if action and action["action"]["type"] == "assist":
                self.opposition_engine.apply(action, mock_quest_engine, world)

        assert mock_quest.arc_progress > 0.3

    def test_world_tension_escalates(self):
        """Test that world tension increases with aggressive NPC actions."""
        aggressor = NPCActor(id="3", name="Aggressor", faction="Warlike")
        aggressor.traits["aggression"] = 0.9
        aggressor.traits["strategy"] = "aggressive"
        world = {"global_tension": 0.2}
        mock_quest_engine = MagicMock()
        mock_quest_engine.tracker.get_active_quests.return_value = []

        for tick in range(10):
            aggressor.current_plan = [{"type": "attack", "weight": 0.9}]
            action = self.intent_engine.update_npc(aggressor, world, tick)
            if action and action["action"]["type"] == "attack":
                self.opposition_engine.apply(action, mock_quest_engine, world)

        assert world["global_tension"] > 0.2

    def test_faction_power_changes(self):
        """Test that faction power changes based on NPC actions."""
        npc = NPCActor(id="4", name="Leader", faction="A")
        world = {"factions": {"A": {"power": 0.5}}}
        mock_quest_engine = MagicMock()
        mock_quest_engine.tracker.get_active_quests.return_value = []

        for tick in range(5):
            npc.current_plan = [{"type": "expand", "weight": 0.8}]
            action = self.intent_engine.update_npc(npc, world, tick)
            if action:
                action["faction"] = "A"
                self.opposition_engine.apply(action, mock_quest_engine, world)

        assert world["factions"]["A"]["power"] > 0.5

    def test_player_reputation_changes(self):
        """Test that player reputation changes based on NPC actions."""
        npc = NPCActor(id="5", name="Slanderer", faction="B")
        world = {"player_reputation": 0.5}
        mock_quest_engine = MagicMock()
        mock_quest_engine.tracker.get_active_quests.return_value = []

        for tick in range(3):
            npc.current_plan = [{"type": "frame_player", "weight": 0.8}]
            action = self.intent_engine.update_npc(npc, world, tick)
            if action:
                self.opposition_engine.apply(action, mock_quest_engine, world)

        assert world["player_reputation"] < 0.5


class TestEndToEndSimulation:
    """End-to-end simulation tests."""

    def test_enemy_faction_undermines_player(self):
        """Full simulation of enemy faction undermining player."""
        enemy = NPCActor(id="enemy1", name="Enemy Leader", faction="Enemies")
        enemy.traits["aggression"] = 0.8
        enemy.traits["strategy"] = "aggressive"
        world = {"player_reputation": -0.5, "global_tension": 0.3, "factions": {"Enemies": {"power": 0.7}}}

        mock_quest = MagicMock()
        mock_quest.id = "main_quest"
        mock_quest.arc_progress = 0.5
        mock_quest_engine = MagicMock()
        mock_quest_engine.tracker.get_active_quests.return_value = [mock_quest]

        intent_engine = IntentEngine()
        opposition_engine = OppositionEngine()
        tension_history = []

        for tick in range(20):
            tension_history.append(world["global_tension"])
            action = intent_engine.update_npc(enemy, world, tick)
            if action:
                opposition_engine.apply(action, mock_quest_engine, world)

        assert any(t > 0.3 for t in tension_history)

    def test_friendly_faction_helps_player(self):
        """Full simulation of friendly faction helping player."""
        ally = NPCActor(id="ally1", name="Friendly Ally", faction="Allies")
        ally.traits["strategy"] = "diplomatic"
        ally.traits["aggression"] = 0.2
        world = {"player_reputation": 0.7, "global_tension": 0.2, "factions": {"Allies": {"power": 0.6}}}

        mock_quest = MagicMock()
        mock_quest.id = "help_quest"
        mock_quest.arc_progress = 0.2
        mock_quest_engine = MagicMock()
        mock_quest_engine.tracker.get_active_quests.return_value = [mock_quest]

        intent_engine = IntentEngine()
        opposition_engine = OppositionEngine()

        for tick in range(15):
            ally.current_plan = [{"type": "assist", "weight": 0.9}]
            action = intent_engine.update_npc(ally, world, tick)
            if action:
                opposition_engine.apply(action, mock_quest_engine, world)

        assert mock_quest.arc_progress > 0.2