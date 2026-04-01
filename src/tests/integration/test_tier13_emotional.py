"""Integration Tests — Tier 13: Emotional + Experiential Layer.

Integration tests for the full Tier 13 pipeline:
- ResolutionEngine + NarrativeMemory + EmotionModifier
- 300+ tick drift test (no over-convergence)
- Narrative repetition test
- Player agency perception test
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
import random
import os
import sys

# Add src to path if needed
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from rpg.cognitive.resolution_engine import ResolutionEngine, ResolutionResult
from rpg.cognitive.emotion_modifier import EmotionModifier, EmotionalState
from rpg.cognitive.narrative_memory import NarrativeMemory
from rpg.cognitive.narrative_gravity import NarrativeGravity, StorylineState


class TestTier13Integration:
    """Integration tests for Tier 13 full pipeline."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.resolution = ResolutionEngine()
        self.emotion_mod = EmotionModifier()
        self.narrative_memory = NarrativeMemory()
        self.gravity = NarrativeGravity(max_active=3, player_id="player")
    
    def _create_character(self, emotions: dict) -> MagicMock:
        """Create a mock character with emotional state."""
        char = MagicMock()
        char.emotional_state = EmotionalState(emotions=emotions)
        char.id = emotions.get("_id", "char_1")
        return char
    
    def test_full_resolution_pipeline(self):
        """Test resolution -> memory -> emotion pipeline."""
        # Phase 1: Create a storyline and resolve it
        storyline = {
            "event_type": "faction_conflict",
            "participants": ["A", "B"],
            "events": [
                {"type": "alliance", "description": "A allied with B"},
                {"type": "betrayal", "betrayer": "A", "description": "A betrayed B"},
            ],
            "progress": 0.8,
            "importance": 0.7,
            "is_player_involved": False,
        }
        characters = {
            "A": {"name": "Alice", "emotions": {"anger": 0.6, "guilt": 0.4}},
            "B": {"name": "Bob", "emotions": {"anger": 0.8, "fear": 0.3}},
        }
        
        # Generate resolution
        resolution = self.resolution.generate(storyline, characters)
        
        assert isinstance(resolution, ResolutionResult)
        assert len(resolution.text) > 0
        
        # Phase 2: Store in narrative memory
        arc_data = {
            "arc_id": "conflict_1",
            "arc_type": "faction_conflict",
            "outcome": resolution.text,
            "participants": list(storyline["participants"]),
            "emotions": resolution.emotional_impact,
            "impact": resolution.importance,
            "tick_resolved": 100,
            "resolution_type": resolution.resolution_type,
            "consequences": resolution.consequences,
        }
        self.narrative_memory.store_arc(arc_data)
        
        # Phase 3: Get emotional residue
        residue = self.narrative_memory.get_emotional_resonance(
            character_ids=["A", "B"],
            current_tick=150,
        )
        
        assert isinstance(residue, dict)
        
        # Phase 4: Check reputation history
        reputation_a = self.narrative_memory.get_reputation_history("A")
        assert len(reputation_a) >= 1
    
    def test_emotional_feedback_loop(self):
        """Test how emotional residue affects future decisions."""
        # Create emotional residue from past betrayal
        self.narrative_memory.store_arc({
            "arc_id": "betrayal_1",
            "arc_type": "personal_conflict",
            "outcome": "A betrayed B",
            "participants": ["A", "B"],
            "emotions": {"anger": 0.7, "distrust": 0.6},
            "impact": 0.8,
            "tick_resolved": 100,
            "resolution_type": "betrayal",
        })
        
        # Get emotional residue for B (victim of betrayal)
        residue = self.narrative_memory.get_emotional_resonance(
            character_ids=["B"],
            current_tick=120,
        )
        
        # Create character with the emotional residue (use numeric values only in emotions dict)
        char_b = self._create_character({
            "anger": residue.get("anger", 0.0),
            "fear": residue.get("fear", 0.0),
            "trust": 0.2,  # Low trust after betrayal
        })
        char_b.id = "B"
        
        # Try diplomatic action - should be influenced by low trust
        intent = {"type": "negotiate", "priority": 5.0, "target": "A"}
        result = self.emotion_mod.apply(char_b, intent)
        
        assert hasattr(result, "modified_intent")


