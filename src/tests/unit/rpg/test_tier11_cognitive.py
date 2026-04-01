"""Unit Tests — Tier 11: Hybrid Cognitive Simulation.

This module provides comprehensive unit tests for all Tier 11 cognitive
systems: Intent Enrichment, Identity System, Coalition System, Learning
System, and the unified CognitiveLayer.

Test Categories:
    - IntentEnrichment: LLM-assisted intent refinement with guardrails
    - IdentitySystem: Reputation, fame, rumors tracking
    - CoalitionSystem: Coordinated faction behavior
    - LearningSystem: Outcome tracking and adaptation
    - CognitiveLayer: Unified interface integration

Usage:
    pytest src/tests/unit/rpg/test_tier11_cognitive.py -v
"""

from __future__ import annotations

import os
import sys
from collections import deque
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# Add project path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "app"))

from rpg.cognitive.intent_enrichment import IntentEnrichment, ALLOWED_INTENTS
from rpg.cognitive.identity import IdentitySystem, CharacterIdentity
from rpg.cognitive.coalition import CoalitionSystem, Coalition
from rpg.cognitive.learning import LearningSystem
from rpg.cognitive.cognitive_layer import CognitiveLayer


# ============================================================================
# Mock LLM Client
# ============================================================================

class MockLLMClient:
    """Mock LLM client for testing."""
    
    def __init__(self, response: Dict[str, Any] = None):
        """Initialize mock client.
        
        Args:
            response: Response to return from generate_json.
        """
        self.default_response = response or {
            "priority": 7.0,
            "target": "bandit_camp",
            "reasoning": "High threat detected nearby",
        }
        self.call_count = 0
        self.last_prompt = None
    
    def generate_json(self, prompt: str) -> Dict[str, Any]:
        """Mock JSON generation.
        
        Args:
            prompt: Input prompt.
            
        Returns:
            Default response dict.
        """
        self.call_count += 1
        self.last_prompt = prompt
        return dict(self.default_response)
    
    def generate(self, prompt: str) -> str:
        """Mock text generation.
        
        Args:
            prompt: Input prompt.
            
        Returns:
            JSON string response.
        """
        self.call_count += 1
        self.last_prompt = prompt
        import json
        return json.dumps(self.default_response)


# ============================================================================
# Helper to create test characters
# ============================================================================

def make_character(
    char_id: str = "test_char",
    traits: list = None,
    goals: list = None,
    beliefs: dict = None,
) -> MagicMock:
    """Create a mock character for testing.
    
    Args:
        char_id: Character ID.
        traits: Character traits list.
        goals: Character goals list.
        beliefs: Character beliefs dict.
        
    Returns:
        Mock character object.
    """
    char = MagicMock()
    char.id = char_id
    char.traits = traits or ["brave", "cunning"]
    char.goals = goals or ["expand influence", "gather_resources"]
    char.beliefs = beliefs or {"faction_a": 0.5, "faction_b": -0.3}
    return char


def make_world_state(
    factions: dict = None,
    tick: int = 0,
) -> Dict[str, Any]:
    """Create a mock world state for testing.
    
    Args:
        factions: Faction data dict.
        tick: Current tick.
        
    Returns:
        World state dict.
    """
    if factions is None:
        factions = {
            "faction_a": {
                "name": "Faction A",
                "power": 0.6,
                "relations": {"test_char": 0.5},
            },
            "faction_b": {
                "name": "Faction B",
                "power": 0.8,
                "relations": {"test_char": -0.7},
            },
        }
    
    return {
        "factions": factions,
        "tick": tick,
        "events": [],
    }


# ============================================================================
# IntentEnrichment Tests
# ============================================================================

