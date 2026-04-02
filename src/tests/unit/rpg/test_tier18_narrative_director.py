"""Tests for Tier 18: Narrative Director (Meta-AI Story Director)."""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "app"))

from rpg.narrative.story_state import StoryState
from rpg.narrative.tension_engine import TensionEngine
from rpg.narrative.arc_manager import ArcManager
from rpg.narrative.event_injector import EventInjector
from rpg.narrative.narrative_director_t18 import NarrativeDirector


class TestStoryState:
    def test_initial_state(self):
        state = StoryState()
        assert state.tension == 0.3
        assert state.phase == "rising"
        assert state.active_arcs == []

    def test_add_event(self):
        state = StoryState()
        state.add_event({"type": "combat"})
        assert len(state.major_events) == 1

    def test_shift_phase(self):
        state = StoryState()
        state.shift_phase("climax")
        assert state.phase == "climax"


class TestTensionEngine:
    def test_initial_state(self):
        engine = TensionEngine()
        assert engine.tension == 0.3
        assert engine.phase == "rising"

    def test_climax_transition(self):
        engine = TensionEngine()
        state = StoryState()
        state.tension = 0.7
        world = {"global_tension": 1.0, "recent_events": [
            {"type": "combat"}, {"type": "death"}, {"type": "betrayal"}
        ]}
        engine.update(state, world)
        assert state.phase == "climax"

    def test_falling_transition(self):
        engine = TensionEngine()
        state = StoryState()
        state.tension = 0.2
        world = {"global_tension": 0.0}
        engine.update(state, world)
        assert state.phase == "falling"

    def test_tension_clamped(self):
        engine = TensionEngine()
        state = StoryState()
        state.tension = 0.9
        world = {"global_tension": 1.0, "recent_events": [
            {"type": "death"}, {"type": "betrayal"}, {"type": "combat"},
            {"type": "critical_hit"}, {"type": "damage"}
        ]}
        engine.update(state, world)
        assert 0.0 <= state.tension <= 1.0

    def test_reset(self):
        engine = TensionEngine()
        state = StoryState()
        world = {"global_tension": 1.0}
        engine.update(state, world)
        engine.reset()
        assert engine.tension == 0.3
        assert engine.phase == "rising"


class TestArcManager:
    def test_add_arc(self):
        manager = ArcManager()
        arc = manager.add_arc("revenge", "Seek vengeance")
        assert arc["id"] == "revenge"
        assert arc["status"] == "active"

    def test_arc_resolution(self):
        manager = ArcManager()
        manager.add_arc("test", "Test arc", progress=0.98)
        state = StoryState()
        manager.update(state)
        assert len(manager.active_arcs) == 0
        assert len(state.resolved_arcs) == 1

    def test_get_active_arc_ids(self):
        manager = ArcManager()
        manager.add_arc("a", "Arc A")
        manager.add_arc("b", "Arc B")
        assert manager.get_active_arc_ids() == ["a", "b"]


class TestEventInjector:
    def test_rising_phase_events(self):
        injector = EventInjector()
        state = StoryState()
        state.phase = "rising"
        import random
        random.seed(42)
        events = injector.inject(state, {})
        assert isinstance(events, list)

    def test_climax_phase_events(self):
        injector = EventInjector()
        state = StoryState()
        state.phase = "climax"
        import random
        random.seed(0)
        events = injector.inject(state, {})
        assert isinstance(events, list)

    def test_falling_phase_events(self):
        injector = EventInjector()
        state = StoryState()
        state.phase = "falling"
        events = injector.inject(state, {})
        assert isinstance(events, list)


class TestNarrativeDirector:
    def test_initial_state(self):
        director = NarrativeDirector()
        assert director.state.tension == 0.3
        assert director.state.phase == "rising"

    def test_update_returns_events(self):
        director = NarrativeDirector()
        world = {"global_tension": 0.5, "recent_events": []}
        events = director.update(world)
        assert isinstance(events, list)

    def test_update_updates_tension(self):
        director = NarrativeDirector()
        world = {"global_tension": 1.0, "recent_events": [{"type": "combat"}]}
        initial_tension = director.state.tension
        director.update(world)
        assert director.state.tension != initial_tension

    def test_update_updates_world_pacing(self):
        director = NarrativeDirector()
        world = {"global_tension": 1.0, "npc_activity_multiplier": 1.0}
        director.update(world)
        assert "npc_activity_multiplier" in world

    def test_force_emergence_boost(self):
        director = NarrativeDirector()
        initial = director.state.tension
        director.force_emergence_boost()
        assert director.state.tension > initial

    def test_reset(self):
        director = NarrativeDirector()
        world = {"global_tension": 1.0}
        director.update(world)
        director.reset()
        assert director.state.tension == 0.3
        assert director.state.phase == "rising"


class TestStoryPhases:
    def test_story_has_climax(self):
        director = NarrativeDirector()
        world = {"global_tension": 1.0}
        phases = []
        for _ in range(100):
            events = director.update(world)
            phases.append(director.state.phase)
        assert "climax" in phases

    def test_events_generated_with_high_tension(self):
        director = NarrativeDirector()
        world = {"global_tension": 1.0}
        events = director.update(world)
        assert isinstance(events, list)

    def test_phase_transitions(self):
        director = NarrativeDirector()
        phases_seen = set()
        world = {"global_tension": 0.8, "recent_events": [{"type": "combat"}]}
        for _ in range(200):
            director.update(world)
            phases_seen.add(director.state.phase)
        assert "climax" in phases_seen or "falling" in phases_seen
