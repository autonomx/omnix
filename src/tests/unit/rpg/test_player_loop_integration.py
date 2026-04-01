"""Player Loop Integration Test — STEP 7 of RPG Design Implementation.

Minimal integration test verifying that the player loop connects
world simulation, narrative conversion, scene management, and narration.

Test Coverage:
    - PlayerLoop.step() returns narration
    - Events are properly converted and scored
    - Scene context is tracked
    - Template fallback works without LLM
    - Empty input handling
    - Multiple player actions in sequence
"""

from __future__ import annotations

import pytest
import sys
import os
from unittest.mock import MagicMock

# Add src/app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'app'))

# Import narrative components
from rpg.narrative.narrative_event import NarrativeEvent
from rpg.narrative.narrative_director import NarrativeDirector
from rpg.narrative.scene_manager import SceneManager
from rpg.narrative.narrative_generator import NarrativeGenerator

# Import player loop
from rpg.core.player_loop import PlayerLoop


class TestNarrativeEvent:
    """Unit tests for NarrativeEvent dataclass."""

    def test_create_event(self):
        event = NarrativeEvent(
            id="evt_001",
            type="combat",
            description="The knight strikes the dragon",
            actors=["knight", "dragon"],
            location="dragon_lair",
            importance=0.8,
        )
        assert event.id == "evt_001"
        assert event.type == "combat"
        assert event.description == "The knight strikes the dragon"
        assert "knight" in event.actors
        assert "dragon" in event.actors
        assert event.location == "dragon_lair"
        assert event.importance == 0.8

    def test_event_to_dict(self):
        event = NarrativeEvent(
            id="evt_002",
            type="death",
            description="The goblin falls",
            actors=["goblin"],
            importance=0.9,
        )
        d = event.to_dict()
        assert d["id"] == "evt_002"
        assert d["type"] == "death"
        assert d["description"] == "The goblin falls"
        assert d["actors"] == ["goblin"]

    def test_event_from_dict(self):
        data = {
            "id": "evt_003",
            "type": "heal",
            "description": "Healing light envelops the warrior",
            "actors": ["warrior"],
            "location": "temple",
            "importance": 0.6,
        }
        event = NarrativeEvent.from_dict(data, raw_event={"extra": "data"})
        assert event.id == "evt_003"
        assert event.type == "heal"

    def test_narrative_priority(self):
        event1 = NarrativeEvent(
            id="evt_high", type="death", description="death",
            importance=0.9, emotional_weight=1.0,
        )
        event2 = NarrativeEvent(
            id="evt_low", type="move", description="move",
            importance=0.3, emotional_weight=0.0,
        )
        assert event1.narrative_priority() > event2.narrative_priority()


class TestNarrativeDirector:
    """Unit tests for NarrativeDirector."""

    def test_convert_events(self):
        director = NarrativeDirector()
        world_events = [
            {"type": "combat", "description": "Player fights guard", "actors": ["player", "guard"]},
            {"type": "death", "description": "Guard falls", "actors": ["guard"]},
        ]
        result = director.convert_events(world_events)
        assert len(result) == 2
        assert isinstance(result[0], NarrativeEvent)
        assert result[0].type == "combat"
        assert result[1].type == "death"

    def test_convert_empty_events(self):
        director = NarrativeDirector()
        result = director.convert_events([])
        assert result == []

    def test_score_importance(self):
        director = NarrativeDirector()
        combat_event = {"type": "combat", "actors": ["player"]}
        move_event = {"type": "move", "actors": ["npc"]}
        death_event = {"type": "death", "actors": ["player", "boss"]}

        assert director.score_importance(combat_event) > director.score_importance(move_event)
        assert director.score_importance(death_event) >= director.score_importance(combat_event)

    def test_score_emotion(self):
        director = NarrativeDirector()
        death_event = {"type": "death"}
        move_event = {"type": "move"}
        assert director.score_emotion(death_event) > director.score_emotion(move_event)

    def test_select_focus_events(self):
        director = NarrativeDirector()
        events = [
            NarrativeEvent(id="1", type="death", description="death", importance=0.9, emotional_weight=1.0),
            NarrativeEvent(id="2", type="move", description="move", importance=0.2, emotional_weight=0.0),
            NarrativeEvent(id="3", type="combat", description="combat", importance=0.6, emotional_weight=0.6),
        ]
        focus = director.select_focus_events(events, max_events=2)
        assert len(focus) == 2
        # Death should be first (highest priority)
        assert focus[0].type == "death"

    def test_get_recent_events(self):
        director = NarrativeDirector(max_buffer=5)
        events = [{"type": f"event_{i}"} for i in range(10)]
        director.convert_events(events)
        recent = director.get_recent_events(limit=3)
        assert len(recent) <= 3

    def test_clear_buffer(self):
        director = NarrativeDirector()
        director.convert_events([{"type": "combat"}])
        assert len(director.recent_events) > 0
        director.clear_buffer()
        assert len(director.recent_events) == 0


