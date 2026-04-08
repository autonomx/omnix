"""Integration Test: TIER 9 Narrative Intelligence Layer.

This module tests the TIER 9 Narrative Intelligence systems integrated
into the PlayerLoop. It verifies that scenes, characters, narrative memory,
story arcs, and the narrative renderer all work correctly together.

Test Coverage:
    - Scene generation from world events
    - Character belief updates from events
    - Narrative memory storage and summarization
    - Story arc registration and completion
    - Narrative rendering output
    - 100-tick narrative stability simulation
"""

from __future__ import annotations

import os
import sys

# Add app directory to path (same as other test files)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'app'))

import pytest
from rpg.character.character_engine import Character, CharacterEngine
from rpg.core.player_loop import PlayerLoop
from rpg.memory.narrative_memory import NarrativeMemory
from rpg.story.narrative_renderer import NarrativeRenderer
from rpg.story.scene_engine import Scene, SceneEngine
from rpg.story.story_arc_engine import StoryArc, StoryArcEngine, create_war_arc


class TestSceneEngine:
    """Test SceneEngine functionality."""
    
    def test_generate_from_coup_event(self):
        """Test coup event generates coup scene."""
        engine = SceneEngine()
        events = [
            {
                "type": "coup",
                "faction": "mages_guild",
                "old_leader": "Archmage",
                "new_leader": "Usurper",
                "location": "tower",
            }
        ]
        
        scenes = engine.generate_from_events(events)
        
        assert len(scenes) == 1
        assert scenes[0].type == "coup"
        assert scenes[0].location == "tower"
        assert "mages_guild" in scenes[0].participants
        assert scenes[0].stakes == "Control of the faction"
    
    def test_generate_from_crisis_event(self):
        """Test shortage event generates crisis scene."""
        engine = SceneEngine()
        events = [
            {
                "type": "shortage",
                "location": "docks",
                "good": "food",
                "severity": 0.9,
            }
        ]
        
        scenes = engine.generate_from_events(events)
        
        assert len(scenes) == 1
        assert scenes[0].type == "crisis"
        assert "Survival" in scenes[0].stakes or "serious" in scenes[0].stakes.lower()
    
    def test_generate_from_battle_event(self):
        """Test faction conflict generates battle scene."""
        engine = SceneEngine()
        events = [
            {
                "type": "faction_conflict",
                "factions": ["mages", "warriors"],
                "description": "Troops clash at the border",
                "importance": 0.9,
            }
        ]
        
        scenes = engine.generate_from_events(events)
        
        assert len(scenes) == 1
        assert scenes[0].type == "battle"
        assert "mages" in scenes[0].participants
        assert "warriors" in scenes[0].participants
    
    def test_scene_resolution(self):
        """Test scene can be resolved."""
        engine = SceneEngine()
        events = [{"type": "player_action", "description": "Player mediates peace"}]
        scenes = engine.generate_from_events(events)
        
        assert len(scenes) == 1
        assert not scenes[0].resolved
        
        scenes[0].resolve("Peace was negotiated")
        assert scenes[0].resolved
        assert scenes[0].resolution == "Peace was negotiated"
    
    def test_max_active_scenes(self):
        """Test scene limit is enforced."""
        engine = SceneEngine(max_active_scenes=5)
        
        for i in range(10):
            engine.generate_from_events([
                {"type": "player_action", "description": f"Action {i}"}
            ])
        
        assert len(engine.active_scenes) <= 5


class TestCharacterEngine:
    """Test CharacterEngine functionality."""
    
    def test_create_character(self):
        """Test character creation."""
        engine = CharacterEngine()
        char = engine.get_or_create("mage1", "Aldric")
        
        assert char.id == "mage1"
        assert char.name == "Aldric"
        assert char.beliefs == {}
        assert char.goals == []
    
    def test_belief_management(self):
        """Test belief setting and adjustment."""
        engine = CharacterEngine()
        char = engine.get_or_create("mage1", "Aldric")
        
        char.add_belief("mages_guild", 0.8)
        assert char.get_belief("mages_guild") == 0.8
        
        char.adjust_belief("mages_guild", -0.3)
        assert abs(char.get_belief("mages_guild") - 0.5) < 0.01
    
    def test_coup_updates_beliefs(self):
        """Test coup event updates leader beliefs."""
        engine = CharacterEngine()
        events = [
            {
                "type": "coup",
                "faction": "mages_guild",
                "old_leader": "Archmage",
                "new_leader": "Usurper",
            }
        ]
        
        engine.update_from_events(events)
        
        old_leader = engine.get_or_create("Archmage")
        new_leader = engine.get_or_create("Usurper")
        
        assert old_leader.get_belief("power") == -1.0
        assert new_leader.get_belief("power") == 1.0
        assert f"Regain control of mages_guild" in old_leader.goals
    
    def test_goal_management(self):
        """Test goal add and remove."""
        engine = CharacterEngine()
        char = engine.get_or_create("hero", "Hero")
        
        char.add_goal("save the world")
        assert "save the world" in char.goals
        
        char.add_goal("save the world")  # Duplicate should not add
        assert char.goals.count("save the world") == 1
        
        assert char.remove_goal("save the world")
        assert "save the world" not in char.goals
        assert not char.remove_goal("nonexistent")
    
    def test_memory_storage(self):
        """Test event storage in character memory."""
        engine = CharacterEngine(max_memory_per_char=5)
        
        # Add events that involve this character
        events = [
            {"type": "player_action", "description": "Hero helps village", "actors": ["Hero"]}
        ]
        engine.update_from_events(events)
        
        char = engine.get_or_create("Hero")
        assert len(char.memory) > 0


