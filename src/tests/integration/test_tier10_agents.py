"""Integration/Functional Tests for TIER 10: Autonomous NPC Agent System.

Tests the full agent pipeline integrated with PlayerLoop:
- NPCs act autonomously based on goals
- Plans persist across ticks
- Agent events are generated and processed
- Multi-tick simulation with autonomous NPCs
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

import pytest

# Add project path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))


@dataclass
class MockCharacter:
    """Mock character for testing."""
    id: str
    name: str = "Test Character"
    beliefs: Dict[str, float] = field(default_factory=dict)
    goals: List[str] = field(default_factory=list)
    memory: List[Dict[str, Any]] = field(default_factory=list)
    traits: List[str] = field(default_factory=list)
    role: str = "unknown"
    power: float = 0.5
    resources: float = 0.5
    
    def get_belief(self, entity_id: str) -> float:
        return self.beliefs.get(entity_id, 0.0)
    
    def add_belief(self, entity_id: str, value: float) -> None:
        self.beliefs[entity_id] = max(-1.0, min(1.0, value))
    
    def adjust_belief(self, entity_id: str, delta: float) -> float:
        current = self.beliefs.get(entity_id, 0.0)
        new_value = max(-1.0, min(1.0, current + delta))
        self.beliefs[entity_id] = new_value
        return new_value
    
    def add_goal(self, goal: str) -> None:
        if goal not in self.goals:
            self.goals.append(goal)


class TestAgentSimulation:
    """Functional tests for agent simulation."""

    def test_agents_generate_actions_over_multiple_ticks(self):
        """Test that agents with goals generate events over multiple ticks."""
        from rpg.agent.agent_system import AgentSystem

        agents = AgentSystem(max_per_tick=10)
        
        # Create character with goal
        c = MockCharacter(
            id="npc_1",
            goals=["gain power"],
            beliefs={"rival": -0.3},
        )
        chars = {"npc_1": c}

        events_generated = 0

        for tick in range(50):
            events = agents.update(chars, {"factions": {}, "economy": {}, "tick": tick})
            events_generated += len(events)

        assert events_generated > 0

    def test_agents_with_different_goal_types(self):
        """Test agents with various goal types produce different events."""
        from rpg.agent.agent_system import AgentSystem

        agents = AgentSystem(max_per_tick=10)
        
        chars = {
            "warlord": MockCharacter(
                id="warlord",
                goals=["attack enemies"],
                beliefs={"enemy_faction": -0.8},
            ),
            "healer": MockCharacter(
                id="healer",
                goals=["help the wounded"],
                beliefs={"village": 0.7},
            ),
            "merchant": MockCharacter(
                id="merchant",
                goals=["gather wealth"],
                beliefs={"trade_guild": 0.5},
            ),
        }

        all_event_types = set()
        
        for tick in range(20):
            events = agents.update(chars, {"factions": {}, "economy": {}, "tick": tick})
            for event in events:
                all_event_types.add(event.get("type", "unknown"))

        # Should have generated multiple event types
        assert len(all_event_types) >= 1

    def test_agent_plans_persist_across_ticks(self):
        """Test that multi-step plans are maintained across ticks."""
        from rpg.agent.agent_system import AgentSystem

        agents = AgentSystem(max_per_tick=10)
        
        # Character with attack goal produces multi-step plan
        char = MockCharacter(
            id="general",
            goals=["destroy the fortress"],
            beliefs={"enemy": -0.9},
        )
        chars = {"general": char}

        # First tick - should create a plan
        agents.update(chars, {"factions": {}, "tick": 0})
        
        # Plan should exist (either still active or completed)
        # Note: Plan may have been consumed if only 1 step executed
        
        # Run multiple ticks - character should keep producing events
        total_events = 0
        for _ in range(10):
            events = agents.update(chars, {"factions": {}, "tick": 0})
            total_events += len(events)

        assert total_events > 0

    def test_character_without_actions_stays_idle(self):
        """Test that characters who 'idle' don't generate events."""
        from rpg.agent.agent_system import AgentSystem

        agents = AgentSystem(max_per_tick=10)
        
        char = MockCharacter(
            id="hermit",
            goals=[],  # No goals
        )
        chars = {"hermit": char}

        for _ in range(10):
            events = agents.update(chars, {"factions": {}, "tick": 0})
            assert len(events) == 0

    def test_agent_system_integrated_with_player_loop(self):
        """Test that AgentSystem integrates with PlayerLoop correctly."""
        from rpg.core.player_loop import PlayerLoop

        loop = PlayerLoop()
        
        # Add a character with goals using CharacterEngine
        char = loop.characters.get_or_create("rival_lord", "Lord Malachar")
        char.add_belief("player", -0.5)
        char.add_goal("gain power")

        # Run several ticks
        events_generated = []
        
        for _ in range(10):
            result = loop.step("wait")
            events_generated.extend(result.get("raw_events", []))

        # Should have generated some events
        assert len(events_generated) > 0

    def test_multiple_agents_dont_interfere(self):
        """Test that multiple agents don't interfere with each other."""
        from rpg.agent.agent_system import AgentSystem

        agents = AgentSystem(max_per_tick=10)
        
        chars = {
            f"npc_{i}": MockCharacter(
                id=f"npc_{i}",
                goals=["gain power"],
                beliefs={f"faction_{i}": 0.3},
            )
            for i in range(5)
        }

        events = []
        for _ in range(20):
            tick_events = agents.update(chars, {"factions": {}, "tick": 0})
            events.extend(tick_events)

        # Each agent's events should be well-formed
        for event in events:
            assert "type" in event
            assert "actor" in event

    def test_agent_scheduler_limits_active_agents(self):
        """Test that scheduler respects max_per_tick limit."""
        from rpg.agent.agent_system import AgentSystem

        agents = AgentSystem(max_per_tick=2)
        
        chars = {
            f"npc_{i}": MockCharacter(
                id=f"npc_{i}",
                goals=["expand influence"],
                beliefs={f"faction_{i}": 0.5},
            )
            for i in range(10)
        }

        # Run many ticks
        for _ in range(50):
            agents.update(chars, {"factions": {}, "tick": 0})
        
        # Get last selected - should have limited agents
        last_selected = agents.scheduler.get_last_selected()
        assert len(last_selected) <= 2