class TestSceneManager:
    """Unit tests for SceneManager."""

    def test_create_scene_from_events(self):
        sm = SceneManager()
        events = [{"location": "forest", "actors": ["player"], "type": "move"}]
        sm.update_scene(events)
        assert sm.active_scene is not None
        assert sm.active_scene.location == "forest"

    def test_no_events_no_scene(self):
        sm = SceneManager()
        sm.update_scene([])
        assert sm.active_scene is None

    def test_get_scene_context(self):
        sm = SceneManager()
        ctx = sm.get_scene_context()
        assert ctx == {
            "location": "unknown",
            "participants": [],
            "recent_events": [],
            "mood": "neutral",
        }

    def test_scene_context_after_update(self):
        sm = SceneManager()
        sm.update_scene([{"location": "dungeon", "actors": ["hero"], "type": "move"}])
        ctx = sm.get_scene_context()
        assert ctx["location"] == "dungeon"
        assert "hero" in ctx["participants"]

    def test_event_memory_bounded(self):
        sm = SceneManager(max_events_per_scene=3)
        events = [{"location": "hub", "actors": [f"npc_{i}"], "type": "move"} for i in range(10)]
        sm.update_scene(events)
        assert len(sm.active_scene.recent_events) <= 3

    def test_scene_transition(self):
        sm = SceneManager()
        sm.update_scene([{"location": "forest", "actors": ["player"], "type": "move"}])
        assert sm.active_scene.location == "forest"
        sm.update_scene([{"location": "dungeon", "actors": ["player"], "type": "move"}])
        assert sm.active_scene.location == "dungeon"

    def test_end_scene(self):
        sm = SceneManager()
        sm.update_scene([{"location": "forest", "actors": ["player"], "type": "move"}])
        completed = sm.end_scene()
        assert completed is not None
        assert completed.location == "forest"
        assert sm.active_scene is None

    def test_force_new_scene(self):
        sm = SceneManager()
        sm.force_new_scene("new_location")
        assert sm.active_scene is not None
        assert sm.active_scene.location == "new_location"

    def test_mood_updates(self):
        sm = SceneManager()
        dark_events = [{"type": "combat", "actors": ["player"]}, {"type": "death", "actors": ["enemy"]}]
        sm.update_scene(dark_events)
        assert sm.active_scene.mood in ["tense", "dark"]


class TestNarrativeGenerator:
    """Unit tests for NarrativeGenerator."""

    def test_template_generation(self):
        gen = NarrativeGenerator()  # No LLM = template mode
        events = [
            NarrativeEvent(id="1", type="combat", description="Player fights", actors=["player"]),
        ]
        ctx = {"location": "arena", "participants": ["player"], "mood": "tense"}
        result = gen.generate(events, ctx)
        assert len(result) > 0

    def test_empty_events(self):
        gen = NarrativeGenerator()
        result = gen.generate([], {"location": "void"})
        assert result == ""

    def test_generate_from_dicts(self):
        gen = NarrativeGenerator()
        events = [{"type": "death", "description": "Boss dies", "actors": ["boss"]}]
        ctx = {"location": "throne"}
        result = gen.generate_from_dicts(events, ctx)
        assert len(result) > 0
        # Should mention the death
        assert "fall" in result.lower() or "death" in result.lower()

    def test_llm_fallback_on_error(self):
        bad_llm = MagicMock(side_effect=RuntimeError("API down"))
        gen = NarrativeGenerator(llm=bad_llm, style="dramatic")
        events = [
            NarrativeEvent(id="1", type="combat", description="Battle ensues", actors=["hero"]),
        ]
        ctx = {"location": "field", "participants": ["hero"], "mood": "tense"}
        result = gen.generate(events, ctx)
        # Should fall back to template
        assert len(result) > 0

    def test_max_words_trimming(self):
        gen = NarrativeGenerator(max_words=10)
        events = [
            NarrativeEvent(id=f"e_{i}", type="speak", description=f"Speaking event number {i}")
            for i in range(5)
        ]
        result = gen._generate_with_templates(events)
        assert len(result.split()) <= gen.max_words + 2  # +2 for "..."


