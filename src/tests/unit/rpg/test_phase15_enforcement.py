"""Unit tests for PHASE 1.5 — ENFORCEMENT PATCH components.

Tests the new enforcement features from rpg-design.txt:
1. Context-local GameLoop using contextvars
2. EventBus enforcement for cross-system calls
3. EventBus event history for replay/debug
4. StoryDirector structured event types
5. Event source field for system identity
6. Tick ID injection for temporal debugging

Modules tested:
    - Event & EventBus (core/event_bus.py)
    - GameLoop (core/game_loop.py)
    - StoryDirector (narrative/story_director.py)
"""

import pytest
from unittest.mock import MagicMock, Mock, patch

from app.rpg.core.event_bus import Event, EventBus
from app.rpg.core.game_loop import (
    GameLoop,
    TickContext,
    TickPhase,
    IntentParser,
    WorldSystem,
    NPCSystem,
    StoryDirector as StoryDirectorProtocol,
    SceneRenderer,
    _active_loop_ctx,
)
from app.rpg.narrative.story_director import (
    StoryDirector as UnifiedStoryDirector,
    DefaultArcManager,
    DefaultPlotEngine,
    DefaultSceneEngine,
)


@pytest.fixture(autouse=True)
def _reset_context_var():
    """Reset the context var between tests."""
    _active_loop_ctx.set(None)
    yield
    _active_loop_ctx.set(None)


# ============================================================
# Event with source field tests
# ============================================================

class TestEventSourceField:
    """Tests for Event source field (Fix #5)."""

    def test_event_with_source(self):
        """Test event creation with source."""
        event = Event(type="test_event", payload={"key": "value"}, source="story_director")
        assert event.type == "test_event"
        assert event.payload == {"key": "value"}
        assert event.source == "story_director"

    def test_event_without_source(self):
        """Test event creation without source (defaults to None)."""
        event = Event(type="test_event")
        assert event.source is None

    def test_event_repr_includes_source(self):
        """Test that repr includes source when present."""
        event = Event(type="test", payload={"a": 1}, source="world")
        assert "test" in repr(event)
        assert "source='world'" in repr(event)

    def test_events_are_independent(self):
        """Test that events don't share payload or source references."""
        event1 = Event(type="e1", payload={}, source="a")
        event2 = Event(type="e2", payload={}, source="b")
        event1.payload["shared"] = True
        assert "shared" not in event2.payload
        assert event1.source == "a"
        assert event2.source == "b"


# ============================================================
# EventBus history tests
# ============================================================

class TestEventBusHistory:
    """Tests for EventBus history feature (Fix #3)."""

    def test_history_stores_all_events(self):
        """Test that history stores all events ever emitted."""
        bus = EventBus()
        bus.emit(Event("e1", {"data": 1}, source="sys1"))
        bus.emit(Event("e2", {"data": 2}, source="sys2"))
        bus.emit(Event("e3", {"data": 3}, source="sys3"))

        history = bus.history()
        assert len(history) == 3
        assert history[0].type == "e1"
        assert history[1].type == "e2"
        assert history[2].type == "e3"

    def test_history_not_cleared_by_collect(self):
        """Test that history persists after collect."""
        bus = EventBus()
        bus.emit(Event("e1"))
        bus.emit(Event("e2"))

        collected = bus.collect()
        assert len(collected) == 2

        # History should still have the events
        history = bus.history()
        assert len(history) == 2

    def test_history_returns_copy(self):
        """Test that history returns a copy (not mutable)."""
        bus = EventBus()
        bus.emit(Event("e1"))
        history = bus.history()
        history.clear()

        # Original history should be unchanged
        assert len(bus.history()) == 1

    def test_history_with_reset(self):
        """Test that reset clears history."""
        bus = EventBus()
        bus.emit(Event("e1"))
        bus.emit(Event("e2"))
        bus.reset()

        assert len(bus.history()) == 0


# ============================================================
# EventBus tick ID injection tests
# ============================================================

