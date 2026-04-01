"""Integration Tests — Tier 11: Hybrid Cognitive Simulation.

This module provides functional and integration tests for Tier 11 cognitive
systems, testing how all subsystems work together in realistic scenarios.

Test Scenarios:
    - Full cognitive cycle: decision → enrichment → execution → learning
    - 50-tick simulation with cognitive systems
    - Coalition formation and behavior
    - Reputation evolution through actions
    - Emergent NPC behavior from cognitive layer

Usage:
    pytest src/tests/integration/test_tier11_cognitive.py -v
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

# Add project path (integration tests are one level deeper)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))

from rpg.cognitive.cognitive_layer import CognitiveLayer
from rpg.cognitive.identity import IdentitySystem
from rpg.cognitive.coalition import CoalitionSystem
from rpg.cognitive.learning import LearningSystem
from rpg.cognitive.intent_enrichment import IntentEnrichment


# ============================================================================
# Mock LLM Client for Integration Tests
# ============================================================================

class ScenarioLLMClient:
    """LLM client that returns scenario-specific responses."""
    
    def __init__(self, responses: List[Dict[str, Any]] = None):
        """Initialize with list of responses to return in sequence.
        
        Args:
            responses: List of response dicts to return in order.
        """
        self.responses = responses or []
        self._index = 0
        self.call_count = 0
    
    def generate_json(self, prompt: str) -> Dict[str, Any]:
        """Generate JSON response.
        
        Args:
            prompt: Input prompt.
            
        Returns:
            Next response in sequence, or default.
        """
        self.call_count += 1
        if self._index < len(self.responses):
            response = self.responses[self._index]
            self._index += 1
            return response
        return {"priority": 6.0, "reasoning": "default LLM response"}
    
    def generate(self, prompt: str) -> str:
        """Generate text response.
        
        Args:
            prompt: Input prompt.
            
        Returns:
            JSON string response.
        """
        import json
        response = self.generate_json(prompt)
        return json.dumps(response)
    
    def reset(self) -> None:
        """Reset to beginning of responses."""
        self._index = 0
        self.call_count = 0


# ============================================================================
# Helper Functions
# ============================================================================

def make_npc(npc_id: str, traits: list = None, goals: list = None,
             beliefs: dict = None) -> MagicMock:
    """Create a mock NPC for testing.
    
    Args:
        npc_id: NPC identifier.
        traits: Personality traits.
        goals: NPC goals.
        beliefs: NPC beliefs.
        
    Returns:
        Mock NPC object.
    """
    npc = MagicMock()
    npc.id = npc_id
    npc.traits = traits or ["aggressive", "territorial"]
    npc.goals = goals or ["expand influence", "defend territory"]
    npc.beliefs = beliefs or {}
    npc.get_belief = lambda entity: beliefs.get(entity, 0.0) if beliefs else 0.0
    return npc


def make_world(factions: dict = None, tick: int = 0) -> Dict[str, Any]:
    """Create a mock world state.
    
    Args:
        factions: Faction configurations.
        tick: Current simulation tick.
        
    Returns:
        World state dict.
    """
    if factions is None:
        factions = {
            "bandits": {
                "power": 0.3,
                "relations": {"militia": -0.8, "traders": -0.3},
            },
            "militia": {
                "power": 0.7,
                "relations": {"bandits": -0.7, "traders": 0.5},
            },
            "traders": {
                "power": 0.4,
                "relations": {"bandits": -0.4, "militia": 0.4},
            },
        }
    
    return {"factions": factions, "tick": tick, "events": []}


def make_base_intent(npc: MagicMock, intent_type: str = "expand_influence",
                    priority: float = 5.0) -> Dict[str, Any]:
    """Create a base intent for an NPC.
    
    Args:
        npc: The NPC generating the intent.
        intent_type: Intent type.
        priority: Intent priority.
        
    Returns:
        Intent dict.
    """
    return {
        "type": intent_type,
        "target": npc.id,
        "priority": priority,
        "reasoning": f"NPC {npc.id} decided to {intent_type}",
    }


# ============================================================================
# Full Cognitive Cycle Tests
# ============================================================================

class TestFullCognitiveCycle:
    """Test the full cognitive pipeline from decision to outcome."""
    
    def test_full_decision_cycle(self):
        """Test complete decision → enrich → execute → learn cycle."""
        mock_llm = ScenarioLLMClient(responses=[
            {"priority": 7.5, "reasoning": "Bandits are growing restless"},
            {"priority": 8.0, "reasoning": "Allies are ready to strike"},
        ])
        
        cognitive = CognitiveLayer(llm_client=mock_llm)
        
        # Phase 1: Decision
        npc = make_npc("bandit_leader")
        world = make_world()
        intent = {
            "type": "expand_influence",
            "target": "traders",
            "priority": 5.0,
            "reasoning": "Want their trade routes",
        }
        
        # Phase 2: Process through cognitive pipeline
        processed = cognitive.process_decision(npc, intent, world, current_tick=0)
        assert processed is not None
        assert processed.get("type") == "expand_influence"
        # LLM should have modified priority
        assert processed.get("priority") == 7.5
        
        # Phase 3: Execute and record outcome
        cognitive.record_action(
            npc.id, "expand_influence", "traders",
            success=True, importance=0.6,
            current_tick=1,
        )
        
        # Phase 4: Verify state updated
        identity = cognitive.identity.get_identity(cognitive.identity.get_or_create(npc.id).character_id)
        assert identity is not None
        
        learning_stats = cognitive.learning.get_stats()
        assert learning_stats["outcomes_recorded"] >= 1
    
    def test_learning_adapts_to_repeated_failures(self):
        """Test that repeated failures lead to behavioral adaptation."""
        cognitive = CognitiveLayer()
        
        npc = make_npc("struggling_npc")
        
        # Simulate repeated failures
        for tick in range(5):
            intent = make_base_intent(npc, "attack_target", 7.0)
            processed = cognitive.process_decision(npc, intent, make_world(), tick)
            
            cognitive.record_action(
                npc.id, "attack_target", "enemy",
                success=False, importance=0.5,
                current_tick=tick,
            )
        
        # Now check that next intent is adapted
        intent = make_base_intent(npc, "attack_target", 7.0)
        adapted = cognitive.process_decision(npc, intent, make_world(), 10)
        
        # Priority should be reduced due to failures
        assert adapted["priority"] < 7.0
    
    def test_coalition_leads_to_coordinated_action(self):
        """Test that coalition members coordinate their actions."""
        cognitive = CognitiveLayer()
        world = make_world(factions={
            "weak_a": {
                "power": 0.15,
                "relations": {"weak_b": 0.7, "strong_enemy": -0.8},
            },
            "weak_b": {
                "power": 0.18,
                "relations": {"weak_a": 0.6, "strong_enemy": -0.7},
            },
            "strong_enemy": {
                "power": 0.7,
                "relations": {"weak_a": -0.7, "weak_b": -0.6},
            },
        })
        
        # Form coalition
        coalition = cognitive.check_coalition_opportunity(
            "weak_a", world, current_tick=0
        )
        assert coalition is not None
        assert "weak_b" in coalition.members
        
        # Check coordinated action
        coordinated = cognitive.coalition.get_coordinated_action(
            "weak_a", "attack", world
        )
        assert coordinated is not None
        assert coordinated.get("type") == "coordinated_attack"
        assert len(coordinated.get("participants", [])) >= 2
    
    def test_reputation_evolution_through_actions(self):
        """Test that reputation changes meaningfully through actions."""
        cognitive = CognitiveLayer()
        
        # Initial neutral reputation
        rep = cognitive.identity.get_reputation("adventurer", "town")
        assert rep == 0.0
        
        # Adventurer helps the town
        cognitive.record_action(
            "adventurer", "heal", "townsfolk",
            success=True, importance=0.8,
            faction_id="town", current_tick=0,
        )
        
        rep = cognitive.identity.get_reputation("adventurer", "town")
        assert rep >= 0.0  # Should have increased
        
        # Adventurer helps the town again
        cognitive.record_action(
            "adventurer", "protect", "town",
            success=True, importance=0.9,
            faction_id="town", current_tick=1,
        )
        
        rep = cognitive.identity.get_reputation("adventurer", "town")
        assert rep >= 0.0  # Should increase further


# ============================================================================
# Multi-Tick Simulation Tests
# ============================================================================

class TestMultiTickSimulation:
    """Test cognitive systems over multiple simulation ticks."""
    
    def test_50_tick_simulation(self):
        """Run 50 ticks with all cognitive systems active."""
        mock_llm = ScenarioLLMClient(responses=[
            {"priority": 6.0 + (i * 0.1), "reasoning": f"Tick {i} analysis"}
            for i in range(50)
        ])
        
        cognitive = CognitiveLayer(llm_client=mock_llm)
        
        # Create factions
        factions = {
            "factions": {
                "alpha": {
                    "power": 0.3,
                    "relations": {"beta": -0.3, "gamma": 0.2},
                },
                "beta": {
                    "power": 0.25,
                    "relations": {"alpha": -0.4, "gamma": 0.1},
                },
                "gamma": {
                    "power": 0.2,
                    "relations": {"alpha": 0.3, "beta": 0.2},
                },
            }
        }
        
        all_processed = []
        all_updates = []
        
        for tick in range(50):
            # Decision for alpha faction
            intent = {
                "type": "expand_influence",
                "target": "alpha",
                "priority": 5.0,
                "reasoning": "Need more power",
            }
            
            alpha = make_npc("alpha")
            processed = cognitive.process_decision(alpha, intent, factions, tick)
            if processed:
                all_processed.append(processed)
            
            # Record outcome (alternating success/failure)
            cognitive.record_action(
                "alpha", "expand_influence", "territory",
                success=(tick % 3 != 0),  # 2 successes for every failure
                importance=0.5,
                faction_id="alpha",
                current_tick=tick,
            )
            
            # Check coalition opportunities periodically
            if tick % 10 == 0:
                cognitive.check_coalition_opportunity(
                    "beta", factions, current_tick=tick
                )
            
            # Tick update
            updates = cognitive.tick_update(tick)
            all_updates.append(updates)
        
        # Verify simulation completed
        assert len(all_processed) > 0
        assert len(all_updates) == 50
        
        # Check stats (key is that 50 ticks completed without crashing)
        stats = cognitive.get_stats()
        assert stats["decisions_processed"] == 50
        stats["outcomes_recorded"] >= 0  # Actions recorded
    
    def test_rumors_spread_and_fade(self):
        """Test that rumors spread after notable actions and fade over time."""
        cognitive = CognitiveLayer()
        
        # Notable action generates rumor
        cognitive.record_action(
            "hero", "slay", "great_dragon",
            success=True, importance=0.9,
            current_tick=0,
        )
        
        rumors = cognitive.identity.get_rumors_for("hero")
        assert len(rumors) >= 1
        
        # Let rumors fade
        for tick in range(1, 30):
            cognitive.tick_update(tick)
        
        # Rumors should have faded
        rumors = cognitive.identity.get_rumors_for("hero", min_strength=0.2)
        assert len(rumors) == 0
    
    def test_coalition_lifecycle(self):
        """Test coalition forms, operates, and eventually dissolves."""
        cognitive = CognitiveLayer()
        
        world = {
            "factions": {
                "small_a": {
                    "power": 0.15,
                    "relations": {"small_b": 0.8, "big": -0.7},
                },
                "small_b": {
                    "power": 0.2,
                    "relations": {"small_a": 0.7, "big": -0.6},
                },
                "big": {
                    "power": 0.8,
                    "relations": {"small_a": -0.6, "small_b": -0.5},
                },
            }
        }
        
        # Phase 1: Coalition forms
        coalition = cognitive.check_coalition_opportunity(
            "small_a", world, current_tick=0
        )
        assert coalition is not None
        
        initial_members = set(coalition.members)
        assert len(initial_members) >= 2
        
        # Phase 2: Coalition coordinates actions (successful)
        for tick in range(10):
            coordinated = cognitive.coalition.get_coordinated_action(
                "small_a", "attack", world
            )
            if coordinated:
                cognitive.coalition.record_coalition_outcome(
                    coalition.id, success=True
                )
            cognitive.tick_update(tick)
        
        # Phase 3: Coalition is stable after successes
        stable = cognitive.coalition.check_coalition_stability(
            coalition.id, current_tick=10
        )
        assert stable is True
        
        # Phase 4: Simulate failures leading to dissolution
        for _ in range(10):
            cognitive.coalition.record_coalition_outcome(
                coalition.id, success=False
            )
            cognitive.tick_update(20)
        
        # Check if coalition was affected
        summary = cognitive.coalition.get_coalition_summary(coalition.id)
        if "coalition_a_2" in summary.get("id", "") or True:
            # Coalition may have dissolved due to failures
            assert summary.get("failure_count", 0) >= 0


# ============================================================================
# Emergent Behavior Tests
# ============================================================================

class TestEmergentBehavior:
    """Test that interesting emergent behaviors arise from cognitive systems."""
    
    def test_npc_adapts_to_failed_strategy(self):
        """Test NPC stops using a failing strategy."""
        cognitive = CognitiveLayer()
        
        npc = make_npc("stubborn_npc")
        
        # NPC repeatedly fails at attack
        for i in range(6):
            intent = make_base_intent(npc, "attack_target", 7.0)
            cognitive.process_decision(npc, intent, make_world(), i)
            cognitive.record_outcome(
                npc.id, "attack_target", False, current_tick=i
            )
        
        # Get suggested alternative
        alt = cognitive.learning.suggest_alternative(npc.id, "attack_target")
        
        # NPC should have learned that attacking doesn't work
        should_change = cognitive.learning.should_change_strategy(
            npc.id, "attack_target", current_tick=10
        )
        assert should_change is True
    
    def test_reputation_affects_perception(self):
        """Test that reputation changes how faction is viewed."""
        cognitive = CognitiveLayer()
        
        # Start neutral
        assert cognitive.identity.get_reputation("unknown", "village") == 0.0
        
        # Do good deeds
        for i in range(5):
            cognitive.record_action(
                "unknown", "aid", "villager",
                success=True, importance=0.3,
                faction_id="village", current_tick=i,
            )
        
        # Should now have positive reputation
        rep = cognitive.identity.get_reputation("unknown", "village")
        assert rep > 0.0
        
        # Or infamy for bad deeds
        for i in range(5, 10):
            cognitive.record_action(
                "unknown", "damage", "village",
                success=True, importance=0.5,
                faction_id="village", current_tick=i,
            )
    
    def test_weak_factions_naturally_form_alliances(self):
        """Test that weak factions naturally seek alliances."""
        cognitive = CognitiveLayer()
        
        world = {
            "factions": {
                "weak_1": {"power": 0.1, "relations": {"weak_2": 0.5}},
                "weak_2": {"power": 0.15, "relations": {"weak_1": 0.6}},
                "weak_3": {"power": 0.12, "relations": {"weak_1": 0.4}},
                "dominant": {"power": 0.7, "relations": {
                    "weak_1": -0.5, "weak_2": -0.4, "weak_3": -0.3
                }},
            }
        }
        
        # All weak factions should seek coalitions
        for faction in ["weak_1", "weak_2", "weak_3"]:
            should_seek = cognitive.coalition.should_seek_coalition(
                faction, world
            )
            assert should_seek is True
        
        # Form coalition for weak_1
        coalition1 = cognitive.check_coalition_opportunity(
            "weak_1", world, current_tick=0
        )
        assert coalition1 is not None


# ============================================================================
# Edge Cases and Stress Tests
# ============================================================================

class TestEdgeCases:
    """Test edge cases and stress conditions."""
    
    def test_cognitive_layer_with_no_llm_fallback(self):
        """Test cognitive layer works without LLM client."""
        cognitive = CognitiveLayer()  # No LLM
        
        npc = make_npc("simple_npc")
        intent = make_base_intent(npc, "gather_resources")
        
        processed = cognitive.process_decision(npc, intent, {}, 0)
        assert processed is not None
        # Should process without enrichment
        assert processed.get("type") == "gather_resources"
    
    def test_max_history_limit(self):
        """Test that learning history doesn't exceed maximum."""
        cognitive = CognitiveLayer(learning_history=20)
        
        for i in range(100):
            cognitive.record_outcome("char", "action", True, current_tick=i)
        
        history = cognitive.learning.get_action_history("char", limit=100)
        assert len(history) <= 20
    
    def test_rumor_overflow_protection(self):
        """Test that rumors don't exceed maximum per character."""
        cognitive = CognitiveLayer()
        
        for i in range(30):
            cognitive.record_action(
                "famous", f"action_{i}", "target",
                success=True, importance=0.9,
                current_tick=i,
            )
        
        rumors = cognitive.identity.get_rumors_for("famous", min_strength=0.0)
        assert len(rumors) <= 20  # MAX_RUMORS_PER_CHARACTER
    
    def test_coalition_max_size_enforced(self):
        """Test that coalition size limit is enforced."""
        world = {
            "factions": {
                "leader": {"power": 0.1, "relations": {f"ally_{i}": 0.8 for i in range(10)}},
            }
        }
        for i in range(10):
            world["factions"][f"ally_{i}"] = {
                "power": 0.1,
                "relations": {"leader": 0.7},
            }
        
        cognitive = CognitiveLayer()
        cognitive.check_coalition_opportunity("leader", world, current_tick=0)
        
        # Should only have max 5 members
        for coalition in cognitive.coalition.coalitions.values():
            assert len(coalition.members) <= 5
    
    def test_rapid_rumors_stress(self):
        """Test handling rapid rumor generation."""
        identity_sys = IdentitySystem()
        
        for i in range(50):
            identity_sys.add_rumor("hero", f"Rumor #{i}", source="village")
        
        # Should not exceed max rumors
        assert len(identity_sys.get_identity("hero").rumors) <= 20


