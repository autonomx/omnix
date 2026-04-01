"""TIER 5 Experience Orchestration Tests.

Tests for the three TIER 5 systems:
1. AI Director (Tension Engine)
2. Dialogue Engine (Belief-Driven Dialogue)
3. Pacing Controller (Narrative Length Control)

Plus integration tests verifying they work together with PlayerLoop.
"""

from __future__ import annotations

import pytest
import sys
import os
from unittest.mock import MagicMock

# Add src/app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'app'))

from rpg.narrative.ai_director import AIDirector
from rpg.narrative.dialogue_engine import DialogueEngine
from rpg.narrative.pacing_controller import PacingController
from rpg.narrative.narrative_event import NarrativeEvent
from rpg.narrative.narrative_generator import NarrativeGenerator
from rpg.core.player_loop import PlayerLoop


class TestAIDirector:
    """Unit tests for AI Director (Tension Engine)."""

    def test_initial_state(self):
        director = AIDirector()
        assert director.tick == 0
        assert director.tension == 0.0

    def test_update_increases_tick(self):
        director = AIDirector()
        director.update()
        assert director.tick == 1
        # Tension remains 0.0 when no events provided (no source of tension)
        assert director.tension == 0.0

    def test_tension_rises_with_events(self):
        """Test that tension increases with dramatic events."""
        director = AIDirector()
        
        # Provide high emotional weight events
        events = [
            NarrativeEvent(id="1", type="combat", description="Fight!", 
                         emotional_weight=0.9),
            NarrativeEvent(id="2", type="death", description="Fall", 
                         emotional_weight=1.0),
        ]
        director.update(events)
        
        assert director.tick == 1
        assert director.tension > 0.0  # Events should increase tension
        
        # Multiple rounds of high-tension events should build tension
        for _ in range(5):
            director.update(events)
        
        assert director.tension > 0.1  # Should accumulate
    
    def test_tension_decays_without_events(self):
        """Test that tension naturally decays during calm periods."""
        director = AIDirector()
        
        # Build up tension
        events = [
            NarrativeEvent(id="1", type="combat", description="Fight!", 
                         emotional_weight=0.9),
        ]
        for _ in range(5):
            director.update(events)
        
        high_tension = director.tension
        assert high_tension > 0.0
        
        # Now decay with no events
        for _ in range(10):
            director.update()  # No events
        
        assert director.tension < high_tension  # Should have decayed
    
    def test_tension_history_tracking(self):
        """Test that tension history is properly tracked."""
        director = AIDirector()
        
        events = [
            NarrativeEvent(id="1", type="combat", description="Fight!", 
                         emotional_weight=0.5),
        ]
        
        for _ in range(5):
            director.update(events)
        
        history = director.get_tension_history()
        assert len(history) > 0
        assert all(0.0 <= t <= 1.0 for t in history)

    def test_filter_events_high_tension(self):
        director = AIDirector()
        director.tension = 0.9  # High tension
        
        events = [
            NarrativeEvent(id="1", type="combat", description="Fight!", 
                         emotional_weight=0.8, importance=0.7),
            NarrativeEvent(id="2", type="speak", description="Hello", 
                         emotional_weight=0.1, importance=0.3),
            NarrativeEvent(id="3", type="death", description="Death", 
                         emotional_weight=0.9, importance=0.9),
        ]
        
        filtered = director.filter_events(events)
        # Should prioritize high emotional weight events
        assert len(filtered) <= 3
        assert any(e.type in ("combat", "death") for e in filtered)

    def test_filter_events_low_tension(self):
        director = AIDirector()
        director.tension = 0.1  # Low tension
        
        events = [
            NarrativeEvent(id="1", type="combat", description="Fight!", 
                         emotional_weight=0.8, importance=0.7),
            NarrativeEvent(id="2", type="speak", description="Hello", 
                         emotional_weight=0.1, importance=0.3),
            NarrativeEvent(id="3", type="heal", description="Healing", 
                         emotional_weight=0.2, importance=0.4),
        ]
        
        filtered = director.filter_events(events)
        # Should return events including calm ones
        assert len(filtered) > 0
        assert len(filtered) <= 4

    def test_filter_events_empty(self):
        director = AIDirector()
        assert director.filter_events([]) == []

    def test_set_tension(self):
        director = AIDirector()
        director.set_tension(0.8)
        assert director.tension == 0.8

    def test_set_tension_clamped(self):
        director = AIDirector()
        director.set_tension(1.5)
        assert director.tension == 1.0
        
        director.set_tension(-0.5)
        assert director.tension == 0.0

    def test_reset(self):
        director = AIDirector()
        director.update()
        director.update()
        director.reset()
        assert director.tick == 0
        assert director.tension == 0.0