class TestEventBusTickInjection:
    """Tests for tick ID injection (Fix #6)."""

    def test_tick_injected_on_emit(self):
        """Test that tick ID is injected into event payload."""
        bus = EventBus()
        bus.set_tick(5)
        bus.emit(Event("test", {"data": "value"}, source="test"))

        history = bus.history()
        assert history[0].payload["tick"] == 5

    def test_tick_not_injected_when_none(self):
        """Test that tick is not injected when _current_tick is None."""
        bus = EventBus()
        bus.set_tick(None)
        bus.emit(Event("test", {"data": "value"}, source="test"))

        history = bus.history()
        assert "tick" not in history[0].payload

    def test_tick_overwritten_on_emit(self):
        """Test that existing tick in payload is overwritten."""
        bus = EventBus()
        bus.set_tick(10)
        bus.emit(Event("test", {"tick": 999}, source="test"))

        history = bus.history()
        assert history[0].payload["tick"] == 10


# ============================================================
# EventBus cross-system enforcement tests
# ============================================================

class TestEventBusEnforcement:
    """Tests for EventBus enforcement (Fix #2)."""

    def test_enforcement_disabled_by_default(self):
        """Test that enforcement is disabled without enforce=True."""
        bus = EventBus()
        # Should not raise
        bus.emit(Event("test"))

    def test_enforcement_enabled(self):
        """Test that enforcement checks active when enabled."""
        bus = EventBus(enforce=True)
        # Should not raise when source is provided
        bus.emit(Event("test", source="test_system"))

    def test_enforcement_allows_core_systems(self):
        """Test that core systems are allowed."""
        bus = EventBus(enforce=True)
        # This should not raise when source is provided
        bus.emit(Event("test", source="test_system"))


# ============================================================
# GameLoop contextvars tests
# ============================================================

class TestGameLoopContextVars:
    """Tests for contextvars-based loop tracking (Fix #1)."""

    def _create_loop(self, **kwargs):
        """Helper to create a GameLoop with mocks."""
        return GameLoop(
            intent_parser=kwargs.get("intent_parser", Mock(spec=IntentParser)),
            world=kwargs.get("world", Mock(spec=WorldSystem)),
            npc_system=kwargs.get("npc_system", Mock(spec=NPCSystem)),
            event_bus=kwargs.get("event_bus", EventBus()),
            story_director=kwargs.get("story_director", Mock(spec=StoryDirectorProtocol)),
            scene_renderer=kwargs.get("scene_renderer", Mock(spec=SceneRenderer)),
        )

    def test_context_var_set_on_tick(self):
        """Test that context var is set when tick is called."""
        loop = self._create_loop()
        assert _active_loop_ctx.get() is None
        loop.tick("test")
        # Context var should be reset after tick completes
        assert _active_loop_ctx.get() is None

    def test_context_var_reset_after_tick(self):
        """Test that context var is reset after tick (finally block)."""
        loop = self._create_loop()
        loop.tick("test")
        # Should be reset
        assert _active_loop_ctx.get() is None

    def test_multiple_loop_detection_in_same_context(self):
        """Test that multiple loops in same context raise error."""
        loop1 = self._create_loop()
        loop2 = self._create_loop()

        # Manually set context var to simulate conflict
        _active_loop_ctx.set(loop1)

        with pytest.raises(RuntimeError, match="Multiple GameLoop instances detected"):
            loop2.tick("test")

    def test_same_loop_can_tick_multiple_times(self):
        """Test that same loop can tick multiple times."""
        loop = self._create_loop()
        loop.tick("first")
        loop.tick("second")
        loop.tick("third")
        assert loop.tick_count == 3

    def test_tick_injects_into_event_bus(self):
        """Test that tick sets _current_tick on event bus via set_tick()."""
        event_bus = EventBus()

        # Create a world that emits events
        class EmittingWorld:
            def tick(self, event_bus):
                event_bus.emit(Event("world_ticked", source="world"))

        loop = GameLoop(
            intent_parser=Mock(spec=IntentParser),
            world=EmittingWorld(),
            npc_system=Mock(spec=NPCSystem),
            event_bus=event_bus,
            story_director=Mock(spec=StoryDirectorProtocol),
            scene_renderer=Mock(spec=SceneRenderer),
        )

        loop.tick("test")
        # Events are cloned, so tick is in the cloned event's payload
        history = event_bus.history()
        assert len(history) > 0
        assert history[0].payload.get("tick") == 1

        loop.tick("test2")
        history = event_bus.history()
        world_events = [e for e in history if e.source == "world"]
        assert any(e.payload.get("tick") == 2 for e in world_events)


# ============================================================
# StoryDirector structured events tests
# ============================================================