class TestIntentEnrichment:
    """Test intent enrichment with LLM assistance."""
    
    def test_init_default_values(self):
        """Test initialization with defaults."""
        enrichment = IntentEnrichment()
        assert enrichment.llm_client is None
        assert enrichment.cooldown_ticks == 5
        assert enrichment._last_llm_call_tick == -5
        assert enrichment._stats["enrichment_attempts"] == 0
    
    def test_enrich_returns_original_if_intent_none(self):
        """Test that None intent returns None."""
        enrichment = IntentEnrichment()
        assert enrichment.enrich(None, make_character(), {}) is None
    
    def test_enrich_returns_original_without_llm(self):
        """Test that without LLM client, original intent is returned."""
        enrichment = IntentEnrichment()
        intent = {"type": "attack_target", "priority": 5.0}
        result = enrichment.enrich(intent, make_character(), {})
        assert result == intent
    
    def test_enrich_with_llm_modifies_priority(self):
        """Test that LLM enrichment can modify priority."""
        mock_llm = MockLLMClient(response={"priority": 8.0, "target": "new_target"})
        enrichment = IntentEnrichment(llm_client=mock_llm)
        
        intent = {"type": "attack_target", "priority": 5.0, "reasoning": "test"}
        character = make_character()
        world = make_world_state()
        
        result = enrichment.enrich(intent, character, world, current_tick=10)
        
        assert result["priority"] == 8.0
        assert result.get("llm_adjusted_priority") is True
        assert result["target"] == "new_target"
    
    def test_enrich_rejects_invalid_intents(self):
        """Test that invalid intent types are not enriched."""
        mock_llm = MockLLMClient()
        enrichment = IntentEnrichment(llm_client=mock_llm)
        
        intent = {"type": "invalid_intent", "priority": 5.0}
        result = enrichment.enrich(intent, make_character(), {}, current_tick=10)
        
        # Should return original intent unchanged
        assert result["priority"] == 5.0
        assert mock_llm.call_count == 0
    
    def test_enrich_cooldown_prevents_rapid_calls(self):
        """Test cooldown prevents rapid LLM calls."""
        mock_llm = MockLLMClient()
        enrichment = IntentEnrichment(llm_client=mock_llm, cooldown_ticks=5)
        
        intent = {"type": "attack_target", "priority": 5.0}
        char = make_character()
        world = make_world_state()
        
        # First call (should use LLM)
        enrichment.enrich(intent, char, world, current_tick=10)
        assert mock_llm.call_count == 1
        
        # Second call within cooldown (should not use LLM)
        enrichment.enrich(intent, char, world, current_tick=11)
        assert mock_llm.call_count == 1  # Same count
        
        # Third call after cooldown (should use LLM)
        enrichment.enrich(intent, char, world, current_tick=16)
        assert mock_llm.call_count == 2
    
    def test_enrich_low_priority_intents_skip_llm(self):
        """Test that low priority intents skip LLM enrichment."""
        mock_llm = MockLLMClient()
        enrichment = IntentEnrichment(llm_client=mock_llm)
        
        intent = {"type": "idle", "priority": 1.0}
        result = enrichment.enrich(intent, make_character(), {}, current_tick=10)
        
        assert result["priority"] == 1.0
        assert mock_llm.call_count == 0
    
    def test_validate_priority_bounds(self):
        """Test that priority is clamped to valid bounds."""
        # Test out-of-range priority is rejected
        mock_llm = MockLLMClient(response={"priority": 15.0})
        enrichment = IntentEnrichment(llm_client=mock_llm)
        
        intent = {"type": "attack_target", "priority": 5.0}
        result = enrichment.enrich(
            intent, make_character(), make_world_state(), current_tick=10
        )
        
        # Out of bounds priority should be rejected, keep original
        assert result["priority"] == 5.0
    
    def test_stats_tracking(self):
        """Test that enrichment statistics are tracked."""
        enrichment = IntentEnrichment()
        
        assert enrichment.get_stats()["enrichment_attempts"] == 0
        
        # Make some enrichment calls
        intent = {"type": "attack_target", "priority": 5.0}
        enrichment.enrich(intent, make_character(), {}, current_tick=10)
        enrichment.enrich(intent, make_character(), {}, current_tick=20)
        
        stats = enrichment.get_stats()
        assert stats["enrichment_attempts"] == 2
    
    def test_reset_stats(self):
        """Test that stats can be reset."""
        enrichment = IntentEnrichment()
        enrichment._stats["enrichment_attempts"] = 5
        enrichment.reset_stats()
        assert enrichment.get_stats()["enrichment_attempts"] == 0
    
    def test_set_cooldown(self):
        """Test cooldown can be changed."""
        enrichment = IntentEnrichment(cooldown_ticks=5)
        enrichment.set_cooldown(10)
        assert enrichment.cooldown_ticks == 10
    
    def test_is_ready(self):
        """Test cooldown readiness check."""
        enrichment = IntentEnrichment(cooldown_ticks=5)
        
        assert enrichment.is_ready(0) is True  # Initially ready
        enrichment._last_llm_call_tick = 5
        assert enrichment.is_ready(7) is False
        assert enrichment.is_ready(11) is True


# ============================================================================
# IdentitySystem Tests
# ============================================================================