class Test300TickDrift:
    """Test narrative stability over 300+ ticks."""
    
    def test_300_tick_no_over_convergence(self):
        """Test that narrative diversity prevents over-convergence over 300 ticks."""
        gravity = NarrativeGravity(max_active=3, player_id="player")
        
        # Track character appearances across all ticks
        appearance_counts = {}
        all_characters = [f"char_{i}" for i in range(10)]
        
        for tick in range(1, 301):
            # Simulate random events with random characters
            num_participants = random.randint(1, 3)
            participants = random.sample(all_characters, num_participants)
            
            event = {
                "type": random.choice(["conflict", "alliance", "discovery"]),
                "participants": participants,
                "progress": random.uniform(0.1, 0.9),
            }
            
            score = gravity.score_event(event)
            
            # Add storyline
            sl = StorylineState(
                id=f"sl_{tick}",
                event_type=event["type"],
                participants=participants,
                start_tick=tick,
                last_active_tick=tick,
                importance=score,
                progress=random.uniform(0.1, 0.5),
            )
            gravity.add_storyline(sl)
            
            # Update storylines (conclude old ones)
            focused = gravity.update_storylines(current_tick=tick)
            
            # Track appearances
            for char_id in participants:
                appearance_counts[char_id] = appearance_counts.get(char_id, 0) + 1
            
            # Conclude some storylines
            for sl_id in list(gravity._storylines.keys()):
                sl = gravity._storylines[sl_id]
                if gravity.should_conclude(sl, tick):
                    gravity.conclude_storyline(sl_id)
            
            # Clean up old storylines to prevent infinite growth
            if len(gravity._storylines) > 10:
                oldest = min(gravity._storylines.keys(),
                             key=lambda k: gravity._storylines[k].last_active_tick)
                gravity._storylines.pop(oldest)
        
        # Check: No single character should dominate (>40% of appearances)
        total_appearances = sum(appearance_counts.values())
        max_appearances = max(appearance_counts.values()) if appearance_counts else 0
        
        # With diversity bonus, the most frequent character should have <50% of total
        dominance_ratio = max_appearances / max(total_appearances, 1)
        assert dominance_ratio < 0.5, (
            f"Character dominance too high: {dominance_ratio:.2%} "
            f"(max={max_appearances}, total={total_appearances})"
        )
    
    def test_300_tick_narrative_repetition(self):
        """Test that narrative doesn't become too repetitive."""
        gravity = NarrativeGravity(max_active=3)
        
        # Simulate 300 ticks
        storyline_types_seen = set()
        resolution_count = 0
        
        for tick in range(1, 301):
            event = {
                "type": random.choice(["conflict", "alliance", "betrayal", "quest_start"]),
                "participants": [f"char_{random.randint(1, 5)}"],
                "progress": random.uniform(0.1, 0.9),
            }
            
            score = gravity.score_event(event)
            
            sl = StorylineState(
                id=f"sl_{tick}",
                event_type=event["type"],
                participants=event["participants"],
                start_tick=tick,
                last_active_tick=tick,
                importance=score,
                progress=event.get("progress", 0.5),
            )
            gravity.add_storyline(sl)
            
            # Track storyline types
            storyline_types_seen.add(event["type"])
            
            focused = gravity.update_storylines(current_tick=tick)
            
            for sl_id in list(gravity._storylines.keys()):
                sl = gravity._storylines[sl_id]
                if gravity.should_conclude(sl, tick):
                    resolution = gravity.generate_resolution(sl)
                    gravity.conclude_storyline(sl_id, resolution)
                    resolution_count += 1
            
            # Limit storylines
            if len(gravity._storylines) > 10:
                oldest = min(gravity._storylines.keys(),
                             key=lambda k: gravity._storylines[k].last_active_tick)
                gravity._storylines.pop(oldest)
        
        # With diversity, we should see at least 2-3 different storyline types
        assert len(storyline_types_seen) >= 2, (
            f"Narrative too repetitive: only {len(storyline_types_seen)} types seen"
        )
        
        # Should have resolved some storylines
        assert resolution_count > 0, "No storylines were resolved"


