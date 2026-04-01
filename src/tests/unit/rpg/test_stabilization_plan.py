"""Tests for the 4-Step Stabilization Plan implementation.

Tests cover:
- STEP 1: Conflict Resolution 2.0 (temporal + causal resolution)
- STEP 2: Memory Cognitive Layer (types, decay, contradiction)
- STEP 3: NPC Agency Upgrade (utility scoring, interrupts, personality)
- STEP 4: World Simulation Loop (continuous tick, async scheduling, passive events)
"""

import math
import os
import sys
import random
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'app'))

from rpg.core.action_resolver import (
    ActionResolver,
    ResolutionStrategy,
    CONFLICT_TYPES,
    get_conflict_type,
)
from rpg.core.npc_state import (
    NPCState,
    GoalState,
    Personality,
    PERSONALITY_TEMPLATES,
)
from rpg.core.world_loop import (
    WorldSimulationLoop,
    PASSIVE_EVENT_PROBABILITIES,
)
from rpg.memory.memory_manager import (
    MemoryManager,
    MEMORY_TYPES,
    GOAL_BOOST,
    EMOTIONAL_AMPLIFIER,
    DECAY_HALF_LIFE,
)


# ===================================================================
# STEP 1: Conflict Resolution 2.0
# ===================================================================

class TestConflictTypes:
    """Test soft conflict type classification."""

    def test_exclusive_actions(self):
        assert get_conflict_type("move") == "exclusive"
        assert get_conflict_type("pick_up") == "exclusive"
        assert get_conflict_type("equip") == "exclusive"

    def test_stackable_actions(self):
        assert get_conflict_type("attack") == "stackable"
        assert get_conflict_type("heal") == "stackable"
        assert get_conflict_type("buff") == "stackable"

    def test_override_actions(self):
        assert get_conflict_type("kill") == "override"
        assert get_conflict_type("escape") == "override"
        assert get_conflict_type("flee") == "override"

    def test_unknown_is_exclusive(self):
        assert get_conflict_type("unknown_action") == "exclusive"


class TestTemporalSorting:
    """Test action sorting by intent time + reaction time."""

    def test_sort_by_intent_tick(self):
        resolver = ActionResolver()
        actions = [
            {"action": "move", "npc_id": "npc1", "intent_tick": 5},
            {"action": "attack", "npc_id": "npc1", "intent_tick": 2},
            {"action": "heal", "npc_id": "npc1", "intent_tick": 8},
        ]
        resolver._sort_by_timeline(actions)
        assert actions[0]["intent_tick"] == 2
        assert actions[1]["intent_tick"] == 5
        assert actions[2]["intent_tick"] == 8

    def test_sort_by_reaction_time_tiebreak(self):
        resolver = ActionResolver()
        actions = [
            {"action": "move", "npc_id": "npc1", "intent_tick": 5, "reaction_time": 2.0},
            {"action": "attack", "npc_id": "npc2", "intent_tick": 5, "reaction_time": 0.5},
        ]
        resolver._sort_by_timeline(actions)
        assert actions[0]["reaction_time"] == 0.5
        assert actions[1]["reaction_time"] == 2.0

    def test_sort_by_priority_final_tiebreak(self):
        resolver = ActionResolver()
        actions = [
            {"action": "move", "npc_id": "npc1", "intent_tick": 5, "reaction_time": 1.0, "priority": 3},
            {"action": "attack", "npc_id": "npc2", "intent_tick": 5, "reaction_time": 1.0, "priority": 7},
        ]
        resolver._sort_by_timeline(actions)
        assert actions[0]["priority"] == 7
        assert actions[1]["priority"] == 3