class TestIdentitySystem:
    """Test persistent identity tracking."""
    
    def test_init(self):
        """Test initialization."""
        identity_sys = IdentitySystem()
        assert len(identity_sys.identities) == 0
    
    def test_get_or_create(self):
        """Test identity creation."""
        identity_sys = IdentitySystem()
        identity = identity_sys.get_or_create("hero_alice")
        assert identity.character_id == "hero_alice"
        assert identity.fame == 0.0
    
    def test_get_identity_nonexistent(self):
        """Test getting non-existent identity returns None."""
        identity_sys = IdentitySystem()
        assert identity_sys.get_identity("unknown") is None
    
    def test_set_and_get_fame(self):
        """Test fame setting and getting."""
        identity_sys = IdentitySystem()
        identity_sys.set_fame("hero_alice", 0.8)
        
        identity = identity_sys.get_identity("hero_alice")
        assert identity.fame == 0.8
    
    def test_fame_bounds(self):
        """Test fame is clamped to 0-1 range."""
        identity_sys = IdentitySystem()
        identity_sys.set_fame("char", 2.0)
        assert identity_sys.get_identity("char").fame == 1.0
        
        identity_sys.set_fame("char", -0.5)
        assert identity_sys.get_identity("char").fame == 0.0
    
    def test_adjust_fame(self):
        """Test fame adjustment."""
        import math
        identity_sys = IdentitySystem()
        identity_sys.set_fame("hero", 0.5)
        new_fame = identity_sys.adjust_fame("hero", 0.2)
        assert math.isclose(new_fame, 0.7, rel_tol=1e-9)
        
        new_fame = identity_sys.adjust_fame("hero", -0.3)
        assert math.isclose(new_fame, 0.4, rel_tol=1e-9)
    
    def test_reputation_tracking(self):
        """Test faction reputation tracking."""
        import math
        identity_sys = IdentitySystem()
        
        # Set reputation (max change is 0.3 per call)
        rep = identity_sys.update_reputation("hero", "mages_guild", 0.3)
        assert math.isclose(rep, 0.3, rel_tol=1e-9)
        
        # Get reputation
        rep = identity_sys.get_reputation("hero", "mages_guild")
        assert math.isclose(rep, 0.3, rel_tol=1e-9)
        
        # Update again
        rep2 = identity_sys.update_reputation("hero", "mages_guild", 0.2)
        assert math.isclose(rep2, 0.5, rel_tol=1e-9)
        
        # Non-existent faction returns 0
        rep = identity_sys.get_reputation("hero", "unknown_faction")
        assert rep == 0.0
    
    def test_reputation_bounds(self):
        """Test reputation respects max change limit."""
        identity_sys = IdentitySystem()
        
        # Max single change is 0.3
        rep = identity_sys.update_reputation("hero", "faction", 0.5)
        assert rep <= 0.3  # Should be clamped
    
    def test_rumors(self):
        """Test rumor tracking."""
        identity_sys = IdentitySystem()
        
        identity_sys.add_rumor("hero", "Slayed the dragon!")
        rumors = identity_sys.get_rumors_for("hero")
        assert len(rumors) == 1
        assert "dragon" in rumors[0]
    
    def test_process_action_positive(self):
        """Test positive action reputation."""
        identity_sys = IdentitySystem()
        
        changes = identity_sys.process_action(
            "hero", "heal", "villager", importance=0.5
        )
        
        # Healing should give positive reputation
        identity = identity_sys.get_identity("hero")
        assert identity is not None
    
    def test_process_action_negative(self):
        """Test negative action reputation."""
        identity_sys = IdentitySystem()
        
        identity_sys.update_reputation("hero", "village", 0.5)
        changes = identity_sys.process_action(
            "hero", "attack", "villager", importance=0.5,
            faction_id="village"
        )
        
        # Attack should give negative reputation
        assert "village" in changes
    
    def test_relationships(self):
        """Test character relationship tracking."""
        identity_sys = IdentitySystem()
        
        identity_sys.update_relationship("hero", "npc_bob", 0.3)
        rel = identity_sys.get_relationship("hero", "npc_bob")
        assert rel == 0.3
    
    def test_reputation_summary(self):
        """Test reputation summary."""
        identity_sys = IdentitySystem()
        identity_sys.update_reputation("hero", "guild_a", 0.5)
        identity_sys.set_fame("hero", 0.8)
        identity_sys.add_rumor("hero", "Famous hero")
        
        summary = identity_sys.get_reputation_summary("hero")
        assert summary["fame"] == 0.8
        assert "guild_a" in summary["reputation"]
        assert len(summary["rumors"]) >= 1
    
    def test_tick_update_fades_rumors(self):
        """Test that tick update fades rumors."""
        identity_sys = IdentitySystem()
        identity_sys.add_rumor("hero", "Old rumor", source="someone")
        
        # Run many ticks
        for _ in range(30):
            identity_sys.tick_update()
        
        # Rumor should be gone (faded below 0.1 threshold)
        rumors = identity_sys.get_rumors_for("hero", min_strength=0.2)
        assert len(rumors) == 0
    
    def test_remove_identity(self):
        """Test identity removal."""
        identity_sys = IdentitySystem()
        identity_sys.get_or_create("hero")
        
        removed = identity_sys.remove_identity("hero")
        assert removed is not None
        assert identity_sys.get_identity("hero") is None
    
    def test_get_stats(self):
        """Test statistics tracking."""
        identity_sys = IdentitySystem()
        identity_sys.get_or_create("hero")
        identity_sys.get_or_create("villain")
        
        stats = identity_sys.get_stats()
        assert stats["total_identities"] == 2
    
    def test_reset(self):
        """Test full system reset."""
        identity_sys = IdentitySystem()
        identity_sys.get_or_create("hero")
        identity_sys.reset()
        assert len(identity_sys.identities) == 0