class TestPlayerLoop:
    """Integration tests for PlayerLoop — STEP 7 of rpg-design.txt."""

    def _make_mocks(self):
        director = MagicMock(spec=NarrativeDirector)
        sm = MagicMock(spec=SceneManager)
        gen = MagicMock(spec=NarrativeGenerator)

        director.convert_events.return_value = [
            NarrativeEvent(id="1", type="combat", description="Fight!")
        ]
        director.select_focus_events.return_value = [
            NarrativeEvent(id="1", type="combat", description="Fight!")
        ]
        sm.get_scene_context.return_value = {
            "location": "arena",
            "participants": ["player"],
            "mood": "tense",
        }
        gen.generate.return_value = "The player fights bravely."

        world = MagicMock()
        world.world_tick.return_value = [
            {"type": "combat", "description": "Player fights guard", "actors": ["player", "guard"]}
        ]

        return world, director, sm, gen

    def test_player_loop_runs(self):
        world, director, sm, gen = self._make_mocks()
        loop = PlayerLoop(
            world=world,
            director=director,
            scene_manager=sm,
            narrator=gen,
        )

        result = loop.step("I attack the guard")

        assert "narration" in result
        assert len(result["events"]) > 0
        assert len(result["narration"]) > 0

    def test_player_loop_no_director_fallback(self):
        sm = MagicMock(spec=SceneManager)
        sm.get_scene_context.return_value = {}
        gen = MagicMock(spec=NarrativeGenerator)
        gen.generate.return_value = "Template fallback narrative."

        world = MagicMock()
        world.world_tick.return_value = [
            {"type": "damage", "description": "Player is hit", "actors": ["player"]}
        ]

        loop = PlayerLoop(world=world, scene_manager=sm, narrator=gen)
        result = loop.step("I dodge")
        assert "narration" in result
        # Without director, all events become narrative events
        assert len(result["events"]) > 0

    def test_player_loop_no_narration(self):
        world, director, sm, gen = self._make_mocks()
        loop = PlayerLoop(world=world, director=director, scene_manager=sm, narrator=gen)
        result = loop.step_no_narration("I prepare")
        assert result["narration"] == ""
        assert len(result["events"]) > 0

    def test_player_loop_convert_input(self):
        loop = PlayerLoop()
        event = loop._convert_input("I attack the guard")
        assert event["type"] == "player_action"
        assert "I attack" in event["description"]
        assert event["actors"] == ["player"]

    def test_player_loop_reset(self):
        world, director, sm, gen = self._make_mocks()
        loop = PlayerLoop(world=world, director=director, scene_manager=sm, narrator=gen)
        loop.step("I attack")
        assert loop.get_last_result() != {}
        loop.reset()
        assert loop.get_last_result() == {}

    def test_player_loop_with_simulate_fn(self):
        def tick_fn():
            return [
                {"type": "combat", "description": "Player vs guard", "actors": ["player", "guard"]},
            ]
        director = NarrativeDirector()
        sm = SceneManager()
        gen = NarrativeGenerator()
        loop = PlayerLoop(director=director, scene_manager=sm, narrator=gen, simulate_fn=tick_fn)

        result = loop.step("I fight")
        assert "narration" in result
        assert len(result["events"]) > 0

    def test_player_loop_empty_simulation_fn(self):
        def tick_fn():
            return []
        director = NarrativeDirector()
        sm = SceneManager()
        gen = NarrativeGenerator()
        loop = PlayerLoop(director=director, scene_manager=sm, narrator=gen, simulate_fn=tick_fn)

        result = loop.step("I wait")
        assert "narration" in result
        # Player event description is returned even with no simulation events
        assert len(result["narration"]) > 0