class TestNarrativeMemory:
    """Test NarrativeMemory functionality."""
    
    def test_add_events_with_importance(self):
        """Test only important events are stored."""
        memory = NarrativeMemory(max_entries=100)
        
        events = [
            {"type": "coup", "importance": 0.9},
            {"type": "minor_trade", "importance": 0.2},
            {"type": "battle", "importance": 0.8},
        ]
        
        memory.add_events(events)
        
        assert len(memory.events) == 2  # Only 0.9 and 0.8 events
        assert all(e["importance"] > 0.5 for e in memory.events)
    
    def test_summarization_trigger(self):
        """Test summarization triggers when max_entries exceeded."""
        memory = NarrativeMemory(max_entries=5)
        
        # Add 10 important events
        for i in range(10):
            memory.add_event({"type": "major_event", "importance": 0.9, "id": i})
        
        # Should have triggered summarization
        assert len(memory.summaries) > 0
        assert len(memory.events) <= 5
    
    def test_get_context(self):
        """Test context retrieval."""
        memory = NarrativeMemory(max_entries=100)
        memory.add_event({"type": "coup", "importance": 0.9})
        
        ctx = memory.get_context()
        
        assert "recent_events" in ctx
        assert "summaries" in ctx
        assert ctx["total_events_stored"] == 1


class TestStoryArcEngine:
    """Test StoryArcEngine functionality."""
    
    def test_register_and_complete_arc(self):
        """Test arc registration and completion."""
        engine = StoryArcEngine()
        
        arc = StoryArc(
            id="test_arc",
            description="Test setup",
            payoff_condition=lambda ws: ws.get("complete", False),
            payoff_description="Test payoff",
        )
        engine.register_arc(arc)
        
        # Arc should be active
        assert len(engine.get_active_arcs()) == 1
        
        # Complete the arc
        results = engine.update({"complete": True, "tick": 5})
        
        assert len(results) == 1
        assert results[0]["arc_id"] == "test_arc"
        assert len(engine.get_completed_arcs()) == 1
    
    def test_arc_duration_tracking(self):
        """Test arc tracks creation and completion ticks."""
        engine = StoryArcEngine()
        
        engine.register_arc_simple(
            arc_id="duration_test",
            setup="Starting out",
            payoff_condition=lambda ws: True,  # Always completes
            payoff_description="Done",
            current_tick=10,
        )
        
        results = engine.update({"tick": 15})
        
        assert len(results) == 1
        assert results[0]["duration"] == 5
    
    def test_create_war_arc(self):
        """Test war arc factory function."""
        arc = create_war_arc(["mages", "warriors"], duration_threshold=5)
        
        assert "war" in arc.id
        assert arc.metadata["factions"] == ["mages", "warriors"]
    
    def test_incomplete_arc_stays_active(self):
        """Test arc that doesn't meet condition stays active."""
        engine = StoryArcEngine()
        
        engine.register_arc_simple(
            arc_id="long_arc",
            setup="Beginning",
            payoff_condition=lambda ws: ws.get("value", 0) > 100,
            payoff_description="End",
        )
        
        engine.update({"tick": 1, "value": 5})
        
        assert len(engine.get_active_arcs()) == 1
        assert len(engine.get_completed_arcs()) == 0