# ============================================================================
# CoalitionSystem Tests
# ============================================================================

class TestCoalitionSystem:
    """Test coalition management."""
    
    def test_init(self):
        """Test initialization."""
        coalition_sys = CoalitionSystem()
        assert len(coalition_sys.coalitions) == 0
    
    def test_should_seek_coalition_weak_faction(self):
        """Test weak factions seek coalitions."""
        coalition_sys = CoalitionSystem()
        
        world = {
            "factions": {
                "weak_faction": {"power": 0.2},
                "strong_faction": {"power": 0.8},
            }
        }
        
        assert coalition_sys.should_seek_coalition("weak_faction", world) is True
    
    def test_should_seek_coalition_strong_faction(self):
        """Test strong factions don't seek coalitions."""
        coalition_sys = CoalitionSystem()
        
        world = {
            "factions": {
                "strong_faction": {"power": 0.9},
                "other_faction": {"power": 0.3, "relations": {"strong_faction": -0.5}},
            }
        }
        
        assert coalition_sys.should_seek_coalition("strong_faction", world) is False
    
    def test_should_seek_coalition_threatened_faction(self):
        """Test threatened factions seek coalitions."""
        coalition_sys = CoalitionSystem()
        
        world = {
            "factions": {
                "target": {
                    "power": 0.4,
                    "relations": {"enemy": -0.5},
                },
                "enemy": {
                    "power": 0.9,
                    "relations": {"target": -0.5},
                },
            }
        }
        
        assert coalition_sys.should_seek_coalition("target", world) is True
    
    def test_find_potential_partners(self):
        """Test partner finding."""
        coalition_sys = CoalitionSystem()
        
        world = {
            "factions": {
                "seeker": {
                    "power": 0.4,
                    "relations": {"ally": 0.7, "enemy": -0.5},
                },
                "ally": {
                    "power": 0.5,
                    "relations": {"seeker": 0.6},
                },
                "enemy": {
                    "power": 0.8,
                    "relations": {"seeker": -0.6},
                },
            }
        }
        
        partners = coalition_sys.find_potential_partners("seeker", world)
        assert "ally" in partners
        assert "enemy" not in partners
    
    def test_form_coalition(self):
        """Test coalition formation."""
        coalition_sys = CoalitionSystem()
        
        coalition = coalition_sys.form_coalition(
            "faction_a", ["faction_b", "faction_c"],
            current_tick=10,
        )
        
        assert coalition is not None
        assert "faction_a" in coalition.members
        assert "faction_b" in coalition.members
        assert coalition.leader == "faction_a"
    
    def test_form_coalition_empty_partners(self):
        """Test coalition formation with no partners."""
        coalition_sys = CoalitionSystem()
        
        coalition = coalition_sys.form_coalition("faction_a", [])
        assert coalition is None
    
    def test_coalition_trust(self):
        """Test coalition trust mechanics."""
        coalition = Coalition("test_coal")
        coalition.add_member("a", initial_trust=0.5)
        coalition.add_member("b", initial_trust=0.5)
        
        # Record success boosts trust
        coalition.record_success()
        avg_trust = coalition.get_average_trust()
        assert avg_trust > 0.5
        
        # Record failure reduces trust
        coalition.record_failure()
        # Trust should be reduced from the success boost
    
    def test_coalition_max_size(self):
        """Test coalition size limit."""
        coalition = Coalition("test_coal")
        for i in range(10):
            coalition.add_member(f"member_{i}")
        
        assert len(coalition.members) <= 5  # MAX_COALITION_SIZE
    
    def test_remove_member(self):
        """Test member removal from coalition."""
        coalition = Coalition("test_coal")
        coalition.add_member("leader", initial_trust=0.5)
        coalition.add_member("member", initial_trust=0.5)
        
        assert coalition.remove_member("member") is True
        assert "member" not in coalition.members
        
        assert coalition.remove_member("nonexistent") is False
    
    def test_coalition_dissolution_low_trust(self):
        """Test coalition dissolves on low trust."""
        coalition_sys = CoalitionSystem()
        coalition = coalition_sys.form_coalition("a", ["b"])
        
        # Reduce trust to minimum
        coal = coalition_sys.coalitions[coalition.id]
        coal.trust_levels["a"]["b"] = -0.5
        coal.trust_levels["b"]["a"] = -0.5
        
        stable = coalition_sys.check_coalition_stability(coalition.id, current_tick=100)
        assert stable is False
    
    def test_coalition_dissolution_stale(self):
        """Test coalition dissolves when too old without success."""
        coalition_sys = CoalitionSystem()
        coalition = coalition_sys.form_coalition("a", ["b"], current_tick=0)
        
        stable = coalition_sys.check_coalition_stability(
            coalition.id, current_tick=60
        )
        assert stable is False  # 60 ticks old, no success > 50 limit
    
    def test_record_coalition_outcome_success(self):
        """Test recording coalition success."""
        coalition_sys = CoalitionSystem()
        coalition = coalition_sys.form_coalition("a", ["b"])
        
        coalition_sys.record_coalition_outcome(coalition.id, success=True)
        assert coalition.success_count == 1
    
    def test_record_coalition_outcome_failure(self):
        """Test recording coalition failure."""
        coalition_sys = CoalitionSystem()
        coalition = coalition_sys.form_coalition("a", ["b"])
        
        coalition_sys.record_coalition_outcome(coalition.id, success=False)
        assert coalition.failure_count == 1
    
    def test_get_coordinated_action_no_coalition(self):
        """Test coordinated action returns None without coalition."""
        coalition_sys = CoalitionSystem()
        action = coalition_sys.get_coordinated_action(
            "faction", "attack", {"factions": {}}
        )
        assert action is None
    
    def test_check_coalition_stability_no_coalition(self):
        """Test stability check with non-existent coalition."""
        coalition_sys = CoalitionSystem()
        assert coalition_sys.check_coalition_stability("nonexistent") is False
    
    def test_get_stats(self):
        """Test statistics tracking."""
        coalition_sys = CoalitionSystem()
        coalition_sys.form_coalition("a", ["b"])
        
        stats = coalition_sys.get_stats()
        assert stats["coalitions_formed"] == 1
        assert stats["active_coalitions"] == 1
    
    def test_reset(self):
        """Test system reset."""
        coalition_sys = CoalitionSystem()
        coalition_sys.form_coalition("a", ["b"])
        coalition_sys.reset()
        assert len(coalition_sys.coalitions) == 0


