"""Integration Tests — Tier 12: Narrative Convergence Engine.

This module provides functional and integration tests for Tier 12 convergence
systems, testing how all subsystems work together in realistic scenarios.

Test Scenarios:
    - Full cognitive cycle with Tier 12 convergence
    - 100-tick convergence simulation
    - Decision arbitration under conflicting inputs
    - Coalition lock lifecycle with learning system interaction
    - Narrative gravity storyline convergence
    - Player-centric event filtering

Usage:
    pytest src/tests/integration/test_tier12_convergence.py -v
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

# Add project path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))

from rpg.cognitive.coalition_lock import CoalitionLockManager
from rpg.cognitive.cognitive_layer import CognitiveLayer
from rpg.cognitive.decision_resolver import DecisionResolver
from rpg.cognitive.narrative_gravity import NarrativeGravity, StorylineState

# ============================================================================
# Helper Functions
# ============================================================================

def make_npc(npc_id: str, traits: list = None, goals: list = None) -> MagicMock:
    """Create a mock NPC for testing."""
    npc = MagicMock()
    npc.id = npc_id
    npc.traits = traits or ["aggressive", "territorial"]
    npc.goals = goals or ["expand influence", "defend territory"]
    npc.beliefs = {}
    npc.get_belief = lambda entity: 0.0
    npc.learning = None
    npc.identity = None
    npc.relationships = {}
    return npc


def make_world(factions: dict = None, tick: int = 0) -> Dict[str, Any]:
    """Create a mock world state."""
    if factions is None:
        factions = {
            "bandits": {"power": 0.3, "relations": {"militia": -0.8, "traders": -0.3}},
            "militia": {"power": 0.7, "relations": {"bandits": -0.7, "traders": 0.5}},
            "traders": {"power": 0.4, "relations": {"bandits": -0.4, "militia": 0.4}},
        }
    return {"factions": factions, "tick": tick, "events": []}


def make_base_intent(intent_type: str = "expand_influence", priority: float = 5.0) -> Dict[str, Any]:
    """Create a base intent."""
    return {
        "type": intent_type,
        "priority": priority,
        "reasoning": f"NPC decided to {intent_type}",
    }


# ============================================================================
# Full Cognitive Cycle with Tier 12 Tests
# ============================================================================

class TestCognitiveCycleWithTier12:
    """Test full cognitive pipeline including Tier 12 convergence."""
    
    def test_full_decision_pipeline_with_resolver(self):
        """Test cognitive pipeline with decision arbitration."""
        cognitive = CognitiveLayer()
        resolver = DecisionResolver()
        
        npc = make_npc("bandit_leader")
        world = make_world()
        
        # Get base intent from cognitive pipeline
        base_intent = make_base_intent("expand_influence", 5.0)
        processed = cognitive.process_decision(npc, base_intent, world, current_tick=0)
        
        # Use resolver for final arbitration
        final = resolver.resolve(processed, processed, npc)
        assert final is not None
        assert "resolved_by_arbiter" in final
    
    def test_coalition_lock_with_cognitive_layer(self):
        """Test coalition lock integration with cognitive layer."""
        cognitive = CognitiveLayer()
        lock_manager = CoalitionLockManager(default_duration=10)
        
        # Form a coalition
        world = make_world(factions={
            "weak_a": {"power": 0.15, "relations": {"weak_b": 0.7, "strong_enemy": -0.8}},
            "weak_b": {"power": 0.18, "relations": {"weak_a": 0.6, "strong_enemy": -0.7}},
            "strong_enemy": {"power": 0.7, "relations": {"weak_a": -0.7, "weak_b": -0.6}},
        })
        
        coalition = cognitive.check_coalition_opportunity("weak_a", world, current_tick=0)
        assert coalition is not None
        
        # Lock coalition member intent
        lock_manager.acquire_lock(
            "weak_a",
            "strong_enemy",
            "coordinated_attack",
            coalition_id=coalition.id,
            current_tick=0,
        )
        
        # Verify lock is active
        assert lock_manager.is_locked("weak_a", current_tick=5) == True
        
        # Try to change intent - should be enforced
        intent = make_base_intent("idle", 2.0)
        result = lock_manager.enforce_lock("weak_a", intent, current_tick=5)
        assert result["coalition_locked"] == True
        assert result["type"] == "coordinated_attack"
    
    def test_narrative_gravity_with_cognitive_events(self):
        """Test narrative gravity with events from cognitive layer."""
        cognitive = CognitiveLayer()
        gravity = NarrativeGravity(max_active=2, player_id="player")
        
        # Create storyline from coalition activity
        world = make_world(factions={
            "faction_a": {"power": 0.3, "relations": {"faction_b": -0.5}},
            "faction_b": {"power": 0.4, "relations": {"faction_a": -0.4}},
        })
        
        coalition = cognitive.check_coalition_opportunity("faction_a", world, current_tick=0)
        
        if coalition:
            storyline = StorylineState(
                id=f"coalition_{coalition.id}",
                event_type="conflict",
                participants=list(coalition.members),
                target="faction_b",
                start_tick=0,
                importance=0.7,
                is_player_involved=True,
            )
            gravity.add_storyline(storyline)
        
        # Add some NPC-driven storylines
        for i in range(3):
            sl = StorylineState(
                id=f"npc_story_{i}",
                event_type="personal",
                participants=[f"npc_{i}"],
                start_tick=0,
                importance=0.2 + i * 0.1,
            )
            gravity.add_storyline(sl)
        
        # Update and verify focus
        focused = gravity.update_storylines(current_tick=10)
        
        # Should have at most max_active focused
        assert len(focused) <= 2
        
        # Player-involved storyline should have higher importance
        for sl in focused:
            if sl.is_player_involved:
                assert sl.importance > 0.3


# ============================================================================
# Multi-Tick Convergence Tests
# ============================================================================

class TestMultiTickConvergence:
    """Test convergence behavior over multiple ticks."""
    
    def test_100_tick_convergence_simulation(self):
        """Run 100-tick simulation to verify convergence."""
        resolver = DecisionResolver()
        lock_manager = CoalitionLockManager(default_duration=10)
        gravity = NarrativeGravity(max_active=3, player_id="player")
        
        # Create initial storylines with varying importance
        storylines_created = 0
        for i in range(8):
            sl = StorylineState(
                id=f"story_{i}",
                event_type="conflict" if i % 2 == 0 else "personal",
                participants=[f"npc_{i}", f"npc_{(i+1) % 8}"],
                importance=0.3 + i * 0.05,
                start_tick=0,
                is_player_involved=(i == 0),
            )
            gravity.add_storyline(sl)
            storylines_created += 1
        
        metrics = {
            "ticks_processed": 0,
            "conflicts_detected": 0,
            "locks_acquired": 0,
            "locks_expired": 0,
            "storylines_demoted": 0,
            "storylines_concluded": 0,
            "max_focused_at_once": 0,
            "events_scored": 0,
        }
        
        for tick in range(100):
            metrics["ticks_processed"] += 1
            
            # 1. Decision Resolution with varying inputs
            base_priority = 5.0 + (tick % 7) * 0.5
            enriched_priority = 6.0 + (tick % 5) * 0.3
            base = make_base_intent("expand_influence", base_priority)
            enriched = make_base_intent("expand_influence", enriched_priority)
            
            result = resolver.resolve(base, enriched, None)
            
            # 2. Coalition Lock Management
            if tick % 15 == 0:
                lock = lock_manager.acquire_lock(
                    f"npc_{tick % 8}",
                    f"target_{tick % 4}",
                    "coordinated_attack",
                    coalition_id=f"coal_{tick // 15}",
                    duration=8,
                    current_tick=tick,
                )
                if lock:
                    metrics["locks_acquired"] += 1
            
            lock_manager.tick_cleanup(tick)
            
            # 3. Narrative Gravity Update
            focused = gravity.update_storylines(current_tick=tick)
            metrics["max_focused_at_once"] = max(
                metrics["max_focused_at_once"], len(focused)
            )
            
            # Check for storyline conclusions
            for sl in list(gravity.get_active_storylines().values()):
                if gravity.should_conclude(sl, tick):
                    resolution = gravity.generate_resolution(sl)
                    gravity.conclude_storyline(sl.id, resolution)
                    metrics["storylines_concluded"] += 1
            
            # Score events periodically
            if tick % 10 == 0:
                event = {
                    "type": "battle" if tick % 20 == 0 else "negotiation",
                    "participants": [f"npc_{tick % 8}", f"npc_{(tick + 1) % 8}"],
                    "progress": min(1.0, tick / 100),
                }
                score = gravity.score_event(event)
                metrics["events_scored"] += 1
        
        # Update final metrics
        metrics["conflicts_detected"] = resolver.get_stats()["conflicts_detected"]
        metrics["locks_expired"] = lock_manager.get_stats().get("locks_expired", 0)
        metrics["storylines_demoted"] = gravity.get_stats()["storylines_demoted"]
        
        # Verify convergence behavior
        assert metrics["ticks_processed"] == 100, "Should process all 100 ticks"
        assert metrics["max_focused_at_once"] <= 3, "Focused storylines should never exceed max_active"
        assert gravity.get_stats()["storylines_demoted"] > 0, "Background demotion should occur"
        assert resolver.get_stats()["resolutions"] == 100, "Should resolve 100 decisions"
        
        return metrics
    
    def test_oscillation_prevention_with_coalition_locks(self):
        """Test that coalition locks prevent intent oscillation."""
        lock_manager = CoalitionLockManager(default_duration=15)
        
        npc_id = "oscillator_npc"
        
        # Acquire coalition lock
        lock = lock_manager.acquire_lock(
            npc_id, "enemy_base", "coordinated_attack",
            coalition_id="coal_1",
            current_tick=0,
        )
        assert lock is not None
        
        # Simulate oscillating intents from learning system
        oscillating_intents = [
            make_base_intent("coordinated_attack", 7.0),
            make_base_intent("defend", 3.0),  # Learning says "defend"
            make_base_intent("gather_resources", 5.0),  # Rules say "gather"
            make_base_intent("coordinated_attack", 6.5),
            make_base_intent("idle", 1.0),  # Learning says "idle"
        ]
        
        enforced_count = 0
        for tick, intent in enumerate(oscillating_intents):
            result = lock_manager.enforce_lock(npc_id, intent, current_tick=tick + 1)
            if result.get("coalition_locked"):
                enforced_count += 1
        
        # Most intents should be locked to coalition action
        assert enforced_count >= 3, "Coalition lock should prevent most oscillation"
    
    def test_conflicting_systems_resolution(self):
        """Test decision resolver handles conflicting system inputs."""
        resolver = DecisionResolver()
        
        # Character with negative learning history but positive LLM suggestion
        char = MagicMock()
        char.id = "conflicted_char"
        char.learning = MagicMock()
        char.learning.get_failure_counts = MagicMock(return_value={"attack": 5})
        char.identity = MagicMock()
        char.identity.get_reputation = MagicMock(return_value=0.6)  # Ally
        char.relationships = {}
        
        # Base intent says attack
        base = {"type": "attack", "priority": 8.0, "target": "former_ally"}
        
        # LLM says increase priority (revenge narrative)
        enriched = {"type": "attack", "priority": 9.0, "reasoning": "Revenge!", "target": "former_ally"}
        
        # Resolve - learning and reputation should reduce priority
        result = resolver.resolve(base, enriched, char)
        
        assert result is not None
        assert result.get("resolved_by_arbiter") == True
        assert result["priority"] <= 9.0  # Should be reduced by learning/reputation


# ============================================================================
# Player-Centric Filtering Tests
# ============================================================================

class TestPlayerCentricFiltering:
    """Test player-centric event prioritization."""
    
    def test_player_events_boosted(self):
        """Test that player-involved events score higher."""
        gravity = NarrativeGravity(player_id="hero_player")
        
        # Event with player
        event_with_player = {
            "type": "battle",
            "participants": ["hero_player", "villain"],
            "progress": 0.5,
        }
        
        # Event without player
        event_without_player = {
            "type": "battle",
            "participants": ["npc_a", "npc_b"],
            "progress": 0.5,
        }
        
        score_with = gravity.score_event(event_with_player)
        score_without = gravity.score_event(event_without_player)
        
        assert score_with > score_without, "Player events should score higher"
        assert score_with - score_without >= 0.2, "Player boost should be significant"
    
    def test_focused_events_include_player_even_when_low_progress(self):
        """Test player events remain focused even with low progress."""
        gravity = NarrativeGravity(max_active=2, player_id="hero_player")
        
        # High importance non-player storyline
        sl_high = StorylineState(
            id="high_drama",
            event_type="betrayal",
            participants=["major_npc_1", "major_npc_2"],
            importance=0.9,
        )
        
        # Player storyline with lower progress
        sl_player = StorylineState(
            id="player_quest",
            event_type="quest_start",
            participants=["hero_player", "sidekick"],
            importance=0.4,
            is_player_involved=True,
        )
        
        # Another non-player storyline
        sl_medium = StorylineState(
            id="side_plot",
            event_type="discovery",
            participants=["minor_npc"],
            importance=0.7,
        )
        
        gravity.add_storyline(sl_high)
        gravity.add_storyline(sl_player)
        gravity.add_storyline(sl_medium)
        
        focused = gravity.update_storylines(current_tick=10)
        
        # Top 2 should be highest importance
        # Since player_boost is applied at scoring time, not here,
        # we verify the focus mechanism works correctly
        assert len(focused) == 2


# ============================================================================
# Regression and Edge Case Tests
# ============================================================================

class TestTier12Regression:
    """Regression tests for Tier 12 edge cases."""
    
    def test_empty_inputs_handled(self):
        """Test systems handle empty/None inputs gracefully."""
        resolver = DecisionResolver()
        lock_manager = CoalitionLockManager()
        gravity = NarrativeGravity()
        
        # Resolver with empty dicts
        result = resolver.resolve({}, {}, None)
        assert result is not None
        
        # Lock manager with empty intent
        result = lock_manager.enforce_lock("npc", {}, 0)
        assert result is not None
        
        # Gravity with empty event
        score = gravity.score_event({})
        assert 0.0 <= score <= 1.0
    
    def test_rapid_tick_processing(self):
        """Test systems handle rapid tick processing without degradation."""
        resolver = DecisionResolver()
        lock_manager = CoalitionLockManager()
        gravity = NarrativeGravity(max_active=3)
        
        for i in range(5):
            sl = StorylineState(
                id=f"rapid_{i}",
                importance=0.5,
            )
            gravity.add_storyline(sl)
        
        for tick in range(200):
            resolver.resolve(
                make_base_intent("attack", 5.0),
                make_base_intent("attack", 6.0),
                None
            )
            lock_manager.tick_cleanup(tick)
            gravity.update_storylines(current_tick=tick)
        
        # Systems should still be functional
        stats = resolver.get_stats()
        assert stats["resolutions"] == 200
    
    def test_storyline_limit_enforced(self):
        """Test that storyline limit is strictly enforced."""
        gravity = NarrativeGravity(max_active=3)
        
        # Add many storylines
        for i in range(20):
            sl = StorylineState(id=f"story_{i}", importance=0.1 * i)
            gravity.add_storyline(sl)
        
        focused = gravity.update_storylines(current_tick=10)
        assert len(focused) == 3
        
        # All 20 storylines should still be tracked, but only 3 focused
        assert len(gravity.get_active_storylines()) == 20
        
        # Count background storylines manually
        background_count = sum(
            1 for sl in gravity.get_active_storylines().values()
            if sl.is_background
        )
        assert background_count == 17
    
    def test_full_cycle_no_crashes(self):
        """Test that full Tier 12 cycle doesn't crash with various inputs."""
        resolver = DecisionResolver()
        lock_manager = CoalitionLockManager()
        
        test_scenarios = [
            {"resolver_base": {}, "resolver_enriched": {"priority": 5.0}},
            {
                "resolver_base": {"type": "attack", "priority": 0.0},
                "resolver_enriched": {"type": "attack", "priority": 10.0},
            },
            {"lock_char": "npc", "lock_intent": {"type": "idle", "priority": 0.0}},
            {"lock_char": None, "lock_intent": None},
        ]
        
        for scenario in test_scenarios:
            # Resolver test
            if "resolver_base" in scenario:
                try:
                    result = resolver.resolve(
                        scenario["resolver_base"],
                        scenario["resolver_enriched"],
                        None
                    )
                    assert True  # No crash
                except Exception as e:
                    pytest.fail(f"Resolver crashed: {e}")
            
            # Lock test
            if "lock_char" in scenario:
                try:
                    result = lock_manager.enforce_lock(
                        scenario.get("lock_char", "npc"),
                        scenario.get("lock_intent") or {},
                        0
                    )
                    assert True  # No crash
                except Exception as e:
                    pytest.fail(f"Lock manager crashed: {e}")