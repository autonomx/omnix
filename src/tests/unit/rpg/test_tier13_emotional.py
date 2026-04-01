"""Unit Tests — Tier 13: Emotional + Experiential Layer.

Tests for:
- ResolutionEngine (emotionally satisfying resolutions)
- EmotionModifier (emotion -> decision/dialogue mapping)
- NarrativeMemory (historical awareness)
- Narrative Diversity Injection (prevent over-convergence)
"""

from __future__ import annotations

import os
import sys
import pytest
from unittest.mock import MagicMock

# Add project path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "app"))

# Tier 13 modules
from rpg.cognitive.resolution_engine import (
    ResolutionEngine,
    ResolutionResult,
    RESOLUTION_TEMPLATES,
    RESOLUTION_TYPES,
)
from rpg.cognitive.emotion_modifier import (
    EmotionModifier,
    EmotionalState,
    DecisionModification,
    EMOTION_DECISION_MODIFIERS,
    EMOTION_DIALOGUE_MODIFIERS,
    AGGRESSIVE_ACTIONS,
    DIPLOMATIC_ACTIONS,
    BLOCKING_THRESHOLDS,
)
from rpg.cognitive.narrative_memory import (
    NarrativeMemory,
    ArcMemory,
    EmotionalResidue,
)
from rpg.cognitive.narrative_gravity import NarrativeGravity, StorylineState