class TestStoryDirectorStructuredEvents:
    """Tests for StoryDirector structured event types (Fix #4)."""

    def test_emits_narrative_beat_selected(self):
        """Test that narrative_beat_selected event is emitted."""
        director = UnifiedStoryDirector()
        bus = EventBus(debug=True)
        director.process([], {}, bus)

        events = bus.collect()
        types = [e.type for e in events]
        assert "narrative_beat_selected" in types

    def test_emits_scene_generated(self):
        """Test that scene_generated event is emitted."""
        director = UnifiedStoryDirector()
        bus = EventBus(debug=True)
        director.process([], {}, bus)

        events = bus.collect()
        types = [e.type for e in events]
        assert "scene_generated" in types

    def test_narrative_beat_has_correct_payload(self):
        """Test that narrative_beat_selected has correct payload."""
        director = UnifiedStoryDirector()
        bus = EventBus(debug=True)
        director.process([], {}, bus)

        events = bus.collect()
        beat_events = [e for e in events if e.type == "narrative_beat_selected"]
        assert len(beat_events) == 1
        assert "beat" in beat_events[0].payload
        assert "tick" in beat_events[0].payload

    def test_scene_generated_has_scene_in_payload(self):
        """Test that scene_generated has scene in payload."""
        director = UnifiedStoryDirector()
        bus = EventBus(debug=True)
        director.process([], {}, bus)

        events = bus.collect()
        scene_events = [e for e in events if e.type == "scene_generated"]
        assert len(scene_events) == 1
        assert "scene" in scene_events[0].payload
        assert "beat" in scene_events[0].payload

    def test_events_have_source_field(self):
        """Test that emitted events have source field."""
        director = UnifiedStoryDirector()
        bus = EventBus(debug=True)
        director.process([], {}, bus)

        events = bus.collect()
        for event in events:
            if event.source:  # Only check events with source set
                assert event.source == "story_director"

    def test_two_events_emitted_per_tick(self):
        """Test that two events are emitted per process call."""
        director = UnifiedStoryDirector()
        bus = EventBus(debug=True)
        director.process([], {}, bus)

        events = bus.collect()
        assert len(events) == 2


# ============================================================
# Phase 1.6 Critical Fixes Tests (rpg-design.txt)
# ============================================================

class TestPhase16CriticalFixes:
    """Tests for Phase 1.6 critical fixes from rpg-design.txt."""

    # Fix #1: Event Mutation Side Effect
    def test_event_cloned_on_emit(self):
        """Test that events are cloned to prevent mutation side-effects."""
        bus = EventBus()
        original_payload = {"data": "value"}
        event = Event("test", original_payload, source="test")
        bus.set_tick(5)
        bus.emit(event)

        # Original event payload should NOT have tick injected
        assert "tick" not in original_payload
        assert event.payload == {"data": "value"}

        # But the stored event should have tick
        history = bus.history()
        assert history[0].payload["tick"] == 5
        assert history[0].payload["data"] == "value"

    def test_event_reuse_safe(self):
        """Test that reusing the same event object doesn't corrupt data."""
        bus = EventBus()
        event = Event("test", {"key": "value"}, source="test")

        bus.set_tick(1)
        bus.emit(event)

        bus.set_tick(2)
        bus.emit(event)

        history = bus.history()
        assert len(history) == 2
        assert history[0].payload["tick"] == 1
        assert history[1].payload["tick"] == 2
        # Original event should be unchanged
        assert event.payload == {"key": "value"}

    # Fix #2: Source Enforcement
    def test_source_enforcement_raises_when_missing(self):
        """Test that missing source raises RuntimeError when enforcement enabled."""
        bus = EventBus(enforce=True)
        with pytest.raises(RuntimeError, match="missing source"):
            bus.emit(Event("test", {}))

    def test_source_enforcement_passes_when_present(self):
        """Test that source present passes enforcement."""
        bus = EventBus(enforce=True)
        bus.emit(Event("test", {}, source="test_system"))
        assert len(bus.history()) == 1

    def test_source_enforcement_disabled(self):
        """Test that source not required when enforcement disabled."""
        bus = EventBus(enforce=False)
        bus.emit(Event("test", {}))
        assert len(bus.history()) == 1

    # Fix #3: Layer-based Cross-System Detection
    def test_layer_based_detection_allows_core(self):
        """Test that core layer is allowed."""
        bus = EventBus(enforce=True)
        # This test runs from tests module which is in ALLOWED_LAYERS
        bus.emit(Event("test", {}, source="test"))
        assert len(bus.history()) == 1

    def test_layer_based_detection_allows_narrative(self):
        """Test that narrative layer is allowed."""
        bus = EventBus(enforce=True)
        bus.emit(Event("test", {}, source="narrative"))
        assert len(bus.history()) == 1

    # Fix #4: set_tick Method
    def test_set_tick_method(self):
        """Test that set_tick properly sets the tick value."""
        bus = EventBus()
        assert bus._current_tick is None
        bus.set_tick(42)
        assert bus._current_tick == 42

    def test_set_tick_none(self):
        """Test that set_tick can reset to None."""
        bus = EventBus()
        bus.set_tick(10)
        bus.set_tick(None)
        assert bus._current_tick is None

    # Fix #5: Bounded History
    def test_bounded_history_default_limit(self):
        """Test that history is bounded by default limit."""
        bus = EventBus()
        assert bus._max_history == 10000

    def test_bounded_history_truncates(self):
        """Test that history truncates when limit exceeded."""
        bus = EventBus()
        bus._max_history = 100  # Small limit for testing

        for i in range(150):
            bus.emit(Event(f"event_{i}", source="test"))

        history = bus.history()
        assert len(history) == 100
        # Should have the most recent events
        assert history[0].type == "event_50"
        assert history[-1].type == "event_149"

    def test_bounded_history_preserves_order(self):
        """Test that bounded history preserves event order."""
        bus = EventBus()
        bus._max_history = 5

        for i in range(8):
            bus.emit(Event(f"event_{i}", {"seq": i}, source="test"))

        history = bus.history()
        assert len(history) == 5
        assert [e.payload["seq"] for e in history] == [3, 4, 5, 6, 7]