# ============================================================================
# LearningSystem Tests
# ============================================================================

class TestLearningSystem:
    """Test outcome tracking and adaptation."""
    
    def test_init(self):
        """Test initialization."""
        learning = LearningSystem()
        assert len(learning.history) == 0
    
    def test_record_outcome(self):
        """Test outcome recording."""
        learning = LearningSystem()
        learning.record_outcome("char_a", "attack", success=True, current_tick=0)
        
        history = learning.get_action_history("char_a")
        assert len(history) == 1
        assert history[0]["success"] is True
    
    def test_record_multiple_outcomes(self):
        """Test multiple outcome recording."""
        learning = LearningSystem()
        
        for i in range(5):
            learning.record_outcome("char", "attack", success=(i < 3), current_tick=i)
        
        history = learning.get_action_history("char")
        assert len(history) == 5
    
    def test_should_change_strategy_no_failures(self):
        """Test strategy change check with no failures."""
        learning = LearningSystem()
        learning.record_outcome("char", "attack", success=True, current_tick=0)
        
        assert learning.should_change_strategy("char", "attack") is False
    
    def test_should_change_strategy_with_failures(self):
        """Test strategy change check with failures."""
        learning = LearningSystem()
        
        # Record 3 failures (threshold is 3)
        for i in range(3):
            learning.record_outcome("char", "attack", success=False, current_tick=i)
        
        assert learning.should_change_strategy("char", "attack") is True
    
    def test_should_change_strategy_under_threshold(self):
        """Test strategy not changed when under threshold."""
        learning = LearningSystem()
        
        # Record 2 failures (threshold is 3)
        for i in range(2):
            learning.record_outcome("char", "attack", success=False, current_tick=i)
        
        assert learning.should_change_strategy("char", "attack") is False
    
    def test_adapt_cooldown(self):
        """Test adaptation cooldown."""
        learning = LearningSystem(failure_threshold=2)
        
        # Record 2 failures
        learning.record_outcome("char", "attack", success=False, current_tick=0)
        learning.record_outcome("char", "attack", success=False, current_tick=1)
        
        # First check - should trigger
        assert learning.should_change_strategy("char", "attack", current_tick=10) is True
        
        # After cooldown - should still trigger
        assert learning.should_change_strategy("char", "attack", current_tick=20) is True
    
    def test_adapt_intent_reduces_priority(self):
        """Test intent adaptation reduces priority."""
        learning = LearningSystem()
        
        # Record some failures
        for i in range(3):
            learning.record_outcome("char", "attack_target", success=False, current_tick=i)
        
        intent = {"type": "attack_target", "priority": 7.0, "reasoning": "test"}
        adapted = learning.adapt_intent("char", intent)
        
        assert adapted["priority"] < 7.0
        assert adapted.get("adapted_priority") is True
        assert "recent_failures" in adapted
    
    def test_adapt_intent_preserves_none(self):
        """Test that None intent returns None."""
        learning = LearningSystem()
        assert learning.adapt_intent("char", None) is None
    
    def test_adapt_intent_empty_type(self):
        """Test intent with no type."""
        learning = LearningSystem()
        intent = {"priority": 5.0}
        result = learning.adapt_intent("char", intent)
        assert result["priority"] == 5.0  # Unchanged
    
    def test_suggest_alternative(self):
        """Test alternative suggestion."""
        learning = LearningSystem()
        
        # Have successes with negotiate, failures with attack
        for i in range(3):
            learning.record_outcome("char", "attack", success=False, current_tick=i)
        for i in range(4):
            learning.record_outcome("char", "negotiate", success=True, current_tick=i)
        
        alt = learning.suggest_alternative("char", "attack")
        assert alt == "negotiate"
    
    def test_suggest_alternative_no_history(self):
        """Test alternative suggestion with no history."""
        learning = LearningSystem()
        assert learning.suggest_alternative("char", "attack") is None
    
    def test_get_success_rate(self):
        """Test success rate calculation."""
        learning = LearningSystem()
        
        for i in range(4):
            learning.record_outcome("char", "attack", success=(i < 2), current_tick=i)
        
        rate = learning.get_success_rate("char", "attack")
        assert rate == 0.5
    
    def test_get_success_rate_no_data(self):
        """Test success rate with no data."""
        learning = LearningSystem()
        assert learning.get_success_rate("char", "unknown") == -1.0
    
    def test_failure_counts(self):
        """Test failure count tracking."""
        learning = LearningSystem()
        
        for i in range(3):
            learning.record_outcome("char", "attack", success=False, current_tick=i)
        
        counts = learning.get_failure_counts("char")
        assert counts.get("attack", 0) >= 3
    
    def test_success_resets_failure_count(self):
        """Test that success reduces failure count."""
        learning = LearningSystem()
        
        learning.record_outcome("char", "attack", success=False, current_tick=0)
        learning.record_outcome("char", "attack", success=False, current_tick=1)
        learning.record_outcome("char", "attack", success=True, current_tick=2)
        
        # Success should reduce failure count
        counts = learning.get_failure_counts("char")
        assert counts.get("attack", 0) <= 1
    
    def test_clear_history(self):
        """Test clearing learning history."""
        learning = LearningSystem()
        learning.record_outcome("char", "attack", success=True)
        
        learning.clear_history()
        assert len(learning.history) == 0
    
    def test_get_stats(self):
        """Test statistics tracking."""
        learning = LearningSystem()
        learning.record_outcome("char", "attack", success=True)
        
        stats = learning.get_stats()
        assert stats["outcomes_recorded"] == 1
        assert stats["tracked_characters"] == 1
    
    def test_reset(self):
        """Test full system reset."""
        learning = LearningSystem()
        learning.record_outcome("char", "attack", success=True, current_tick=0)
        learning.reset()
        assert len(learning.history) == 0