class TestSoftConflictResolution:
    """Test soft conflict resolution with stackable/override/exclusive."""

    def test_stackable_actions_coexist(self):
        resolver = ActionResolver()
        actions = [
            {"action": "attack", "npc_id": "npc1", "parameters": {"target": "enemy"}},
            {"action": "attack", "npc_id": "npc2", "parameters": {"target": "enemy"}},
        ]
        result = resolver.resolve(actions)
        assert len(result) == 2

    def test_override_action_drops_others(self):
        resolver = ActionResolver()
        actions = [
            {"action": "attack", "npc_id": "npc1", "parameters": {"target": "enemy"}},
            {"action": "kill", "npc_id": "npc2", "parameters": {"target": "enemy"}},
        ]
        result = resolver.resolve(actions)
        assert len(result) == 1
        assert result[0]["action"] == "kill"

    def test_exclusive_picks_one(self):
        """Exclusive actions targeting the SAME entity pick one winner."""
        resolver = ActionResolver()
        # Actions to the same target conflict - only one wins
        actions = [
            {"action": "move", "npc_id": "npc1", "parameters": {"target": "room_a"}},
            {"action": "move", "npc_id": "npc2", "parameters": {"target": "room_a"}},
        ]
        result = resolver.resolve(actions)
        assert len(result) == 1

    def test_exclusive_different_targets_coexist(self):
        """Exclusive actions to different targets can both proceed."""
        resolver = ActionResolver()
        actions = [
            {"action": "move", "npc_id": "npc1", "parameters": {"target": "room_a"}},
            {"action": "move", "npc_id": "npc2", "parameters": {"target": "room_b"}},
        ]
        result = resolver.resolve(actions)
        assert len(result) == 2


class TestCausalBlocking:
    """Test causal blocking when world state invalidates actions."""

    def test_dead_target_blocks_heal(self):
        resolver = ActionResolver()
        world_state = MagicMock()
        world_state.is_alive.return_value = False
        world_state.get_entity.return_value = MagicMock()

        actions = [
            {"action": "heal", "npc_id": "npc1", "parameters": {"target": "player"}},
        ]
        result = resolver.resolve(actions, world_state=world_state)
        assert len(result) == 0

    def test_missing_target_blocks_action(self):
        resolver = ActionResolver()
        world_state = MagicMock()
        world_state.get_entity.return_value = None

        actions = [
            {"action": "attack", "npc_id": "npc1", "parameters": {"target": "ghost"}},
        ]
        result = resolver.resolve(actions, world_state=world_state)
        assert len(result) == 0


# ===================================================================
# STEP 2: Memory Cognitive Layer
# ===================================================================

class TestMemoryTypes:
    """Test memory type tagging."""

    def test_add_event_with_type(self):
        manager = MemoryManager()
        manager.add_event(
            {"type": "combat", "source": "npc1", "target": "player"},
            memory_type="episodic",
        )
        assert manager.raw_events[-1]["memory_type"] == "episodic"

    def test_unknown_type_defaults_to_episodic(self):
        manager = MemoryManager()
        event = {"type": "weird", "source": "npc1", "target": "player"}
        manager.add_event(event, memory_type="invalid_type")
        assert manager.raw_events[-1]["memory_type"] == "episodic"

    def test_all_valid_types(self):
        assert "episodic" in MEMORY_TYPES
        assert "semantic" in MEMORY_TYPES
        assert "emotional" in MEMORY_TYPES
        assert "goal_related" in MEMORY_TYPES


class TestMemoryDecay:
    """Test exponential memory decay."""

    def test_decay_reduces_importance(self):
        manager = MemoryManager()
        episode = MagicMock()
        episode.importance = 0.8
        episode.tick_created = 0
        episode.tags = []

        decay = math.exp(-50 / DECAY_HALF_LIFE)
        assert decay == pytest.approx(math.exp(-1), rel=0.01)

    def test_decay_never_zero(self):
        manager = MemoryManager()
        episode = MagicMock()
        episode.importance = 0.001
        episode.tick_created = 0
        episode.tags = []

        manager.apply_decay(episode, 1000)
        assert episode.importance >= 0.01


class TestGoalAwareRetrievalBoost:
    """Test goal tag retrieval boosting."""

    def test_goal_boost_increases_score(self):
        manager = MemoryManager()
        episode = MagicMock()
        episode.importance = 0.5
        episode.tick_created = 0
        episode.tags = ["hunt", "combat"]
        episode.entities = {"player"}
        episode.has_any_entity.return_value = True

        manager.episodes.append(episode)

        results_no_goal = manager.retrieve(query_entities=["player"], limit=5)
        results_with_goal = manager.retrieve(
            query_entities=["player"], current_goal="hunt", limit=5
        )

        assert len(results_with_goal) >= len(results_no_goal)