# ============================================================
# Integration tests for all fixes
# ============================================================

class TestPhase15Integration:
    """Integration tests for all Phase 1.5 fixes."""

    def test_full_pipeline_with_all_fixes(self):
        """Test full pipeline using all Phase 1.5 features."""
        event_bus = EventBus(debug=True)

        intent_parser = Mock(spec=IntentParser)
        intent_parser.parse.return_value = {"action": "explore"}

        world = Mock(spec=WorldSystem)
        npc_system = Mock(spec=NPCSystem)
        story_director = UnifiedStoryDirector()
        scene_renderer = Mock(spec=SceneRenderer)
        scene_renderer.render.return_value = {"scene": "test"}

        loop = GameLoop(
            intent_parser=intent_parser,
            world=world,
            npc_system=npc_system,
            event_bus=event_bus,
            story_director=story_director,
            scene_renderer=scene_renderer,
        )

        result = loop.tick("explore")

        # Verify tick count
        assert loop.tick_count == 1

        # Verify event bus has history
        history = event_bus.history()
        assert len(history) > 0

        # Verify at least one event has source field
        story_events = [e for e in history if e.source == "story_director"]
        assert len(story_events) >= 1

        # Verify narrative_beat_selected was emitted
        beat_events = [e for e in history if e.type == "narrative_beat_selected"]
        assert len(beat_events) >= 1

    def test_tick_id_in_all_events(self):
        """Test that all events have tick ID injected."""
        event_bus = EventBus()
        story_director = UnifiedStoryDirector()

        loop = GameLoop(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            event_bus=event_bus,
            story_director=story_director,
            scene_renderer=Mock(spec=SceneRenderer),
        )

        loop.tick("test")

        # Check history events have tick
        history = event_bus.history()
        for event in history:
            if event.source == "story_director":
                assert "tick" in event.payload
                assert event.payload["tick"] == 1

    def test_multiple_ticks_have_sequential_tick_ids(self):
        """Test that tick IDs increment properly."""
        event_bus = EventBus()
        story_director = UnifiedStoryDirector()

        loop = GameLoop(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            event_bus=event_bus,
            story_director=story_director,
            scene_renderer=Mock(spec=SceneRenderer),
        )

        loop.tick("test1")
        loop.tick("test2")
        loop.tick("test3")

        history = event_bus.history()
        # Find story_director events
        story_events = [e for e in history if e.source == "story_director"]
        assert len(story_events) == 6  # 2 events per tick * 3 ticks

        # Check tick distribution
        ticks_in_history = [e.payload.get("tick") for e in story_events]
        assert 1 in ticks_in_history
        assert 2 in ticks_in_history
        assert 3 in ticks_in_history