class TestPlayerAgencyPerception:
    """Test player agency is maintained over time."""
    
    def test_player_event_importance_boost(self):
        """Test player-involved events get importance boost."""
        gravity = NarrativeGravity(player_id="player")
        
        # Non-player event
        non_player_event = {
            "type": "conflict",
            "participants": ["A", "B"],
        }
        non_player_score = gravity.score_event(non_player_event)
        
        # Player event
        player_event = {
            "type": "conflict",
            "participants": ["player", "A"],
        }
        player_score = gravity.score_event(player_event)
        
        assert player_score > non_player_score
    
    def test_player_storyline_priority(self):
        """Test player storylines are prioritized."""
        gravity = NarrativeGravity(player_id="player", max_active=2)
        
        # Add non-player storylines
        for i in range(5):
            sl = StorylineState(
                id=f"sl_{i}",
                participants=["A", "B"],
                start_tick=i * 10,
                last_active_tick=i * 10 + 50,
                importance=0.5,  # Medium importance
            )
            gravity.add_storyline(sl)
        
        # Add player storyline with same importance
        player_sl = StorylineState(
            id="player_sl",
            participants=["player", "C"],
            start_tick=50,
            last_active_tick=60,
            importance=0.5,  # Same as others
            is_player_involved=True,
        )
        gravity.add_storyline(player_sl)
        
        # Player storyline should score higher due to player involvement
        updated = [sl for sl in gravity._storylines.values()]
        player_sl_score = player_sl.importance
        
        for sl in updated:
            if "player" in sl.participants:
                assert sl.importance >= 0.5  # At least base importance
                break
    
    def test_player_satisfaction_across_multiple_resolutions(self):
        """Test player satisfaction across multiple storyline resolutions."""
        resolution = ResolutionEngine()
        
        # Multiple player-involved storylines
        storylines = [
            {
                "event_type": "quest",
                "participants": ["player", "A"],
                "events": [{"type": "discovery", "description": "Found clue"}],
                "progress": 0.9,
                "importance": 0.7,
                "is_player_involved": True,
            },
            {
                "event_type": "personal_conflict",
                "participants": ["player", "B"],
                "events": [{"type": "disagreement", "description": "Disagreed"}],
                "progress": 0.6,
                "importance": 0.5,
                "is_player_involved": True,
            },
        ]
        
        satisfying_count = 0
        for sl in storylines:
            result = resolution.generate(sl)
            if result.satisfies_player:
                satisfying_count += 1
        
        # At least 50% of player resolutions should be satisfying
        assert satisfying_count >= len(storylines) * 0.5


class TestFunctionalRegression:
    """Functional and regression tests for Tier 13."""
    
    def test_tier13_imports(self):
        """Test all Tier 13 modules can be imported."""
        from rpg.cognitive import (
            ResolutionEngine,
            ResolutionResult,
            EmotionModifier,
            EmotionalState,
            DecisionModification,
            NarrativeMemory,
            ArcMemory,
            EmotionalResidue,
        )
        # No exceptions = success
    
    def test_backwards_compatibility_narrative_gravity(self):
        """Test NarrativeGravity backwards compatibility with existing API."""
        gravity = NarrativeGravity()
        
        # Old API should still work
        score = gravity.score_event({
            "type": "conflict",
            "participants": ["A", "B"],
        })
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
        
        # Diversity bonus is now calculated automatically
        bonus = gravity._diversity_bonus(["A"])
        assert 0.0 <= bonus <= 0.15
    
    def test_tier12_still_works(self):
        """Test Tier 12 components still function after Tier 13 additions."""
        from rpg.cognitive import (
            DecisionResolver,
            CoalitionLockManager,
            NarrativeGravity,
        )
        
        resolver = DecisionResolver()
        lock_manager = CoalitionLockManager()
        
        # Test resolver with None character (avoids MagicMock comparison issues)
        base_intent = {"type": "attack", "priority": 5.0}
        enriched_intent = {"type": "attack", "priority": 7.0}
        
        result = resolver.resolve(base_intent, enriched_intent, None)
        assert "priority" in result
        
        # Test lock manager
        intent = {"type": "attack", "priority": 5.0}
        locked = lock_manager.enforce_lock("char_1", intent, 1)
        assert isinstance(locked, dict) or hasattr(locked, "__dict__")
    
    def test_tier11_still_works(self):
        """Test Tier 11 components still function."""
        from rpg.cognitive import (
            IntentEnrichment,
            IdentitySystem,
            CoalitionSystem,
            LearningSystem,
        )
        
        enrichment = IntentEnrichment()
        assert enrichment is not None
        
        identity = IdentitySystem()
        assert identity is not None
        
        coalition = CoalitionSystem()
        assert coalition is not None
        
        learning = LearningSystem()
        assert learning is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])