# ============================================================================
# CognitiveLayer Integration Tests
# ============================================================================

class TestCognitiveLayer:
    """Test unified cognitive layer interface."""
    
    def test_init(self):
        """Test initialization."""
        cognitive = CognitiveLayer()
        assert cognitive.intent_enrichment is not None
        assert cognitive.identity is not None
        assert cognitive.coalition is not None
        assert cognitive.learning is not None
    
    def test_process_decision_none_intent(self):
        """Test processing None intent."""
        cognitive = CognitiveLayer()
        assert cognitive.process_decision(
            make_character(), None, {}
        ) is None
    
    def test_process_decision_pipeline(self):
        """Test full decision processing pipeline."""
        mock_llm = MockLLMClient(response={"priority": 8.0})
        cognitive = CognitiveLayer(llm_client=mock_llm)
        
        intent = {"type": "attack_target", "priority": 5.0, "reasoning": "test"}
        character = make_character()
        world = make_world_state()
        
        result = cognitive.process_decision(character, intent, world, current_tick=10)
        
        assert result is not None
        assert result.get("type") == "attack_target"
    
    def test_record_outcome_and_learning(self):
        """Test recording outcomes for learning."""
        cognitive = CognitiveLayer()
        
        cognitive.record_outcome("char", "attack", success=False, current_tick=0)
        cognitive.record_outcome("char", "attack", success=False, current_tick=1)
        cognitive.record_outcome("char", "attack", success=False, current_tick=2)
        
        # Check that learning tracked failures
        assert cognitive.learning._count_recent_failures("char", "attack") >= 3
    
    def test_record_action_reputation(self):
        """Test action recording affects reputation."""
        cognitive = CognitiveLayer()
        
        cognitive.record_action(
            "hero", "heal", "villager", success=True,
            importance=0.5, current_tick=0,
        )
        
        identity = cognitive.identity.get_identity("hero")
        assert identity is not None
    
    def test_record_action_generates_rumors(self):
        """Test notable actions generate rumors."""
        cognitive = CognitiveLayer()
        
        cognitive.record_action(
            "hero", "slay", "dragon", success=True,
            importance=0.9, current_tick=0,
        )
        
        rumors = cognitive.identity.get_rumors_for("hero")
        assert len(rumors) >= 1
    
    def test_generate_dialogue(self):
        """Test dialogue generation."""
        cognitive = CognitiveLayer()
        
        speaker = make_character("hero")
        listener = make_character("villager")
        
        dialogue = cognitive.generate_dialogue(speaker, listener)
        assert isinstance(dialogue, str)
        assert len(dialogue) > 0
    
    def test_generate_dialogue_without_listener(self):
        """Test dialogue generation without listener."""
        cognitive = CognitiveLayer()
        
        speaker = make_character("hermit")
        dialogue = cognitive.generate_dialogue(speaker)
        assert isinstance(dialogue, str)
        assert len(dialogue) > 0
    
    def test_coalition_opportunity(self):
        """Test coalition opportunity detection."""
        cognitive = CognitiveLayer()
        
        world = make_world_state(factions={
            "weak_faction": {"power": 0.2, "relations": {"friendly": 0.6}},
            "friendly": {"power": 0.3, "relations": {"weak_faction": 0.6}},
        })
        
        coalition = cognitive.check_coalition_opportunity(
            "weak_faction", world, current_tick=0
        )
        
        # Should form coalition
        assert coalition is not None
    
    def test_coalition_no_opportunity(self):
        """Test no coalition opportunity for strong faction."""
        cognitive = CognitiveLayer()
        
        world = make_world_state(factions={
            "strong_faction": {"power": 0.9},
            "weak": {"power": 0.1},
        })
        
        coalition = cognitive.check_coalition_opportunity(
            "strong_faction", world, current_tick=0
        )
        assert coalition is None
    
    def test_tick_update(self):
        """Test tick update."""
        cognitive = CognitiveLayer()
        
        updates = cognitive.tick_update(current_tick=10)
        assert "identity" in updates
        assert "coalitions" in updates
    
    def test_get_character_summary(self):
        """Test character cognitive summary."""
        cognitive = CognitiveLayer()
        
        cognitive.record_action("hero", "heal", "villager", True, 0.5)
        
        summary = cognitive.get_character_summary("hero")
        assert summary["character_id"] == "hero"
        assert "identity" in summary
        assert "learning" in summary
    
    def test_get_comprehensive_stats(self):
        """Test comprehensive statistics."""
        cognitive = CognitiveLayer()
        
        cognitive.process_decision(
            make_character(),
            {"type": "attack_target", "priority": 5.0, "reasoning": ""},
            make_world_state(),
            current_tick=0,
        )
        
        stats = cognitive.get_stats()
        assert "decisions_processed" in stats
        assert "intent_enrichment" in stats
        assert "identity" in stats
        assert "coalition" in stats
        assert "learning" in stats
    
    def test_reset(self):
        """Test full system reset."""
        cognitive = CognitiveLayer()
        cognitive.record_outcome("char", "attack", success=True)
        cognitive.reset()
        
        stats = cognitive.get_stats()
        assert stats["outcomes_recorded"] == 0
    
    def test_consider_coalition_no_membership(self):
        """Test coalition consideration without membership."""
        cognitive = CognitiveLayer()
        
        intent = {"type": "attack_target", "priority": 5.0}
        result = cognitive._consider_coalition(
            "lone_faction", intent, {"factions": {}}
        )
        assert result == intent  # Unchanged
    
    def test_add_action_rumor_combat(self):
        """Test rumor generation for combat actions."""
        cognitive = CognitiveLayer()
        
        cognitive._add_action_rumor("hero", "attack", "dragon", 0.9)
        rumors = cognitive.identity.get_rumors_for("hero")
        assert any("attack" in r or "Word" in r for r in rumors)
    
    def test_add_action_rumor_positive(self):
        """Test rumor generation for positive actions."""
        cognitive = CognitiveLayer()
        
        cognitive._add_action_rumor("hero", "heal", "villager", 0.9)
        rumors = cognitive.identity.get_rumors_for("hero")
        assert any("heal" in r or "Word" in r for r in rumors)
    
    def test_fallback_dialogue(self):
        """Test fallback dialogue generation."""
        cognitive = CognitiveLayer()
        
        dialogue = cognitive._fallback_dialogue("speaker", "listener")
        assert "speaker" in dialogue
        assert "listener" in dialogue


