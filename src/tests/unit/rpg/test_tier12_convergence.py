"""Unit Tests — Tier 12: Narrative Convergence Engine.

This module provides comprehensive unit tests for all Tier 12 convergence
systems: DecisionResolver, CoalitionLockManager, and NarrativeGravity.

Test Categories:
    - DecisionResolver: Conflict resolution between subsystems
    - CoalitionLockManager: Intent oscillation prevention
    - NarrativeGravity: Storyline convergence and focus

Usage:
    pytest src/tests/unit/rpg/test_tier12_convergence.py -v
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

# Add project path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "app"))

from rpg.cognitive.coalition_lock import CoalitionLock, CoalitionLockManager
from rpg.cognitive.decision_resolver import DEFAULT_WEIGHTS, DecisionResolver
from rpg.cognitive.narrative_gravity import (
    CONCLUSION_TICK_THRESHOLD,
    MAX_ACTIVE_STORYLINES,
    NarrativeGravity,
    StorylineState,
    StorylineWeight,
)

# ============================================================================
# Helper Functions
# ============================================================================

def make_character(char_id: str = "test_char", relationships: dict = None) -> MagicMock:
    """Create a mock character for testing."""
    char = MagicMock()
    char.id = char_id
    char.relationships = relationships or {}
    return char


def make_character_with_learning(char_id: str = "test_char", failure_counts: dict = None) -> MagicMock:
    """Create mock character with learning system."""
    char = make_character(char_id)
    char.learning = MagicMock()
    char.learning.get_failure_counts = MagicMock(return_value=failure_counts or {})
    return char


def make_character_with_identity(char_id: str = "test_char", reputation: dict = None) -> MagicMock:
    """Create mock character with identity system."""
    char = make_character(char_id)
    char.identity = MagicMock()
    char.identity.get_reputation = MagicMock(
        side_effect=lambda x, y: reputation.get(y, 0.0) if reputation else 0.0
    )
    return char


# ============================================================================
# DecisionResolver Tests
# ============================================================================

class TestDecisionResolver:
    """Test decision arbitration and conflict resolution."""
    
    def test_init_defaults(self):
        resolver = DecisionResolver()
        assert resolver.weights == DEFAULT_WEIGHTS
        assert resolver._stats["resolutions"] == 0
    
    def test_init_custom_weights(self):
        custom_weights = {"base": 2.0, "llm": 0.5}
        resolver = DecisionResolver(weights=custom_weights)
        assert resolver.weights["base"] == 2.0
        assert resolver.weights["llm"] == 0.5
        assert resolver.weights["learning"] == 1.2
    
    def test_resolve_base_intent_only(self):
        resolver = DecisionResolver()
        base_intent = {"type": "attack", "priority": 7.0}
        result = resolver.resolve(base_intent, None, None)
        assert result == base_intent
    
    def test_resolve_enriched_intent_only(self):
        resolver = DecisionResolver()
        enriched = {"type": "attack", "priority": 5.0}
        result = resolver.resolve(None, enriched, None)
        assert result == enriched
    
    def test_resolve_null_inputs(self):
        resolver = DecisionResolver()
        result = resolver.resolve(None, None, None)
        assert result is None
    
    def test_compute_final_priority_basic(self):
        resolver = DecisionResolver()
        scores = {"base": 5.0, "llm": 5.0, "learning": 0.0, "reputation": 0.0}
        priority = resolver._compute_final_priority(scores)
        assert 0 <= priority <= 10
    
    def test_compute_priority_with_weights(self):
        custom = {"base": 2.0, "llm": 0.5, "learning": 1.0, "reputation": 1.0}
        resolver = DecisionResolver(weights=custom)
        scores = {"base": 8.0, "llm": 2.0, "learning": 0.0, "reputation": 0.0}
        priority = resolver._compute_final_priority(scores)
        # (8*2 + 2*0.5) / (2+0.5+1+1) = 17/4.5 = 3.77
        assert abs(priority - 3.77) < 0.1
    
    def test_conflict_detection(self):
        resolver = DecisionResolver()
        base = {"type": "attack", "priority": 2.0}
        enriched = {"type": "attack", "priority": 8.0, "reasoning": ""}
        char = make_character_with_learning("test")
        result = resolver.resolve(base, enriched, char)
        assert result is not None
        assert resolver._stats["conflicts_detected"] >= 1
    
    def test_no_conflict_small_gap(self):
        resolver = DecisionResolver()
        base = {"type": "attack", "priority": 5.0}
        enriched = {"type": "attack", "priority": 5.5, "reasoning": ""}
        result = resolver.resolve(base, enriched, None)
        assert resolver._stats["conflicts_detected"] == 0
    
    def test_learning_penalty_applies(self):
        resolver = DecisionResolver()
        char = make_character_with_learning("test", failure_counts={"attack": 4})
        base = {"type": "attack", "priority": 7.0}
        enriched = {"type": "attack", "priority": 7.5, "reasoning": ""}
        result = resolver.resolve(base, enriched, char)
        assert result is not None
    
    def test_reputation_modifier_hostile(self):
        resolver = DecisionResolver()
        char = MagicMock()
        char.id = "test"
        char.identity = MagicMock()
        char.identity.get_reputation = MagicMock(return_value=-0.7)
        char.learning = MagicMock()
        char.learning.get_failure_counts = MagicMock(return_value={})
        char.relationships = {}
        base = {"type": "attack", "priority": 5.0, "target": "target_enemy"}
        enriched = {"type": "attack", "priority": 5.0, "reasoning": ""}
        result = resolver.resolve(base, enriched, char)
        assert result is not None
        # Hostile action against enemy (rep=-0.7): -(-0.7)*2 = 1.4 positive mod
        assert result["reasoning"] is not None
    
    def test_reputation_modifier_friendly(self):
        resolver = DecisionResolver()
        char = MagicMock()
        char.id = "test"
        char.identity = MagicMock()
        char.identity.get_reputation = MagicMock(return_value=0.7)
        char.learning = MagicMock()
        char.learning.get_failure_counts = MagicMock(return_value={})
        char.relationships = {}
        base = {"type": "attack", "priority": 5.0, "target": "target_ally"}
        enriched = {"type": "attack", "priority": 5.0, "reasoning": ""}
        result = resolver.resolve(base, enriched, char)
        assert result is not None
        # Hostile action against ally (rep=0.7): -(0.7)*2 = -1.4 negative mod
    
    def test_missing_target_no_reputation_effect(self):
        resolver = DecisionResolver()
        char = MagicMock()
        char.id = "test"
        char.relationships = {}
        char.learning = MagicMock()
        char.learning.get_failure_counts = MagicMock(return_value={})
        base = {"type": "attack", "priority": 5.0}
        enriched = {"type": "attack", "priority": 5.0, "reasoning": ""}
        result = resolver.resolve(base, enriched, char)
        assert result is not None
    
    def test_learning_from_intent_metadata(self):
        resolver = DecisionResolver()
        char = MagicMock()
        char.id = "test"
        char.relationships = {}
        # No learning system on this character
        del char.learning
        base = {"type": "attack", "priority": 6.0, "recent_failures": 5, "adapted_priority": True}
        enriched = {"type": "attack", "priority": 7.0, "reasoning": ""}
        result = resolver.resolve(base, enriched, char)
        assert result is not None
        # Learning penalty: 5 * 0.5 = 2.5
    
    def test_stats_tracking(self):
        resolver = DecisionResolver()
        base = {"type": "attack", "priority": 5.0}
        enriched = {"type": "attack", "priority": 5.5, "reasoning": ""}
        for _ in range(5):
            resolver.resolve(base, enriched, None)
        stats = resolver.get_stats()
        assert stats["resolutions"] == 5
    
    def test_reasoning_appended(self):
        resolver = DecisionResolver()
        base = {"type": "attack", "priority": 5.0}
        enriched = {"type": "attack", "priority": 6.0, "reasoning": "Initial reason"}
        result = resolver.resolve(base, enriched, None)
        assert "Arbiter:" in result.get("reasoning", "")
        assert "Initial reason" in result.get("reasoning", "")
    
    def test_metadata_fields_added(self):
        resolver = DecisionResolver()
        base = {"type": "attack", "priority": 5.0}
        enriched = {"type": "attack", "priority": 6.0, "reasoning": ""}
        result = resolver.resolve(base, enriched, None)
        assert "resolved_by_arbiter" in result
        assert "base_priority" in result
        assert "enriched_priority" in result
    
    def test_priority_bounds_enforced(self):
        resolver = DecisionResolver()
        scores = {"base": 100.0, "llm": 100.0, "learning": 100.0, "reputation": 100.0}
        priority = resolver._compute_final_priority(scores)
        assert 0 <= priority <= 10
        scores_neg = {"base": -100.0, "llm": -100.0, "learning": -100.0, "reputation": -100.0}
        priority = resolver._compute_final_priority(scores_neg)
        assert 0 <= priority <= 10
    
    def test_reset(self):
        resolver = DecisionResolver()
        resolver._stats["resolutions"] = 10
        resolver.reset()
        assert resolver.get_stats()["resolutions"] == 0


# ============================================================================
# CoalitionLockManager Tests
# ============================================================================

class TestCoalitionLockManager:
    """Test coalition commitment locks."""
    
    def test_init_defaults(self):
        manager = CoalitionLockManager()
        assert manager.default_duration == 10
        assert manager.emergency_threshold == 2.0
        assert manager._stats["locks_acquired"] == 0
    
    def test_acquire_basic_lock(self):
        manager = CoalitionLockManager()
        lock = manager.acquire_lock("npc_1", "enemy_1", "coordinated_attack", current_tick=50)
        assert lock is not None
        assert lock.character_id == "npc_1"
        assert lock.target == "enemy_1"
        assert lock.expires_tick == 60
    
    def test_acquire_lock_custom_duration(self):
        manager = CoalitionLockManager()
        lock = manager.acquire_lock("npc_1", "target", "coordinated_defense", duration=20, current_tick=100)
        assert lock.expires_tick == 120
    
    def test_acquire_lock_coalition_id(self):
        manager = CoalitionLockManager()
        lock = manager.acquire_lock("npc_1", "target", "coordinated_attack", coalition_id="coal_1", current_tick=50)
        assert lock.coalition_id == "coal_1"
    
    def test_is_locked_basic(self):
        manager = CoalitionLockManager()
        manager.acquire_lock("npc_1", "target", "attack", current_tick=50)
        assert manager.is_locked("npc_1", current_tick=55) is True
        assert manager.is_locked("npc_1", current_tick=100) is False
        assert manager.is_locked("unknown", current_tick=55) is False
    
    def test_is_locked_with_intent_filter(self):
        manager = CoalitionLockManager()
        manager.acquire_lock("npc_1", "target", "coordinated_attack", current_tick=50)
        assert manager.is_locked("npc_1", current_tick=55, intent_type="coordinated_attack") is True
        assert manager.is_locked("npc_1", current_tick=55, intent_type="other_type") is False
    
    def test_enforce_lock_active(self):
        manager = CoalitionLockManager()
        manager.acquire_lock("npc_1", "locked_target", "coordinated_attack", coalition_id="coal_1", current_tick=50)
        intent = {"type": "idle", "priority": 2.0, "reasoning": ""}
        result = manager.enforce_lock("npc_1", intent, current_tick=55)
        assert result["type"] == "coordinated_attack"
        assert result["target"] == "locked_target"
        assert result["coalition_locked"] is True
        assert "Coalition Lock" in result.get("reasoning", "")
    
    def test_enforce_lock_expired(self):
        manager = CoalitionLockManager()
        manager.acquire_lock("npc_1", "target", "attack", current_tick=50)
        intent = {"type": "idle", "priority": 3.0}
        result = manager.enforce_lock("npc_1", intent, current_tick=100)
        assert result["type"] == "idle"
    
    def test_enforce_lock_emergency_override(self):
        manager = CoalitionLockManager()
        manager.acquire_lock("npc_1", "target", "attack", current_tick=50)
        intent = {"type": "flee", "priority": 1.0}
        result = manager.enforce_lock("npc_1", intent, current_tick=55)
        assert result["type"] == "flee"
        assert manager._stats["locks_broken"] >= 1
    
    def test_enforce_lock_none_intent(self):
        manager = CoalitionLockManager()
        result = manager.enforce_lock("npc_1", None, current_tick=55)
        assert result is None
    
    def test_release_specific_lock(self):
        manager = CoalitionLockManager()
        manager.acquire_lock("npc_1", "target", "attack", current_tick=50)
        released = manager.release_lock("npc_1", intent_type="attack")
        assert released is True
        assert manager.is_locked("npc_1", current_tick=55) is False
    
    def test_release_unknown_lock(self):
        manager = CoalitionLockManager()
        released = manager.release_lock("npc_1", intent_type="unknown")
        assert released is False
    
    def test_release_all_locks(self):
        manager = CoalitionLockManager()
        manager.acquire_lock("npc_1", "t1", "type_a", current_tick=50)
        manager.acquire_lock("npc_1", "t2", "type_b", current_tick=50)
        count = manager.release_all_locks("npc_1")
        assert count >= 1
        assert manager.is_locked("npc_1", current_tick=55) is False
    
    def test_tick_cleanup_expires_locks(self):
        manager = CoalitionLockManager(default_duration=5)
        manager.acquire_lock("npc_1", "target", "attack", current_tick=50)
        assert manager.is_locked("npc_1", current_tick=52) is True
        manager.tick_cleanup(current_tick=100)
        assert manager.is_locked("npc_1", current_tick=100) is False
    
    def test_get_active_locks(self):
        manager = CoalitionLockManager()
        manager.acquire_lock("npc_1", "target", "attack", current_tick=50)
        active = manager.get_active_locks("npc_1", current_tick=55)
        assert len(active) == 1
        assert active[0].target == "target"
    
    def test_stats_tracking(self):
        manager = CoalitionLockManager()
        manager.acquire_lock("npc_1", "target", "attack", current_tick=50)
        stats = manager.get_stats()
        assert "locks_acquired" in stats
        assert "active_locks" in stats
    
    def test_lock_serialization(self):
        lock = CoalitionLock("test", "target", "attack", 50, 60, "coal_1", 7.0)
        d = lock.to_dict()
        assert d["character_id"] == "test"
        assert d["expires_tick"] == 60
    
    def test_reset(self):
        manager = CoalitionLockManager()
        manager.acquire_lock("npc_1", "target", "attack", current_tick=50)
        manager.reset()
        assert manager._stats["locks_acquired"] == 0
        assert manager.is_locked("npc_1", current_tick=55) is False


# ============================================================================
# NarrativeGravity Tests
# ============================================================================

class TestNarrativeGravity:
    """Test narrative convergence and storyline focus."""
    
    def test_init_defaults(self):
        gravity = NarrativeGravity()
        assert gravity.max_active == MAX_ACTIVE_STORYLINES
    
    def test_init_custom_values(self):
        gravity = NarrativeGravity(max_active=5, player_id="hero")
        assert gravity.max_active == 5
        assert gravity.player_id == "hero"
    
    def test_score_event_basic(self):
        gravity = NarrativeGravity()
        event = {"type": "battle", "participants": ["npc_1", "npc_2"], "progress": 0.5}
        score = gravity.score_event(event)
        assert 0.0 <= score <= 1.0
    
    def test_score_event_player_boost(self):
        gravity = NarrativeGravity(player_id="player")
        event_with_player = {"type": "battle", "participants": ["player", "npc_1"], "progress": 0.5}
        event_without_player = {"type": "battle", "participants": ["npc_1", "npc_2"], "progress": 0.5}
        score_with = gravity.score_event(event_with_player)
        score_without = gravity.score_event(event_without_player)
        assert score_with > score_without
    
    def test_score_event_coalition_boost(self):
        gravity = NarrativeGravity()
        small = {"type": "conflict", "participants": ["npc_1"], "coalition_size": 2}
        large = {"type": "conflict", "participants": ["npc_1"], "coalition_size": 5}
        assert gravity.score_event(large) >= gravity.score_event(small)
    
    def test_score_event_known_characters(self):
        gravity = NarrativeGravity()
        characters = {"hero": {"importance": 0.9}, "villain": {"importance": 0.8}, "random_npc": {"importance": 0.1}}
        event_important = {"type": "conflict", "participants": ["hero", "villain"]}
        event_unimportant = {"type": "conflict", "participants": ["random_npc"]}
        assert gravity.score_event(event_important, characters=characters) > gravity.score_event(event_unimportant, characters=characters)
    
    def test_score_event_type_weights(self):
        gravity = NarrativeGravity()
        battle = {"type": "battle", "participants": ["npc_1"]}
        personal = {"type": "personal", "participants": ["npc_1"]}
        assert gravity.score_event(battle) > gravity.score_event(personal)
    
    def test_score_event_bounds(self):
        gravity = NarrativeGravity()
        event = {"type": "unknown_type", "participants": [], "coalition_size": 100, "progress": 2.0}
        score = gravity.score_event(event)
        assert 0.0 <= score <= 1.0
    
    def test_storyline_operations(self):
        gravity = NarrativeGravity()
        storyline = StorylineState(id="story_1", event_type="conflict", participants=["npc_1"], start_tick=0)
        gravity.add_storyline(storyline)
        assert gravity.get_storyline("story_1") == storyline
        assert "story_1" in gravity.get_active_storylines()
    
    def test_update_storylines_focuses_top_n(self):
        gravity = NarrativeGravity(max_active=2)
        for i in range(5):
            sl = StorylineState(id=f"story_{i}", event_type="conflict", importance=0.5 + i * 0.1)
            gravity.add_storyline(sl)
        focused = gravity.update_storylines(current_tick=10)
        assert len(focused) == 2
        assert focused[0].importance >= focused[1].importance
    
    def test_update_storylines_demotes_lower(self):
        gravity = NarrativeGravity(max_active=2)
        for i in range(3):
            sl = StorylineState(id=f"story_{i}", event_type="conflict", importance=0.5 + i * 0.1)
            gravity.add_storyline(sl)
        focused = gravity.update_storylines(current_tick=10)
        for sl in gravity._storylines.values():
            if sl not in focused:
                assert sl.is_background is True
    
    def test_background_decay(self):
        gravity = NarrativeGravity(max_active=1)
        sl_main = StorylineState(id="main", importance=0.9)
        sl_bg = StorylineState(id="bg", importance=0.5)
        gravity.add_storyline(sl_main)
        gravity.add_storyline(sl_bg)
        gravity.update_storylines(current_tick=10)
        gravity.update_storylines(current_tick=20)
        assert sl_bg.importance < 0.5
    
    def test_resolution_pressure_builds(self):
        gravity = NarrativeGravity()
        sl = StorylineState(id="old_story", start_tick=0, progress=0.1)
        gravity.add_storyline(sl)
        gravity.update_storylines(current_tick=CONCLUSION_TICK_THRESHOLD)
        assert sl.resolution_pressure > 0.0
    
    def test_should_conclude_complete(self):
        gravity = NarrativeGravity()
        sl = StorylineState(id="done", progress=1.0)
        assert gravity.should_conclude(sl) is True
    
    def test_should_conclude_old_stagnant(self):
        gravity = NarrativeGravity()
        sl = StorylineState(id="old_stagnant", start_tick=0, progress=0.05)
        gravity.add_storyline(sl)
        gravity.update_storylines(current_tick=CONCLUSION_TICK_THRESHOLD * 2)
        assert gravity.should_conclude(sl) is True
    
    def test_should_conclude_low_importance(self):
        gravity = NarrativeGravity()
        sl = StorylineState(id="unimportant", importance=0.05)
        assert gravity.should_conclude(sl) is True
    
    def test_conclude_storyline_moves_to_history(self):
        gravity = NarrativeGravity()
        sl = StorylineState(id="concluded", importance=0.6, progress=0.3)
        gravity.add_storyline(sl)
        result = gravity.conclude_storyline("concluded")
        assert result is not None
        assert "concluded" not in gravity.get_active_storylines()
        assert len(gravity.get_concluded_storylines()) == 1
    
    def test_conclude_nonexistent_storyline(self):
        gravity = NarrativeGravity()
        result = gravity.conclude_storyline("does_not_exist")
        assert result is None
    
    def test_generate_resolution_messages(self):
        gravity = NarrativeGravity()
        sl_complete = StorylineState(id="complete", progress=0.9)
        assert "natural conclusion" in gravity.generate_resolution(sl_complete)
        sl_partial = StorylineState(id="partial", progress=0.6)
        assert "partially resolved" in gravity.generate_resolution(sl_partial)
        sl_faded = StorylineState(id="faded", importance=0.05)
        assert "faded from attention" in gravity.generate_resolution(sl_faded)
    
    def test_get_focused_events_orders_by_importance(self):
        gravity = NarrativeGravity()
        events = [{"importance": 0.3}, {"importance": 0.9}, {"importance": 0.6}]
        focused = gravity.get_focused_events(events, max_count=2)
        assert focused[0]["importance"] == 0.9
        assert len(focused) == 2
    
    def test_background_event_management(self):
        gravity = NarrativeGravity()
        for i in range(25):
            gravity.add_background_event({"id": i})
        assert len(gravity.get_background_events()) <= 20
    
    def test_storyline_summary_includes_history(self):
        gravity = NarrativeGravity()
        sl = StorylineState(id="historic", importance=0.5)
        gravity.add_storyline(sl)
        gravity.conclude_storyline("historic")
        summary = gravity.get_storyline_summary("historic")
        assert summary.get("id") == "historic"
    
    def test_advance_progress(self):
        gravity = NarrativeGravity()
        sl = StorylineState(id="progress_test", progress=0.0)
        gravity.add_storyline(sl)
        gravity.advance_progress_for_participants("progress_test", ["npc_1"], delta=0.3)
        assert sl.progress == 0.3
    
    def test_stats_tracking(self):
        gravity = NarrativeGravity()
        event = {"type": "battle", "participants": ["npc_1"]}
        gravity.score_event(event)
        gravity.score_event(event)
        stats = gravity.get_stats()
        assert stats["events_scored"] == 2
    
    def test_reset(self):
        gravity = NarrativeGravity()
        sl = StorylineState(id="test", importance=0.5)
        gravity.add_storyline(sl)
        gravity.score_event({"type": "battle"})
        gravity.reset()
        assert len(gravity.get_active_storylines()) == 0
        assert gravity.get_stats()["events_scored"] == 0


# ============================================================================
# Integrated 100-Tick Convergence Test
# ============================================================================

class TestConvergenceSimulation:
    """Test full convergence behavior over extended simulation."""
    
    def test_100_tick_simulation(self):
        """Run 100-tick simulation with all Tier 12 systems active."""
        resolver = DecisionResolver()
        lock_manager = CoalitionLockManager(default_duration=10)
        gravity = NarrativeGravity(max_active=3)
        
        # Create initial storylines
        for i in range(5):
            sl = StorylineState(
                id=f"story_{i}",
                event_type="conflict",
                participants=[f"npc_{i}"],
                importance=0.3 + i * 0.1,
                start_tick=0,
            )
            gravity.add_storyline(sl)
        
        focused_counts = []
        concluded_count = 0
        
        for tick in range(100):
            # Decision resolution
            base = {"type": "attack", "priority": 5.0 + (tick % 3) * 0.5}
            enriched = {"type": "attack", "priority": 6.0, "reasoning": ""}
            result = resolver.resolve(base, enriched, None)
            
            # Lock management
            if tick % 20 == 0:
                lock_manager.acquire_lock(f"npc_{tick % 5}", "target", "coordinated_attack", current_tick=tick)
            lock_manager.tick_cleanup(tick)
            
            # Narrative gravity
            focused = gravity.update_storylines(current_tick=tick)
            focused_counts.append(len(focused))
            
            # Check for storyline conclusions
            for sl in list(gravity.get_active_storylines().values()):
                if gravity.should_conclude(sl, tick):
                    resolution = gravity.generate_resolution(sl)
                    gravity.conclude_storyline(sl.id, resolution)
            
            # Record outcomes for learning
            if tick % 50 == 0:
                gravity.score_event({"type": "battle", "participants": ["npc_1", "npc_2"]})
        
        # Verify convergence behavior
        assert all(c <= 3 for c in focused_counts), "Focused storylines should never exceed max_active"
        assert gravity.get_stats()["storylines_demoted"] > 0, "Background demotion should occur"
        stats = resolver.get_stats()
        assert stats["resolutions"] == 100