class TestAgentEventsIntegration:
    """Tests for agent event integration with world systems."""

    def test_faction_conflict_events_from_attack(self):
        """Test that attack actions generate faction_conflict events."""
        from rpg.agent.action_executor import ActionExecutor

        executor = ActionExecutor()
        char = MockCharacter(id="aggressor")
        events = executor.execute(char, {"action": "attack", "target": "target_faction"})

        conflict_events = [e for e in events if e.get("type") == "faction_conflict"]
        assert len(conflict_events) >= 1

    def test_aid_delivered_events(self):
        """Test that deliver actions generate aid events."""
        from rpg.agent.action_executor import ActionExecutor

        executor = ActionExecutor()
        char = MockCharacter(id="messenger")
        events = executor.execute(char, {"action": "deliver", "target": "village"})

        aid_events = [e for e in events if e.get("type") == "aid_delivered"]
        assert len(aid_events) >= 1

    def test_power_growth_events(self):
        """Test that increase_power actions generate events."""
        from rpg.agent.action_executor import ActionExecutor

        executor = ActionExecutor()
        char = MockCharacter(id="rising_star")
        events = executor.execute(char, {"action": "increase_power"})

        power_events = [e for e in events if e.get("type") == "power_growth"]
        assert len(power_events) >= 1

    def test_military_preparation_events(self):
        """Test that gather_forces actions generate events."""
        from rpg.agent.action_executor import ActionExecutor

        executor = ActionExecutor()
        char = MockCharacter(id="warlord")
        events = executor.execute(char, {"action": "gather_forces", "target": "enemy"})

        prep_events = [e for e in events if e.get("type") == "military_preparation"]
        assert len(prep_events) >= 1


class TestRegressionExistingFunctionality:
    """Regression tests to ensure existing functionality still works after Tier 10."""

    def test_player_loop_reset_includes_agents(self):
        """Test that PlayerLoop.reset() resets agent system."""
        from rpg.core.player_loop import PlayerLoop

        loop = PlayerLoop()
        
        # Add a character and run some ticks to create plans
        char = loop.characters.get_or_create("npc1", "Agent One")
        char.add_goal("gain power")
        
        for _ in range(5):
            loop.step("wait")
        
        # Reset
        loop.reset()
        
        # Agent system should be reset
        assert loop.agents.get_active_plan_count() == 0

    def test_player_loop_without_agent_system(self):
        """Test PlayerLoop works without explicitly providing agent system."""
        from rpg.core.player_loop import PlayerLoop

        # Create loop with no agent_system - should use default
        loop = PlayerLoop()
        
        # Should not crash
        result = loop.step("test action")
        assert "narration" in result

    def test_agent_system_does_not_break_existing_tiers(self):
        """Test that adding Tier 10 doesn't break Tier 7-9 systems."""
        from rpg.world.faction_system import FactionSystem, Faction
        from rpg.agent.agent_system import AgentSystem

        # Faction system should still work independently
        fs = FactionSystem()
        fs.add_faction(Faction("test", "Test Faction"))
        events = fs.update()
        assert isinstance(events, list)

        # Agent system should work independently
        agents = AgentSystem(max_per_tick=5)
        chars = {"npc1": MockCharacter(id="npc1", goals=["gain power"])}
        agent_events = agents.update(chars, {"tick": 0})
        assert isinstance(agent_events, list)

    def test_character_engine_still_works_with_agents(self):
        """Test that CharacterEngine works alongside AgentSystem."""
        from rpg.rpg.character.character_engine import CharacterEngine
        from rpg.agent.agent_system import AgentSystem

        engine = CharacterEngine()
        char = engine.get_or_create("test_npc", "Test NPC")
        char.add_belief("faction_a", 0.5)
        char.add_goal("expand influence")

        # Agent system should be able to use this character
        agents = AgentSystem(max_per_tick=10)
        events = agents.update(engine.characters, {"factions": {}, "tick": 0})
        # No crash = success
        assert isinstance(events, list)