class TestDialogueEngine:
    """Unit tests for Dialogue Engine (Belief-Driven Dialogue)."""

    def test_generate_dialogue_no_memory(self):
        engine = DialogueEngine(memory=None)
        line = engine.generate_dialogue("guard", "player")
        assert len(line) > 0
        assert "guard" in line

    def test_generate_dialogue_self(self):
        engine = DialogueEngine(memory=None)
        line = engine.generate_dialogue("npc")
        assert len(line) > 0
        assert "npc" in line

    def test_different_speakers_different_dialogue(self):
        engine = DialogueEngine(memory=None)
        line1 = engine.generate_dialogue("guard", "player")
        line2 = engine.generate_dialogue("merchant", "player")
        assert line1 != line2  # Different speakers = different lines

    def test_hostile_tone_from_beliefs(self):
        mock_memory = MagicMock()
        mock_memory.retrieve.return_value = [
            (0.8, {"type": "relationship", "value": -0.6, "reason": "harmed"})
        ]
        engine = DialogueEngine(memory=mock_memory)
        line = engine.generate_dialogue("victim", "attacker")
        assert len(line) > 0

    def test_friendly_tone_from_beliefs(self):
        mock_memory = MagicMock()
        mock_memory.retrieve.return_value = [
            (0.8, {"type": "relationship", "value": 0.6, "reason": "helped"})
        ]
        engine = DialogueEngine(memory=mock_memory)
        line = engine.generate_dialogue("friend", "ally")
        assert len(line) > 0
        assert "friend" in line.lower() or "ally" in line.lower()

    def test_belief_system_integration(self):
        mock_bs = MagicMock()
        mock_bs.get.return_value = ["player"]  # Hostile targets
        mock_memory = MagicMock()
        mock_memory.belief_system = mock_bs
        
        engine = DialogueEngine(memory=mock_memory)
        line = engine.generate_dialogue("npc", "player")
        assert len(line) > 0

    def test_no_beliefs_returns_neutral(self):
        mock_memory = MagicMock()
        mock_memory.retrieve.return_value = []  # No beliefs
        engine = DialogueEngine(memory=mock_memory)
        line = engine.generate_dialogue("npc", "stranger")
        assert len(line) > 0


class TestPacingController:
    """Unit tests for Pacing Controller (Narrative Length Control)."""

    def test_fast_pace_shortens_output(self):
        controller = PacingController()
        text = "The battle raged on as warriors clashed in the valley. "
        text += "Swords rang out in the darkness. Blood stained the ground. "
        text += "Many fell before the dawn. "
        text += "The survivors regroup and prepare for another day of fighting."
        
        result = controller.adjust(text, tension=0.9)
        assert len(result.split()) <= controller.fast_max + 2  # +2 for ellipsis

    def test_slow_pace_allows_longer_output(self):
        controller = PacingController()
        text = "The peaceful meadow stretched for miles under the gentle sun. "
        text += "Wildflowers danced in the warm breeze. "
        text += "Birds sang their melodic songs from the ancient trees. "
        text += "A crystal stream trickled over smooth stones. "
        text += "The air was sweet with the scent of blooming roses."
        
        result = controller.adjust(text, tension=0.1)
        # Should keep more words than fast pace
        fast_result = controller.adjust(text, tension=0.9)
        assert len(result.split()) >= len(fast_result.split())

    def test_medium_pace(self):
        controller = PacingController()
        text = " ".join(["Word"] * 200)
        result = controller.adjust(text, tension=0.5)
        assert len(result.split()) <= controller.medium_max + 2

    def test_empty_text(self):
        controller = PacingController()
        assert controller.adjust("", tension=0.5) == ""

    def test_compute_target_length(self):
        controller = PacingController()
        assert controller.compute_target_length(0.9) == controller.fast_max
        assert controller.compute_target_length(0.1) == controller.slow_max
        assert controller.compute_target_length(0.5) == controller.medium_max