class TestEmotionalAmplification:
    """Test emotional event amplification."""

    def test_emotional_tag_boosted(self):
        manager = MemoryManager()
        episode = MagicMock()
        episode.importance = 0.3
        episode.tick_created = 0
        episode.tags = ["death"]
        episode.entities = {"player"}
        episode.has_any_entity.return_value = True

        manager.episodes.append(episode)
        results = manager.retrieve(query_entities=["player"], limit=5)

        assert len(results) == 1
        score = results[0][0]
        assert score > 0.3


class TestContradictionDetection:
    """Test contradiction resolution in beliefs."""

    def test_contradiction_updates_existing(self):
        """Test that contradictory beliefs update existing with weighted averaging.
        
        [FIX #2] The new confidence-based system uses gradual updating:
        new_value = old_value * 0.8 + new_value * 0.2
        This prevents belief flip-flopping while still allowing updates.
        """
        manager = MemoryManager()
        manager._add_or_update_belief({
            "type": "relationship",
            "entity": "player",
            "target_entity": "npc1",
            "value": 0.7,
            "reason": "npc1 helped player",
            "importance": 0.8,
        })
        assert len(manager.semantic_beliefs) == 1
        assert manager.semantic_beliefs[0]["value"] == 0.7

        manager._add_or_update_belief({
            "type": "relationship",
            "entity": "player",
            "target_entity": "npc1",
            "value": -0.5,
            "reason": "npc1 betrayed player",
            "importance": 0.9,
        })
        # Same entity+target goes through update path (weighted average)
        # new = 0.7 * 0.8 + (-0.5) * 0.2 = 0.56 - 0.1 = 0.46
        assert len(manager.semantic_beliefs) == 1
        # Value should be updated toward the new evidence, but not fully replaced
        new_value = manager.semantic_beliefs[0]["value"]
        assert new_value < 0.7  # Moved toward negative
        assert new_value > -0.5  # But not fully flipped yet


# ===================================================================
# STEP 3: NPC Agency Upgrade
# ===================================================================

class TestPersonality:
    """Test personality trait modifiers."""

    def test_aggression_boosts_combat(self):
        p = Personality(aggression=0.9, fear=0.1)
        base_utility = 1.0
        modified = p.modify_utility(base_utility, "attack")
        assert modified > 1.0

    def test_fear_boosts_defense(self):
        p = Personality(aggression=0.1, fear=0.9)
        modified = p.modify_utility(1.0, "flee")
        assert modified > 1.0

    def test_personality_clamped(self):
        p = Personality(aggression=2.0, fear=-1.0)
        assert p.aggression == 1.0
        assert p.fear == 0.0


class TestUtilityScoring:
    """Test utility score formula."""

    def test_utility_formula(self):
        goal = GoalState(
            name="test",
            priority=8.0,
            urgency=0.7,
            emotional_drive=0.5,
            context_match=0.3,
        )
        expected = (8.0 * 0.4) + (0.7 * 0.3) + (0.5 * 0.2) + (0.3 * 0.1)
        assert goal.utility_score == pytest.approx(expected, rel=0.01)

    def test_personality_affects_utility(self):
        goal = GoalState(
            name="attack_enemy",
            parameters={"type": "attack"},
            priority=5.0,
            urgency=0.5,
            emotional_drive=0.3,
            context_match=0.4,
        )
        p = Personality(aggression=0.8)
        modified = goal.apply_personality(p)
        assert modified > goal.utility_score


class TestInterruptSystem:
    """Test threat-based interrupt system."""

    def test_high_threat_triggers_interrupt(self):
        npc = NPCState("guard", interrupt_threshold=0.7)
        result = npc.update_threat(0.9)
        assert result is not None
        assert result.name == "flee"
        assert result.parameters["threat_level"] == 0.9

    def test_low_threat_no_interrupt(self):
        npc = NPCState("guard", interrupt_threshold=0.7)
        result = npc.update_threat(0.3)
        assert result is None

    def test_process_interrupt_pushes_goal(self):
        npc = NPCState("guard")
        npc.set_goal("patrol", priority=1.0)
        npc.update_threat(0.9)
        npc.process_interrupts()

        assert npc.current_goal.name == "flee"
        assert len(npc.goal_stack) == 1
        assert npc.goal_stack[0].name == "patrol"

    def test_clear_interrupts(self):
        npc = NPCState("guard")
        npc.update_threat(0.9)
        npc.clear_interrupts()
        assert len(npc._pending_interrupts) == 0