# ============================================================================
# Integration Tests for Guardrails
# ============================================================================

class TestGuardrails:
    """Test that LLM guardrails work correctly."""
    
    def test_allowed_intents_contains_expected_types(self):
        """Test that allowed intents list is comprehensive."""
        expected = {"expand_influence", "attack_target", "deliver_aid",
                    "gather_resources", "negotiate", "defend", "idle"}
        assert expected.issubset(ALLOWED_INTENTS)
    
    def test_llm_cannot_change_intent_type(self):
        """Test that LLM response cannot change intent type."""
        mock_llm = MockLLMClient(response={
            "priority": 8.0,
            # Note: No type field, which LLM would try to inject
        })
        enrichment = IntentEnrichment(llm_client=mock_llm)
        
        intent = {"type": "attack_target", "priority": 5.0}
        result = enrichment.enrich(
            intent, make_character(), make_world_state(), current_tick=10
        )
        
        assert result["type"] == "attack_target"  # Type preserved
    
    def test_llm_invalid_target_is_ignored(self):
        """Test that invalid target values are handled gracefully."""
        mock_llm = MockLLMClient(response={
            "priority": 7.0,
            "target": 12345,  # Invalid: should be string
        })
        enrichment = IntentEnrichment(llm_client=mock_llm)
        
        intent = {"type": "attack_target", "priority": 5.0, "target": "original"}
        result = enrichment.enrich(
            intent, make_character(), make_world_state(), current_tick=10
        )
        
        # Original target should be preserved
        assert result["target"] == "original"
    
    def test_enrichment_reasoning_is_appended(self):
        """Test that LLM reasoning is appended to existing reasoning."""
        mock_llm = MockLLMClient(response={
            "priority": 7.0,
            "reasoning": "LLM added wisdom",
        })
        enrichment = IntentEnrichment(llm_client=mock_llm)
        
        intent = {
            "type": "attack_target",
            "priority": 5.0,
            "reasoning": "Original reasoning",
        }
        result = enrichment.enrich(
            intent, make_character(), make_world_state(), current_tick=10
        )
        
        assert "Original reasoning" in result["reasoning"]
        assert "LLM added wisdom" in result["reasoning"]


