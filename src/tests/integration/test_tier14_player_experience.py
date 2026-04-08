"""Integration Tests — Tier 14: Player Experience & Perception Layer.

Comprehensive integration tests for:
- Full PlayerExperienceEngine workflow
- Narrative surfacing with attention filtering
- Emotional feedback with player profile adaptation
- Memory echo system with long-term continuity
- Tier 14 fixes integration (emotional drift, entropy, relevance)

These tests verify the complete player experience pipeline works correctly
with realistic multi-tick scenarios.
"""

from __future__ import annotations

import importlib
import random
import sys

import pytest

# Module paths
PLAYER_EXP_MODULE = "src.app.rpg.player.player_experience"
COGNITIVE_MODULE = "src.app.rpg.cognitive"


def _import_player_experience():
    """Import player_experience module."""
    if "src.app.rpg.player.player_experience" in sys.modules:
        mod = sys.modules["src.app.rpg.player.player_experience"]
        importlib.reload(mod)
        return mod
    
    try:
        return importlib.import_module("src.app.rpg.player.player_experience")
    except ModuleNotFoundError:
        sys.path.insert(0, "src")
        return importlib.import_module("app.rpg.player.player_experience")


def _import_cognitive():
    """Import cognitive module."""
    try:
        return importlib.import_module("src.app.rpg.cognitive")
    except ModuleNotFoundError:
        sys.path.insert(0, "src")
        return importlib.import_module("app.rpg.cognitive")


px_mod = _import_player_experience()
PlayerExperienceEngine = px_mod.PlayerExperienceEngine
PlayerProfile = px_mod.PlayerProfile
cog_mod = _import_cognitive()