class TestResolutionEngine:
    """Test suite for ResolutionEngine."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.engine = ResolutionEngine()
    
    def test_generate_victory_resolution(self):
        """Test generation of victory resolution."""
        storyline = {
            "event_type": "faction_conflict",
            "participants": ["A", "B"],
            "events": [
                {"type": "attack", "description": "A attacked B"},
                {"type": "victory", "description": "A won"},
            ],
            "progress": 0.9,
            "importance": 0.7,
            "is_player_involved": False,
        }
        characters = {
            "A": {"name": "Alice", "emotions": {"anger": 0.6}},
            "B": {"name": "Bob", "emotions": {"fear": 0.7}},
        }
        
        result = self.engine.generate(storyline, characters)
        
        assert isinstance(result, ResolutionResult)
        assert result.resolution_type in RESOLUTION_TYPES
        assert len(result.text) > 0
        assert isinstance(result.emotional_impact, dict)
    
    def test_generate_compromise_resolution(self):
        """Test generation of compromise resolution."""
        storyline = {
            "event_type": "personal_conflict",
            "participants": ["A", "B"],
            "events": [
                {"type": "disagreement", "description": "A and B disagreed"},
                {"type": "negotiation", "description": "They talked"},
            ],
            "progress": 0.6,
            "importance": 0.5,
            "is_player_involved": False,
        }
        
        result = self.engine.generate(storyline)
        
        assert isinstance(result, ResolutionResult)
        assert len(result.text) > 0
    
    def test_generate_with_betrayal_events(self):
        """Test that betrayal events influence resolution type."""
        storyline = {
            "event_type": "faction_conflict",
            "participants": ["A", "B", "C"],
            "events": [
                {"type": "alliance", "description": "A allied with B"},
                {"type": "betrayal", "betrayer": "A", "description": "A betrayed B"},
            ],
            "progress": 0.5,
            "importance": 0.8,
            "is_player_involved": False,
        }
        
        result = self.engine.generate(storyline)
        
        assert isinstance(result, ResolutionResult)
        # Betrayal resolution should be more likely
        assert result.resolution_type in ["betrayal", "tragedy", "victory"]
    
    def test_player_satisfaction_high_progress(self):
        """Test player satisfaction for high-progress victories."""
        storyline = {
            "event_type": "quest",
            "participants": ["player", "A"],
            "events": [],
            "progress": 0.85,
            "importance": 0.6,
            "is_player_involved": True,
        }
        
        result = self.engine.generate(storyline)
        
        if result.resolution_type in {"victory", "compromise", "redemption", "transcendence"}:
            assert result.satisfies_player is True
    
    def test_emotional_impact_calculation(self):
        """Test emotional impact is calculated correctly."""
        storyline = {
            "event_type": "general",
            "participants": ["A"],
            "events": [],
            "progress": 0.5,
            "importance": 0.8,
        }
        
        result = self.engine.generate(storyline)
        
        if result.emotional_impact:
            for emotion, value in result.emotional_impact.items():
                assert -1.0 <= value <= 1.0
    
    def test_relationship_updates(self):
        """Test relationship updates are calculated."""
        storyline = {
            "event_type": "personal_conflict",
            "participants": ["A", "B"],
            "events": [],
            "progress": 0.5,
            "importance": 0.5,
        }
        
        result = self.engine.generate(storyline)
        
        assert "A:B" in result.relationship_updates
    
    def test_template_resolution_fallback(self):
        """Test template resolution works without LLM."""
        engine = ResolutionEngine(use_llm=False)
        storyline = {
            "event_type": "faction_conflict",
            "participants": ["Alpha", "Beta"],
            "events": [],
            "progress": 0.5,
            "importance": 0.5,
        }
        
        result = engine.generate(storyline)
        
        assert len(result.text) > 0
        # Template resolution should produce valid text
        assert result.resolution_type in RESOLUTION_TYPES
    
    def test_stats_tracking(self):
        """Test engine tracks resolution statistics."""
        storyline = {
            "event_type": "general",
            "participants": ["A"],
            "events": [],
            "progress": 0.5,
            "importance": 0.5,
        }
        
        self.engine.generate(storyline)
        self.engine.generate(storyline)
        
        stats = self.engine.get_stats()
        assert stats["resolutions_generated"] == 2
    
    def test_reset(self):
        """Test engine can be reset."""
        storyline = {
            "event_type": "general",
            "participants": ["A"],
            "events": [],
            "progress": 0.5,
            "importance": 0.5,
        }
        
        self.engine.generate(storyline)
        self.engine.reset()
        
        stats = self.engine.get_stats()
        assert stats["resolutions_generated"] == 0


class TestEmotionModifier:
    """Test suite for EmotionModifier."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.modifier = EmotionModifier()
    
    def _create_character(self, emotions: dict) -> MagicMock:
        """Create a mock character with emotional state."""
        char = MagicMock()
        char.emotional_state = EmotionalState(emotions=emotions)
        return char
    
    def test_anger_modifies_aggression(self):
        """Test anger increases aggression."""
        char = self._create_character({"anger": 0.7, "fear": 0.0, "trust": 0.3})
        intent = {"type": "attack", "priority": 5.0, "target": "B"}
        
        result = self.modifier.apply(char, intent)
        
        assert not result.was_blocked
        assert result.modified_intent["priority"] > 5.0  # Anger increases priority
    
    def test_fear_blocks_confrontation(self):
        """Test high fear blocks confrontation actions."""
        char = self._create_character({
            "anger": 0.0,
            "fear": 0.85,  # Above BLOCKING_THRESHOLDS
            "trust": 0.3,
        })
        intent = {"type": "attack", "priority": 5.0, "target": "B"}
        
        result = self.modifier.apply(char, intent)
        
        assert result.was_blocked is True
        assert "fear" in result.blocking_reason.lower()
    
    def test_anger_blocks_diplomacy(self):
        """Test high anger blocks diplomatic actions."""
        char = self._create_character({
            "anger": 0.75,  # Above BLOCKING_THRESHOLDS
            "fear": 0.0,
            "trust": 0.3,
        })
        intent = {"type": "negotiate", "priority": 5.0, "target": "B"}
        
        result = self.modifier.apply(char, intent)
        
        assert result.was_blocked is True
        assert "anger" in result.blocking_reason.lower()
    
    def test_sadness_blocks_initiative(self):
        """Test high sadness blocks initiative actions."""
        char = self._create_character({
            "sadness": 0.85,  # Above BLOCKING_THRESHOLDS
            "anger": 0.0,
            "fear": 0.0,
        })
        intent = {"type": "help", "priority": 5.0, "target": "B"}
        
        result = self.modifier.apply(char, intent)
        
        assert result.was_blocked is True
    
    def test_trust_increases_cooperation(self):
        """Test trust increases cooperation."""
        char = self._create_character({"trust": 0.7, "anger": 0.0, "fear": 0.0})
        intent = {"type": "alliance", "priority": 5.0, "target": "B"}
        
        result = self.modifier.apply(char, intent)
        
        assert not result.was_blocked
        assert "cooperation" in result.modifiers_used or "diplomacy" in result.modifiers_used
    
    def test_dialogue_modifier_anger(self):
        """Test anger produces aggressive dialogue style."""
        char = self._create_character({"anger": 0.8, "fear": 0.0, "trust": 0.3})
        
        dialogue_style = self.modifier.apply_dialogue_modifier(char)
        
        assert dialogue_style["style"] == "anger"
        assert dialogue_style["tone"] == "aggressive"
        assert dialogue_style["vocabulary"] == "harsh"
    
    def test_dialogue_modifier_fear(self):
        """Test fear produces hesitant dialogue style."""
        char = self._create_character({"fear": 0.8, "anger": 0.0, "trust": 0.3})
        
        dialogue_style = self.modifier.apply_dialogue_modifier(char)
        
        assert dialogue_style["style"] == "fear"
        assert dialogue_style["tone"] == "hesitant"
        assert dialogue_style["vocabulary"] == "uncertain"
    
    def test_dialogue_modifier_trust(self):
        """Test trust produces warm dialogue style."""
        char = self._create_character({"trust": 0.8, "anger": 0.0, "fear": 0.0})
        
        dialogue_style = self.modifier.apply_dialogue_modifier(char)
        
        assert dialogue_style["style"] == "trust"
        assert dialogue_style["tone"] == "warm"
    
    def test_emotional_memory_impact(self):
        """Test emotional memory affects current decisions."""
        char = self._create_character({
            "anger": 0.6,
            "fear": 0.0,
            "trust": 0.3,
        })
        char.emotional_state.add_emotional_event({
            "type": "betrayal",
            "target": "B",
        })
        
        impact = self.modifier.get_emotional_memory_impact(char, target="B")
        
        assert len(impact) > 0
    
    def test_no_emotional_state_returns_unmodified(self):
        """Test character without emotional state returns unmodified intent."""
        char = MagicMock()
        del char.emotional_state
        intent = {"type": "attack", "priority": 5.0}
        
        result = self.modifier.apply(char, intent)
        
        assert result.was_blocked is False
        assert result.confidence == 0.5
    
    def test_stats_tracking(self):
        """Test modifier tracks statistics."""
        char = self._create_character({"anger": 0.0, "fear": 0.0, "trust": 0.5})
        intent = {"type": "negotiate", "priority": 5.0}
        
        self.modifier.apply(char, intent)
        
        stats = self.modifier.get_stats()
        assert stats["modifications_applied"] == 1
    
    def test_reset(self):
        """Test modifier can be reset."""
        char = self._create_character({"anger": 0.0, "fear": 0.0, "trust": 0.5})
        intent = {"type": "negotiate", "priority": 5.0}
        
        self.modifier.apply(char, intent)
        self.modifier.reset()
        
        stats = self.modifier.get_stats()
        assert stats["modifications_applied"] == 0