class TestTier5Integration:
    """Integration tests for TIER 5 systems working together."""

    def test_tension_affects_output_length(self):
        """Test from rpg-design.txt: high tension = short, low tension = long."""
        pacing = PacingController()
        
        # Create text longer than fast_max (60) but within slow_max (150)
        pacing_text = "The battle rages on as swords clash and blood flies. " * 5
        # This should be ~50 words, which is > fast_max (60) after trimming
        
        fast = pacing.adjust(pacing_text, tension=0.9)
        slow = pacing.adjust(pacing_text, tension=0.1)
        
        # Fast should trim to ~60 words, slow keeps more
        assert len(fast.split()) <= pacing.fast_max + 2
        assert len(slow.split()) <= pacing.slow_max + 2
        # When text exceeds fast_max, slow returns more words
        assert len(slow) >= len(fast)

    def test_ai_director_filters_events_for_pacing(self):
        """Test that AI Director properly filters events by tension."""
        director = AIDirector()
        director.tension = 0.9
        
        events = [
            NarrativeEvent(id="1", type="combat", description="Fight", 
                         emotional_weight=0.9),
            NarrativeEvent(id="2", type="move", description="Walk", 
                         emotional_weight=0.1),
            NarrativeEvent(id="3", type="death", description="Fall", 
                         emotional_weight=0.8),
        ]
        
        filtered = director.filter_events(events)
        # High tension should favor dramatic events
        assert all(e.emotional_weight >= 0.6 or e.type in ("combat", "death") 
                   for e in filtered)

    def test_player_loop_with_tier5_systems(self):
        """Test PlayerLoop integrates TIER 5 systems correctly."""
        # Mock world
        world = MagicMock()
        world.world_tick.return_value = [
            {"type": "combat", "description": "Player fights", "actors": ["player"]},
            {"type": "speak", "description": "Guard speaks", "actors": ["guard"]},
        ]
        
        # Create TIER 5 systems
        ai_director = AIDirector()
        pacing = PacingController()
        
        loop = PlayerLoop(
            world=world,
            ai_director=ai_director,
            pacing_controller=pacing,
        )
        
        result = loop.step("I attack")
        
        assert "narration" in result
        assert len(result["narration"]) > 0
        # Narration should be adjusted by pacing controller
        assert len(result["narration"].split()) <= pacing.slow_max

    def test_full_pipeline_with_mock_events(self):
        """Test full pipeline: events → AI Director → pacing."""
        director = AIDirector()
        pacing = PacingController()
        generator = NarrativeGenerator()
        
        # Set high tension
        director.tension = 0.9
        
        events = [
            NarrativeEvent(id="1", type="combat", description="Battle", 
                         emotional_weight=0.9, importance=0.8),
            NarrativeEvent(id="2", type="death", description="Fall", 
                         emotional_weight=0.95, importance=0.9),
        ]
        
        # Filter events
        filtered = director.filter_events(events)
        
        # Generate narration
        narration = generator.generate(filtered, {"location": "field"})
        
        # Apply pacing
        paced = pacing.adjust(narration, director.tension)
        
        assert len(paced.split()) <= pacing.fast_max + 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])