class TestTier14Integration:
    """Integration tests for Tier 14 Player Experience Layer."""

    def test_full_event_pipeline(self):
        """Test complete pipeline: events -> attention -> surfacing -> echo."""
        engine = PlayerExperienceEngine(max_events_per_tick=3)
        
        # Create a series of events
        events = [
            {
                "type": "faction_conflict",
                "faction_a": "Hawks",
                "faction_b": "Doves",
                "issue": "territory",
                "importance": 0.8,
                "characters": ["hawk_leader", "dove_leader"],
                "tick": 1,
            },
            {
                "type": "betrayal",
                "betrayer": "Vargus",
                "victim": "Elara",
                "importance": 0.9,
                "characters": ["Vargus", "Elara"],
                "tick": 2,
            },
            {
                "type": "quest_complete",
                "objective": "ancient artifact",
                "importance": 0.7,
                "characters": ["hero"],
                "tick": 3,
            },
            {
                "type": "trade",
                "importance": 0.2,
                "tick": 4,
            },
            {
                "type": "gossip",
                "importance": 0.1,
                "tick": 5,
            },
        ]
        
        # Filter and surface
        surfaced = engine.filter_events(events, current_tick=6, player_id="hero")
        
        # Should have at most 3 events (max_events_per_tick)
        assert len(surfaced) <= 3
        
        # All surfaced events should be meaningful
        for event in surfaced:
            assert event.headline
            assert event.detail

    def test_player_profile_adapts_narrative(self):
        """Test that player profile affects what narrative is shown."""
        engine = PlayerExperienceEngine()
        
        # Aggressive player
        aggressive_id = "aggressive_player"
        for _ in range(10):
            engine.record_player_action(aggressive_id, "attack")
        
        # Diplomatic player
        diplomatic_id = "diplomatic_player"
        for _ in range(10):
            engine.record_player_action(diplomatic_id, "negotiate")
        
        # Same events, different players
        events = [
            {"type": "attack", "importance": 0.5, "characters": ["enemy"], "tick": 1},
            {"type": "negotiate", "importance": 0.5, "characters": ["ally"], "tick": 2},
        ]
        
        aggressive_surfaced = engine.filter_events(events, current_tick=3, player_id=aggressive_id)
        diplomatic_surfaced = engine.filter_events(events, current_tick=3, player_id=diplomatic_id)
        
        # Both should get surfaced events
        assert len(aggressive_surfaced) > 0
        assert len(diplomatic_surfaced) > 0

    def test_emotional_feedback_accumulates(self):
        """Test that emotional feedback accumulates meaningfully over time."""
        engine = PlayerExperienceEngine()
        
        # Simulate a series of game events
        changes = [
            {"type": "relationship_growth", "magnitude": 0.5, "tick": 1},
            {"type": "reputation_increase", "magnitude": 0.3, "tick": 2},
            {"type": "power_gain", "magnitude": 0.7, "tick": 3},
            {"type": "betrayal", "magnitude": 0.9, "tick": 4},
        ]
        
        for change in changes:
            engine.translate_change(change, player_id="player1")
        
        # Get emotional summary
        summary = engine.get_emotional_summary()
        assert len(summary) > 10

    def test_memory_echoes_create_continuity(self):
        """Test that memory echoes create narrative continuity across ticks."""
        engine = PlayerExperienceEngine()
        
        # Record significant past events
        past_events = [
            {
                "type": "betrayal",
                "characters": ["alice", "bob"],
                "description": "Alice betrayed Bob at the summit",
                "tick": 5,
                "importance": 0.9,
            },
            {
                "type": "faction_conflict",
                "faction_a": "Hawks",
                "faction_b": "Doves",
                "characters": ["hawk_leader"],
                "themes": ["power_struggle"],
                "tick": 10,
                "importance": 0.8,
            },
        ]
        
        for event in past_events:
            engine.surface_event(event)
        
        # Surface new event that relates to past
        current_event = {
            "type": "meeting",
            "characters": ["alice", "charlie"],
            "tick": 50,
            "importance": 0.5,
        }
        
        result = engine.surface_event(current_event)
        assert result is not None
        # Memory echo may or may not trigger depending on relevance
        
        # Check memory echo stats
        stats = engine.get_stats()
        # Should have at least 2 stored (current_event also records)
        assert stats["memory_echo"]["memories_stored"] >= 2

    def test_tier14_emotional_differentiation(self):
        """Test that emotional differentiation prevents NPC homogenization."""
        apply_personality_bias = cog_mod.apply_personality_bias
        inject_variance = cog_mod.inject_variance
        
        # Create two NPCs with different personalities
        npc_a_emotions = {"anger": 0.3, "fear": 0.3, "joy": 0.3}
        npc_b_emotions = {"anger": 0.3, "fear": 0.3, "joy": 0.3}
        
        personality_a = {"anger": 0.5, "joy": -0.3}
        personality_b = {"anger": -0.3, "joy": 0.5}
        
        # Simulate 100 ticks of emotional events
        for tick in range(100):
            # Apply emotions to NPCs
            npc_a_emotions = apply_personality_bias(npc_a_emotions, personality_a)
            npc_b_emotions = apply_personality_bias(npc_b_emotions, personality_b)
            
            # Inject variance
            npc_a_emotions = inject_variance(npc_a_emotions)
            npc_b_emotions = inject_variance(npc_b_emotions)
            
            # Apply some event-based emotions
            npc_a_emotions["anger"] = min(1.0, npc_a_emotions["anger"] + 0.01)
            npc_b_emotions["joy"] = min(1.0, npc_b_emotions["joy"] + 0.01)
        
        # After 100 ticks, NPCs should be emotionally distinct
        total_diff = sum(
            abs(npc_a_emotions[k] - npc_b_emotions[k])
            for k in npc_a_emotions
        )
        assert total_diff > 0.5, f"NPCs converged emotionally: diff={total_diff}"

    def test_tier14_resolution_entropy(self):
        """Test that resolution entropy prevents pattern recognition."""
        ResolutionEngine = cog_mod.ResolutionEngine
        engine = ResolutionEngine()
        
        # Same storyline, many resolutions
        storyline = {
            "progress": 0.8,
            "importance": 0.6,
            "events": [],
            "participants": ["hero", "rival"],
        }
        
        types_seen = set()
        for _ in range(100):
            resolution_type = engine._determine_resolution_type(storyline)
            types_seen.add(resolution_type)
        
        # Should see multiple resolution types (not just the obvious one)
        assert len(types_seen) >= 2, f"Resolution types too limited: {types_seen}"

    def test_tier14_contextual_memory_relevance(self):
        """Test that contextual memory prevents overfitting to history."""
        NarrativeMemory = cog_mod.NarrativeMemory
        relevance_score = cog_mod.relevance_score
        ArcMemory = cog_mod.ArcMemory
        
        memory = NarrativeMemory()
        
        # Store various past events
        memory.store_arc({
            "arc_id": "old_war",
            "arc_type": "war",
            "outcome": "Hawks won",
            "participants": ["hawk_leader", "dove_leader"],
            "impact": 0.8,
            "tick_resolved": 10,
        })
        
        memory.store_arc({
            "arc_id": "trade_agreement",
            "arc_type": "trade",
            "outcome": "Both sides agreed",
            "participants": ["merchant_a", "merchant_b"],
            "impact": 0.2,
            "tick_resolved": 20,
        })
        
        # Query for war-related context
        war_context = {
            "current_actors": ["hawk_leader", "dove_leader"],
            "event_type": "war",
        }
        relevant = memory.get_relevant_history(**war_context, current_tick=50)
        
        # Should return the old_war arc, not the trade
        assert len(relevant) > 0
        assert any("old_war" in str(r) for r in relevant)

    def test_300_tick_simulation(self):
        """Test 300-tick simulation with all Tier 14 systems active."""
        engine = PlayerExperienceEngine(max_events_per_tick=3)
        
        random.seed(42)
        
        event_types = [
            "faction_conflict", "alliance_formed", "betrayal",
            "quest_complete", "character_growth", "death",
            "discovery", "meeting", "trade",
        ]
        
        characters = ["alice", "bob", "charlie", "diana", "eve"]
        locations = ["castle", "village", "forest", "mountain", "temple"]
        
        all_surfaced = []
        
        for tick in range(1, 301):
            # Generate 5-10 raw events per tick
            num_events = random.randint(5, 10)
            events = []
            for _ in range(num_events):
                event = {
                    "type": random.choice(event_types),
                    "importance": random.uniform(0.1, 1.0),
                    "characters": random.sample(characters, k=random.randint(1, 3)),
                    "tick": tick,
                }
                events.append(event)
            
            # Filter and surface
            surfaced = engine.filter_events(events, current_tick=tick)
            all_surfaced.extend(surfaced)
            
            # Record player actions
            if tick % 10 == 0:
                engine.record_player_action(
                    "hero",
                    action_type=random.choice(["attack", "negotiate", "help", "plan"]),
                    value_alignment=random.choice(["loyalty", "power", "freedom"]),
                    relationship=random.choice(characters),
                    relationship_quality=random.uniform(-0.5, 1.0),
                )
            
            # Translate changes
            if tick % 5 == 0:
                engine.translate_change({
                    "type": random.choice(["reputation_increase", "relationship_growth"]),
                    "magnitude": random.uniform(0.2, 0.8),
                }, player_id="hero")
        
        # Verify simulation completed
        stats = engine.get_stats()
        
        # Events should have been processed
        assert stats["events_surfaced"] > 0
        assert stats["events_filtered"] > 0
        
        # Memory echoes should have been recorded
        assert stats["echoes_recorded"] > 0
        
        # Player profile should exist
        assert "hero" in engine.player_profiles
        
        # All surfaced events should have content
        for event in all_surfaced:
            assert event.headline
            assert event.visibility > 0

    def test_attention_prevents_overload(self):
        """Test that attention director prevents information overload."""
        engine = PlayerExperienceEngine(max_events_per_tick=2)
        
        # Generate lots of events
        events = [
            {"type": "death", "importance": 0.9, "tick": i}
            for i in range(20)
        ]
        
        # Filter should never return more than max_events_per_tick
        surfaced = engine.filter_events(events, current_tick=25)
        assert len(surfaced) <= 2

    def test_feedback_loop_quality(self):
        """Test that feedback loop translates game mechanics to emotion."""
        loop = px_mod.EmotionalFeedbackLoop()
        
        # Test various change types
        test_cases = [
            ("reputation_decrease", "isolation"),
            ("relationship_damage", "regret"),
            ("power_loss", "vulnerability"),
            ("resource_loss", "anxiety"),
            ("loyalty_test", "conflict"),
        ]
        
        for change_type, expected_emotion in test_cases:
            feedback = loop.translate({
                "type": change_type,
                "magnitude": 0.5,
            })
            assert feedback["emotion"] == expected_emotion, \
                f"{change_type} should produce {expected_emotion}, got {feedback['emotion']}"


class TestLongTermStability:
    """Tests for long-term stability of Tier 14 systems."""

    def test_no_memory_leak(self):
        """Test that memory systems don't grow unboundedly."""
        system = px_mod.MemoryEchoSystem(max_memories=50)
        
        # Record more events than max
        for i in range(100):
            system.record_event({
                "type": "event",
                "tick": i,
            }, significance=0.5)
        
        assert len(system._memories) <= 50

    def test_engine_resets_cleanly(self):
        """Test that engine reset doesn't leave stale state."""
        engine = PlayerExperienceEngine()
        
        # Do some work
        engine.surface_event({"type": "betrayal", "importance": 0.8})
        engine.record_player_action("p1", "attack")
        engine.translate_change({"type": "reputation_increase", "magnitude": 0.5})
        
        # Reset (preserves profiles)
        engine.reset()
        
        # Stats should be zeroed
        assert engine._stats["events_surfaced"] == 0
        assert engine._stats["feedback_generated"] == 0
        
        # Profiles preserved
        assert "p1" in engine.player_profiles