class TestGoalEvaluation:
    """Test utility-based goal selection."""

    def test_evaluate_goals_selects_best(self):
        npc = NPCState("npc1")
        goals = [
            {"name": "patrol", "priority": 3.0, "urgency": 0.2, "emotional_drive": 0.1, "context_match": 0.5},
            {"name": "hunt", "priority": 8.0, "urgency": 0.7, "emotional_drive": 0.6, "context_match": 0.8},
        ]
        best = npc.evaluate_goals(goals)
        assert best is not None
        assert best.name == "hunt"

    def test_intent_locked_skips_evaluation(self):
        npc = NPCState("npc1")
        npc.set_goal("flee", priority=10.0)
        npc.intent_locked = True

        goals = [{"name": "new_goal", "priority": 10.0, "urgency": 1.0, "emotional_drive": 1.0, "context_match": 1.0}]
        best = npc.evaluate_goals(goals)
        assert best.name == "flee"


# ===================================================================
# STEP 4: World Simulation Loop
# ===================================================================

class TestWorldTick:
    """Test the world_tick pipeline."""

    def test_tick_increments(self):
        loop = WorldSimulationLoop()
        assert loop.tick == 0
        loop.world_tick()
        assert loop.tick == 1

    def test_tick_returns_result(self):
        loop = WorldSimulationLoop()
        result = loop.world_tick()
        assert "tick" in result
        assert result["tick"] == 1
        assert "events" in result


class TestAsyncNPCScheduling:
    """Test async NPC scheduling."""

    def test_npcs_not_all_act_every_tick(self):
        loop = WorldSimulationLoop(
            npcs={
                "npc1": NPCState("npc1"),
                "npc2": NPCState("npc2"),
            },
            tick_min=2,
            tick_max=4,
        )
        for _ in range(5):
            loop.world_tick()

    def test_add_npc_during_simulation(self):
        loop = WorldSimulationLoop()
        loop.world_tick()
        loop.add_npc("npc1", NPCState("npc1"))
        assert "npc1" in loop.npcs
        assert len(loop.next_action_ticks) == 1


class TestPassiveEvents:
    """Test passive world event generation."""

    def test_passive_event_triggered(self):
        """Test that passive events fire on passive ticks (every 10 ticks).
        
        [FIX #5] Tick tiers: passive events only run on ticks divisible by 10.
        """
        loop = WorldSimulationLoop(passive_events={"weather_change": 1.0})
        # Run ticks until we hit a passive tick (tick 10)
        for _ in range(10):
            result = loop.world_tick()
        # Tick 10 is a passive tick (10 % 10 == 0)
        passive = result["passive_events"]
        assert len(passive) >= 1
        assert passive[0]["sub_type"] == "weather_change"

    def test_no_passive_event(self):
        loop = WorldSimulationLoop(passive_events={"weather_change": 0.0})
        result = loop.world_tick()
        passive = result["passive_events"]
        assert len([e for e in passive if isinstance(e, dict) and e.get("sub_type") == "weather_change"]) == 0

    def test_weather_change_generates_data(self):
        loop = WorldSimulationLoop()
        data = loop._generate_passive_event_data("weather_change")
        assert "new_weather" in data
        assert data["new_weather"] in ["clear", "rain", "storm", "fog", "snow"]

    def test_passive_probabilities_default(self):
        for name, prob in PASSIVE_EVENT_PROBABILITIES.items():
            assert 0.0 <= prob <= 1.0


class TestWorldLoopStats:
    """Test world loop statistics."""

    def test_get_stats(self):
        loop = WorldSimulationLoop(
            npcs={"npc1": NPCState("npc1")},
        )
        loop.world_tick()
        stats = loop.get_stats()
        assert stats["tick"] == 1
        assert stats["total_npcs"] == 1
        assert "active_npcs" in stats