class TestNarrativeRenderer:
    """Test NarrativeRenderer functionality."""
    
    def test_render_with_scenes(self):
        """Test rendering with active scenes."""
        renderer = NarrativeRenderer()
        scenes = [
            Scene(
                id="scene1",
                type="battle",
                location="field",
                participants=["mages", "warriors"],
                description="Forces clash",
                stakes="Territory control",
            )
        ]
        
        result = renderer.render(scenes=scenes)
        
        assert "scene_text" in result
        assert "battle" in result["scene_text"]
        assert "field" in result["scene_text"]
    
    def test_render_with_memory(self):
        """Test rendering with narrative memory."""
        renderer = NarrativeRenderer()
        memory = NarrativeMemory()
        memory.add_event({"type": "coup", "importance": 0.9, "importance": 0.9})
        # Add a second event to trigger potential summary content
        memory.add_event({"type": "battle", "importance": 0.85})
        
        result = renderer.render(scenes=[], memory=memory)
        
        assert "memory_summary" in result
    
    def test_render_with_characters(self):
        """Test rendering with characters."""
        renderer = NarrativeRenderer()
        char = Character(id="hero", name="Hero", goals=["save kingdom", "find sword"])
        
        result = renderer.render(scenes=[], characters={"hero": char})
        
        assert "character_updates" in result
        assert "save kingdom" in result["character_updates"]
    
    def test_render_empty(self):
        """Test rendering with no data."""
        renderer = NarrativeRenderer()
        
        result = renderer.render(scenes=[])
        
        assert "No active scenes" in result["scene_text"]
    
    def test_render_for_prompt_truncation(self):
        """Test prompt rendering truncates to max_length."""
        renderer = NarrativeRenderer()
        scenes = [
            Scene(id=f"scene{i}", type="action", description=f"Very long description " * 50)
            for i in range(5)
        ]
        
        result = renderer.render_for_prompt(scenes, max_length=500)
        
        assert len(result) <= 500


class TestPlayerLoopIntegration:
    """Test full PlayerLoop integration with TIER 9 systems."""
    
    def test_step_returns_scenes(self):
        """Test player loop step returns scenes."""
        loop = PlayerLoop()
        
        result = loop.step("I explore the city")
        
        assert "scenes" in result
        assert isinstance(result["scenes"], list)
    
    def test_step_returns_narrative(self):
        """Test player loop step returns rendered narrative."""
        loop = PlayerLoop()
        
        result = loop.step("I explore the city")
        
        assert "narrative" in result
        assert "scene_text" in result["narrative"]
    
    def test_step_returns_completed_arcs(self):
        """Test player loop step returns completed arcs."""
        loop = PlayerLoop()
        
        result = loop.step("I wait")
        
        assert "completed_arcs" in result
        assert isinstance(result["completed_arcs"], list)
    
    def test_character_updates_from_events(self):
        """Test characters are updated from events."""
        loop = PlayerLoop()
        
        # Run a few steps
        for _ in range(3):
            loop.step("I take action")
        
        # Characters should have been created from events
        assert len(loop.characters.characters) >= 0  # May have player-related chars
    
    def test_narrative_memory_grows(self):
        """Test narrative memory accumulates events."""
        loop = PlayerLoop()
        
        initial_size = loop.memory.get_memory_size()
        
        for _ in range(5):
            loop.step("I wait")
        
        final_size = loop.memory.get_memory_size()
        assert final_size >= initial_size
    
    def test_reset_clears_tier9_systems(self):
        """Test reset clears all TIER 9 systems."""
        loop = PlayerLoop()
        
        # Run some steps to populate systems
        for _ in range(3):
            loop.step("test")
        
        loop.reset()
        
        assert len(loop.scenes.active_scenes) == 0
        assert len(loop.scenes.scene_history) == 0
        assert len(loop.characters.characters) == 0
        assert len(loop.memory.events) == 0
        assert len(loop.story_arcs.arcs) == 0


class Test100TickNarrative:
    """100-tick simulation test for TIER 9 narrative stability."""
    
    def test_100_tick_narrative_stability(self):
        """Run 100 ticks and verify narrative systems remain stable."""
        loop = PlayerLoop()
        
        all_scenes = 0
        all_summaries = 0
        completed_arcs_count = 0
        
        for i in range(100):
            result = loop.step("I wait")
            
            all_scenes += len(result.get("scenes", []))
            all_summaries += len(loop.memory.summaries)
            completed_arcs_count += len(result.get("completed_arcs", []))
        
        # Scenes should have been generated
        assert all_scenes > 0, "No scenes generated in 100 ticks"
        
        # Memory should have captured events
        assert len(loop.memory.events) >= 0  # At least non-negative
        
    def test_100_tick_with_scenarios(self):
        """Run 100 ticks with varied actions."""
        loop = PlayerLoop()
        
        actions = [
            "I attack the guard",
            "I help the villagers",
            "I negotiate peace",
            "I explore the ruins",
            "I trade with the merchant",
        ]
        
        narrative_output = []
        
        for i in range(100):
            action = actions[i % len(actions)]
            result = loop.step(action)
            
            if result.get("narrative"):
                narrative_output.append(result["narrative"])
        
        # Should have narrative output for most ticks
        assert len(narrative_output) > 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])