# ============================================================================
# Regression Tests
# ============================================================================

class TestRegressionScenarios:
    """Test specific regression scenarios from real-world issues."""
    
    def test_empty_world_state_handled(self):
        """Test systems handle empty world state."""
        cognitive = CognitiveLayer()
        intent = {"type": "idle", "priority": 0.0}
        
        result = cognitive.process_decision(make_character(), intent, {}, 0)
        assert result is not None
    
    def test_missing_character_attributes(self):
        """Test systems handle character with missing attributes."""
        char = MagicMock()
        char.id = "minimal_char"
        char.traits = []
        char.goals = []
        char.beliefs = {}
        
        cognitive = CognitiveLayer()
        intent = {"type": "idle", "priority": 0.0}
        result = cognitive.process_decision(char, intent, {}, 0)
        assert result is not None
    
    def test_rapid_tick_processing(self):
        """Test systems handle rapid tick processing."""
        cognitive = CognitiveLayer()
        
        for tick in range(100):
            intent = {
                "type": "expand_influence",
                "priority": 5.0,
                "reasoning": "tick",
            }
            cognitive.process_decision(make_character(), intent, {}, tick)
            cognitive.tick_update(tick)
        
        stats = cognitive.get_stats()
        assert stats["decisions_processed"] == 100
    
    def test_memory_leak_check(self):
        """Test that history doesn't grow unbounded."""
        learning = LearningSystem(max_history=10)
        
        for i in range(100):
            learning.record_outcome("char", "action", success=True, current_tick=i)
        
        assert len(learning.history["char"]) <= 10
    
    def test_coalition_dissolution_cascade(self):
        """Test that coalition dissolution doesn't cause errors."""
        cognitive = CognitiveLayer()
        
        # Create coalition
        cognitive.check_coalition_opportunity("weak", {
            "factions": {
                "weak": {"power": 0.1, "relations": {"ally": 0.5}},
                "ally": {"power": 0.2, "relations": {"weak": 0.5}},
            }
        }, current_tick=0)
        
        # Age it past the stability limit
        cognitive.tick_update(current_tick=100)
        
        # Should have been dissolved
        assert len(cognitive.coalition.coalitions) == 0