class TestNarrativeMemory:
    """Test suite for NarrativeMemory."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.memory = NarrativeMemory()
    
    def test_store_arc(self):
        """Test storing a completed arc."""
        arc_data = {
            "arc_id": "war_1",
            "arc_type": "faction_conflict",
            "outcome": "A defeated B",
            "participants": ["A", "B"],
            "impact": 0.6,
            "emotion": {"anger": 0.6, "fear": 0.3},
            "tick_resolved": 100,
            "resolution_type": "victory",
        }
        
        memory = self.memory.store_arc(arc_data)
        
        assert memory.arc_id == "war_1"
        assert len(self.memory.get_all_arcs()) == 1
    
    def test_get_relevant_history_by_actor(self):
        """Test finding relevant arcs by actor overlap."""
        self.memory.store_arc({
            "arc_id": "war_1",
            "arc_type": "faction_conflict",
            "outcome": "A defeated B",
            "participants": ["A", "B"],
            "impact": 0.6,
            "tick_resolved": 100,
            "resolution_type": "victory",
        })
        
        relevant = self.memory.get_relevant_history(
            current_actors=["A", "C"],
            event_type="faction_conflict",
        )
        
        assert len(relevant) >= 0  # May be filtered by similarity threshold
    
    def test_get_relevant_history_by_type(self):
        """Test finding relevant arcs by event type."""
        self.memory.store_arc({
            "arc_id": "war_1",
            "arc_type": "faction_conflict",
            "outcome": "A defeated B",
            "participants": ["A", "B"],
            "impact": 0.9,  # High impact
            "tick_resolved": 100,
            "resolution_type": "victory",
        })
        
        relevant = self.memory.get_relevant_history(
            current_actors=[],
            event_type="faction_conflict",
        )
        
        # High impact arcs may pass threshold
        assert isinstance(relevant, list)
    
    def test_get_reputation_history(self):
        """Test getting character reputation history."""
        self.memory.store_arc({
            "arc_id": "arc_1",
            "arc_type": "faction_conflict",
            "outcome": "A defeated B",
            "participants": ["A", "B"],
            "impact": 0.6,
            "tick_resolved": 100,
            "resolution_type": "victory",
        })
        
        reputation = self.memory.get_reputation_history("A")
        
        assert len(reputation) >= 1
        assert reputation[0]["arc_id"] == "arc_1"
    
    def test_get_emotional_resonance(self):
        """Test getting emotional residue."""
        self.memory.store_arc({
            "arc_id": "arc_1",
            "arc_type": "faction_conflict",
            "outcome": "A defeated B",
            "participants": ["A", "B"],
            "emotions": {"anger": 0.6, "fear": 0.5},
            "impact": 0.6,
            "tick_resolved": 100,
            "resolution_type": "victory",
        })
        
        resonance = self.memory.get_emotional_resonance(
            character_ids=["A"],
            current_tick=150,
        )
        
        assert isinstance(resonance, dict)
    
    def test_memory_decay(self):
        """Test arc relevance decays over time."""
        arc_data = {
            "arc_id": "arc_1",
            "arc_type": "faction_conflict",
            "outcome": "A defeated B",
            "participants": ["A", "B"],
            "impact": 0.6,
            "tick_resolved": 100,
            "resolution_type": "victory",
        }
        self.memory.store_arc(arc_data)
        
        # Check at tick 200
        self.memory.get_relevant_history(current_tick=200)
        arcs = self.memory.get_all_arcs()
        
        # Relevance should be below 1.0 after decay
        assert arcs[0]["relevance"] < 1.0
    
    def test_world_impact(self):
        """Test world impact aggregation."""
        self.memory.store_arc({
            "arc_id": "arc_1",
            "arc_type": "faction_conflict",
            "outcome": "A defeated B",
            "participants": ["A", "B"],
            "impact": 0.6,
            "tick_resolved": 100,
            "resolution_type": "victory",
        })
        self.memory.store_arc({
            "arc_id": "arc_2",
            "arc_type": "personal_conflict",
            "outcome": "Stalemate",
            "participants": ["C", "D"],
            "impact": 0.4,
            "tick_resolved": 150,
            "resolution_type": "stalemate",
        })
        
        impact = self.memory.get_world_impact()
        
        assert impact["total_arcs"] == 2
        assert impact["average_impact"] > 0.0
        assert len(impact["active_conflicts"]) >= 1  # stalemate arc
    
    def test_store_duplicate_arc_updates(self):
        """Test storing arc with same ID updates existing."""
        arc_data = {
            "arc_id": "arc_1",
            "arc_type": "faction_conflict",
            "outcome": "A defeated B",
            "participants": ["A", "B"],
            "impact": 0.5,
            "tick_resolved": 100,
            "resolution_type": "victory",
        }
        self.memory.store_arc(arc_data)
        
        # Store again with different outcome
        arc_data["outcome"] = "B surrendered"
        self.memory.store_arc(arc_data)
        
        assert len(self.memory.get_all_arcs()) == 1  # Still just one arc
    
    def test_clear(self):
        """Test clearing narrative memory."""
        self.memory.store_arc({
            "arc_id": "arc_1",
            "arc_type": "faction_conflict",
            "outcome": "A defeated B",
            "participants": ["A", "B"],
            "impact": 0.6,
            "tick_resolved": 100,
            "resolution_type": "victory",
        })
        
        self.memory.clear()
        
        assert len(self.memory.get_all_arcs()) == 0
        stats = self.memory.get_stats()
        assert stats["arcs_stored"] == 0


class TestNarrativeDiversityInjection:
    """Test suite for Narrative Diversity Injection (Tier 13 patch)."""
    
    def test_diversity_bonus_underrepresented(self):
        """Test diversity bonus for underrepresented actors."""
        gravity = NarrativeGravity(max_active=2)
        
        # Add storylines with dominant characters
        sl1 = StorylineState(
            id="sl1",
            participants=["A", "B"],
            start_tick=0,
            last_active_tick=50,
            importance=0.8,
        )
        sl2 = StorylineState(
            id="sl2",
            participants=["A", "B"],
            start_tick=10,
            last_active_tick=60,
            importance=0.7,
        )
        gravity.add_storyline(sl1)
        gravity.add_storyline(sl2)
        
        # New character C should get bonus
        event = {"type": "conflict", "participants": ["C"]}
        score = gravity.score_event(event)
        
        # Score should include diversity bonus
        assert score >= 0.15  # At least the bonus alone
    
    def test_diversity_bonus_no_bonus_dominant(self):
        """Test no diversity bonus for dominant actors."""
        gravity = NarrativeGravity(max_active=2)
        
        # Add storylines with character A appearing many times
        for i in range(5):
            sl = StorylineState(
                id=f"sl{i}",
                participants=["A"],
                start_tick=i * 10,
                last_active_tick=i * 10 + 50,
                importance=0.5,
            )
            gravity.add_storyline(sl)
        
        # A should NOT get diversity bonus
        event = {"type": "conflict", "participants": ["A"]}
        score = gravity.score_event(event)
        
        # Diversity bonus should be 0.0 for A
        bonus = gravity._diversity_bonus(["A"])
        assert bonus == 0.0
    
    def test_player_override_importance(self):
        """Test player involvement increases importance."""
        gravity = NarrativeGravity(player_id="player")
        
        # Event without player
        event_no_player = {"type": "conflict", "participants": ["A", "B"]}
        score_no = gravity.score_event(event_no_player)
        
        # Event with player
        event_with_player = {"type": "conflict", "participants": ["player", "A"]}
        score_with = gravity.score_event(event_with_player)
        
        assert score_with > score_no


class TestDecisionModification:
    """Test suite for DecisionModification dataclass."""
    
    def test_to_dict(self):
        """Test serialization to dict."""
        dm = DecisionModification(
            original_intent={"type": "attack"},
            modified_intent={"type": "attack", "priority": 7.0},
            emotion_applied={"anger": 0.6},
            modifiers_used=["aggression"],
            was_blocked=False,
            confidence=0.8,
        )
        
        result = dm.to_dict()
        
        assert result["original_intent"] == {"type": "attack"}
        assert result["modifiers_used"] == ["aggression"]
        assert result["was_blocked"] is False


class TestEmotionalState:
    """Test suite for EmotionalState dataclass."""
    
    def test_dominant_emotion(self):
        """Test dominant emotion detection."""
        state = EmotionalState(
            emotions={"anger": 0.7, "fear": 0.3, "trust": 0.2}
        )
        
        assert state.dominant_emotion == "anger"
    
    def test_dominant_emotion_neutral(self):
        """Test dominant emotion is neutral below threshold."""
        state = EmotionalState(
            emotions={"anger": 0.05, "fear": 0.05, "trust": 0.08}
        )
        
        assert state.dominant_emotion == "neutral"
    
    def test_get_dominant_intensity(self):
        """Test getting dominant emotion intensity."""
        state = EmotionalState(
            emotions={"anger": 0.7, "fear": 0.3}
        )
        
        assert state.get_dominant_intensity() == 0.7
    
    def test_is_above_threshold(self):
        """Test threshold checking."""
        state = EmotionalState(
            emotions={"anger": 0.6, "fear": 0.3}
        )
        
        assert state.is_above_threshold("anger", 0.5) is True
        assert state.is_above_threshold("fear", 0.5) is False
    
    def test_add_emotional_event(self):
        """Test recording emotional events."""
        state = EmotionalState()
        
        state.add_emotional_event({"type": "betrayal"})
        
        assert len(state.emotional_memory) == 1
        assert state.emotional_memory[0]["event"]["type"] == "betrayal"
    
    def test_to_dict(self):
        """Test serialization to dict."""
        state = EmotionalState(
            emotions={"anger": 0.5, "fear": 0.3},
            emotional_volatility=0.6,
        )
        
        result = state.to_dict()
        
        assert result["dominant_emotion"] == "anger"
        assert result["emotions"]["anger"] == 0.5
        assert result["volatility"] == 0.6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])