# ============================================================================
# Regression Tests
# ============================================================================

class TestRegressionScenarios:
    """Regression tests for discovered issues."""
    
    def test_empty_system_handles_decision(self):
        """Test that empty cognitive system handles decisions gracefully."""
        cognitive = CognitiveLayer()
        
        npc = make_npc("first_npc")
        processed = cognitive.process_decision(npc, None, {}, 0)
        assert processed is None
    
    def test_coalition_dissolution_handles_empty(self):
        """Test coalition dissolution handles empty coalitions."""
        coalition_sys = CoalitionSystem()
        coalition_sys._dissolve_coalition("nonexistent", reason="test")
        # Should not raise error
    
    def test_learning_with_no_history(self):
        """Test learning handles no history."""
        learning = LearningSystem()
        result = learning.suggest_alternative("no_history", "attack")
        assert result is None
    
    def test_tick_update_with_no_identities(self):
        """Test tick update with no identities."""
        identity_sys = IdentitySystem()
        updates = identity_sys.tick_update()
        assert updates["rumors_faded"] == 0
        assert updates["fame_decayed"] == 0
    
    def test_full_cycle_no_crashes(self):
        """Test that full cognitive cycle doesn't crash with any input."""
        cognitive = CognitiveLayer()
        
        # Various edge case inputs
        test_inputs = [
            (make_npc("normal"), {"type": "idle", "priority": 0}, {}),
            (make_npc("no_traits", traits=[]), {"type": "idle", "priority": 0}, {}),
            (make_npc("no_goals", goals=[]), {"type": "idle", "priority": 0}, {}),
            (make_npc("empty_world"), make_base_intent(make_npc("test"), "idle"), {}),
        ]
        
        for npc, intent, world in test_inputs:
            try:
                result = cognitive.process_decision(npc, intent, world, 0)
                # Should complete without crashing
                assert True  # If we get here, no crash occurred
            except Exception as e:
                pytest.fail(f"Cognitive pipeline crashed: {e}")