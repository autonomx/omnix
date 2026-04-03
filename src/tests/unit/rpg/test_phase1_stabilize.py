"""Unit tests for PHASE 1 — STABILIZE components.

Tests the new single-authority game loop, event bus, story director,
and game engine components specified in rpg-design.txt.

Modules tested:
    - Event & EventBus (core/event_bus.py)
    - GameLoop (core/game_loop.py)
    - StoryDirector (narrative/story_director.py)
    - GameEngine (core/game_engine.py)
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
    StoryDirector,
    SceneRenderer,
)
from app.rpg.narrative.story_director import (
    StoryDirector as UnifiedStoryDirector,
    DefaultArcManager,
    DefaultPlotEngine,
    DefaultSceneEngine,
)
from app.rpg.core.game_engine import GameEngine

# Verify imports from core __init__
from app.rpg.core import Event as CoreEvent, EventBus as CoreEventBus
from app.rpg.core import GameLoop as CoreGameLoop, GameEngine as CoreGameEngine


@pytest.fixture(autouse=True)
def _reset_single_loop_guard():
    """Reset the GameLoop single-loop guard between tests."""
    GameLoop._active_loop = None
    yield
    GameLoop._active_loop = None


# ============================================================
# Event tests
# ============================================================

class TestEvent:
    """Tests for the Event dataclass."""

    def test_event_creation(self):
        """Test basic event creation."""
        event = Event(type="test_event", payload={"key": "value"})
        assert event.type == "test_event"
        assert event.payload == {"key": "value"}

    def test_event_default_payload(self):
        """Test that payload defaults to empty dict."""
        event = Event(type="minimal_event")
        assert event.payload == {}

    def test_event_repr(self):
        """Test event string representation."""
        event = Event(type="test", payload={"a": 1})
        assert "test" in repr(event)
        assert "a" in repr(event)

    def test_events_are_independent(self):
        """Test that events don't share payload references."""
        event1 = Event(type="e1")
        event2 = Event(type="e2")
        event1.payload["shared"] = True
        assert "shared" not in event2.payload


# ============================================================
# EventBus tests
# ============================================================

class TestEventBus:
    """Tests for the EventBus."""

    def test_emit_and_collect(self):
        """Test basic event emission and collection."""
        bus = EventBus()
        bus.emit(Event("test", {"data": 1}))
        events = bus.collect()
        assert len(events) == 1
        assert events[0].type == "test"

    def test_collect_clears_queue(self):
        """Test that collecting events clears the internal queue."""
        bus = EventBus()
        bus.emit(Event("test"))
        bus.collect()
        assert bus.pending_count == 0

    def test_multiple_events(self):
        """Test emitting and collecting multiple events."""
        bus = EventBus()
        for i in range(5):
            bus.emit(Event(f"type_{i}", {"index": i}))
        events = bus.collect()
        assert len(events) == 5
        assert events[2].type == "type_2"

    def test_peek_does_not_clear(self):
        """Test that peek doesn't modify the queue."""
        bus = EventBus()
        bus.emit(Event("test"))
        peeked = bus.peek()
        assert len(peeked) == 1
        assert bus.pending_count == 1  # Queue unchanged

    def test_clear(self):
        """Test clearing events without collecting."""
        bus = EventBus()
        for _ in range(3):
            bus.emit(Event("test"))
        bus.clear()
        assert bus.pending_count == 0

    def test_pending_count(self):
        """Test pending count property."""
        bus = EventBus()
        assert bus.pending_count == 0
        bus.emit(Event("test"))
        assert bus.pending_count == 1

    def test_debug_logging(self):
        """Test that debug mode logs events."""
        bus = EventBus(debug=True)
        bus.emit(Event("test", {"x": 1}))
        log = bus.log
        assert log is not None
        assert len(log) == 1
        assert log[0].type == "test"

    def test_no_logging_without_debug(self):
        """Test that log is None when debug is False."""
        bus = EventBus(debug=False)
        assert bus.log is None

    def test_reset(self):
        """Test reset clears queue and log."""
        bus = EventBus(debug=True)
        bus.emit(Event("test"))
        bus.reset()
        assert bus.pending_count == 0
        assert len(bus.log) == 0

    @patch("builtins.print")
    def test_debug_output(self, mock_print):
        """Test that debug mode prints events."""
        bus = EventBus(debug=True)
        bus.emit(Event("test", {"key": "value"}))
        # Debug should have been printed
        assert mock_print.called


# ============================================================
# GameLoop tests
# ============================================================

class TestGameLoop:
    """Tests for the GameLoop."""

    def _create_loop(self, **kwargs):
        """Helper to create a GameLoop with mocks."""
        return GameLoop(
            intent_parser=kwargs.get("intent_parser", Mock(spec=IntentParser)),
            world=kwargs.get("world", Mock(spec=WorldSystem)),
            npc_system=kwargs.get("npc_system", Mock(spec=NPCSystem)),
            event_bus=kwargs.get("event_bus", EventBus()),
            story_director=kwargs.get("story_director", Mock(spec=StoryDirector)),
            scene_renderer=kwargs.get("scene_renderer", Mock(spec=SceneRenderer)),
        )

    def test_basic_tick(self):
        """Test basic tick execution."""
        intent_parser = Mock(spec=IntentParser)
        intent_parser.parse.return_value = {"action": "look"}
        
        world = Mock(spec=WorldSystem)
        npc_system = Mock(spec=NPCSystem)
        event_bus = EventBus()
        
        story_director = Mock(spec=StoryDirector)
        story_director.process.return_value = {"narrative": "You see a dark room"}
        
        scene_renderer = Mock(spec=SceneRenderer)
        scene_renderer.render.return_value = {"scene": "dark_room"}

        loop = GameLoop(
            intent_parser=intent_parser,
            world=world,
            npc_system=npc_system,
            event_bus=event_bus,
            story_director=story_director,
            scene_renderer=scene_renderer,
        )

        result = loop.tick("look around")

        intent_parser.parse.assert_called_once_with("look around")
        world.tick.assert_called_once()
        npc_system.update.assert_called_once()
        story_director.process.assert_called_once()
        scene_renderer.render.assert_called_once()
        assert result["scene"] == "dark_room"

    def test_tick_count_increments(self):
        """Test that tick count increases with each tick."""
        loop = self._create_loop()
        assert loop.tick_count == 0
        loop.tick("first")
        assert loop.tick_count == 1
        loop.tick("second")
        assert loop.tick_count == 2

    def test_events_are_collected(self):
        """Test that events from the bus are collected and passed to director."""
        event_bus = EventBus()
        event_bus.emit(Event("npc_action", {"npc_id": 1}))
        event_bus.emit(Event("world_change", {"weather": "rain"}))

        story_director = Mock(spec=StoryDirector)
        story_director.process.return_value = {}

        loop = GameLoop(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            event_bus=event_bus,
            story_director=story_director,
            scene_renderer=Mock(spec=SceneRenderer),
        )

        loop.tick("test")

        # Director should receive both events
        call_args = story_director.process.call_args
        events_passed = call_args[0][0]
        assert len(events_passed) == 2
        assert events_passed[0].type == "npc_action"
        assert events_passed[1].type == "world_change"

    def test_pre_tick_callback(self):
        """Test pre-tick callback is called."""
        callback_called = []
        
        def pre_tick(ctx):
            callback_called.append(ctx.tick_number)

        loop = self._create_loop()
        loop.on_pre_tick(pre_tick)
        loop.tick("test")

        assert callback_called == [1]

    def test_post_tick_callback(self):
        """Test post-tick callback is called with scene."""
        results = []
        
        def post_tick(ctx):
            results.append(ctx.scene)

        scene_renderer = Mock(spec=SceneRenderer)
        scene_renderer.render.return_value = {"scene": "result"}
        loop = self._create_loop(scene_renderer=scene_renderer)
        loop.on_post_tick(post_tick)
        loop.tick("test")

        assert results[0]["scene"] == "result"
        assert "coherence" not in results[0]

    def test_event_callback(self):
        """Test event callback is called for each event."""
        captured_events = []
        
        loop = self._create_loop()
        
        # Add events to bus
        loop.event_bus.emit(Event("e1", {"data": 1}))
        loop.event_bus.emit(Event("e2", {"data": 2}))
        loop.on_event(lambda e: captured_events.append(e.type))
        
        loop.tick("test")

        assert captured_events == ["e1", "e2"]

    def test_reset(self):
        """Test reset clears all state."""
        loop = self._create_loop()
        loop.tick("test")
        loop.event_bus.emit(Event("test"))
        loop.reset()
        
        assert loop.tick_count == 0
        assert loop.event_bus.pending_count == 0


# ============================================================
# StoryDirector tests
# ============================================================

class TestStoryDirector:
    """Tests for the unified StoryDirector."""

    def test_process_returns_scene(self):
        """Test that process returns a scene dictionary."""
        director = UnifiedStoryDirector()
        bus = EventBus()
        result = director.process([], {}, bus)
        assert isinstance(result, dict)

    def test_process_with_events(self):
        """Test that events are recorded in the event log."""
        director = UnifiedStoryDirector()
        events = [Event("test", {"key": "value"})]
        bus = EventBus()
        director.process(events, {}, bus)
        
        assert director.tick_count == 1
        assert len(director.event_log) == 1
        assert director.event_log[0]["type"] == "test"
        # StoryDirector should have emitted scene_generated event
        emitted = bus.collect()
        scene_events = [e for e in emitted if e.type == "scene_generated"]
        assert len(scene_events) == 1

    def test_custom_arc_manager(self):
        """Test that custom arc manager is used."""
        arc_manager = Mock()
        arc_manager.update.return_value = [{"name": "quest_arc"}]
        arc_manager.reset = Mock()
        
        plot_engine = Mock()
        plot_engine.select.return_value = {}
        plot_engine.reset = Mock()
        
        scene_engine = Mock()
        scene_engine.generate.return_value = {}
        scene_engine.reset = Mock()

        director = UnifiedStoryDirector(
            arc_manager=arc_manager,
            plot_engine=plot_engine,
            scene_engine=scene_engine,
        )
        bus = EventBus()
        director.process([], {}, bus)

        arc_manager.update.assert_called_once()
        plot_engine.select.assert_called_once()
        scene_engine.generate.assert_called_once()

    def test_reset(self):
        """Test that reset clears state."""
        director = UnifiedStoryDirector()
        bus = EventBus()
        director.process([Event("test")], {}, bus)
        director.reset()
        
        assert director.tick_count == 0
        assert len(director.event_log) == 0


# ============================================================
# Default Component tests
# ============================================================

class TestDefaultComponents:
    """Tests for default fallback components."""

    def test_default_arc_manager(self):
        """Test DefaultArcManager returns empty list."""
        manager = DefaultArcManager()
        assert manager.update({}) == []

    def test_default_plot_engine(self):
        """Test DefaultPlotEngine returns default beat."""
        engine = DefaultPlotEngine()
        beat = engine.select([], {})
        assert beat["type"] == "default_beat"

    def test_default_scene_engine(self):
        """Test DefaultSceneEngine returns scene data."""
        engine = DefaultSceneEngine()
        scene = engine.generate({"type": "test"})
        assert "narrative" in scene
        assert "scene_data" in scene


# ============================================================
# GameEngine tests
# ============================================================

class TestGameEngine:
    """Tests for the GameEngine."""

    def test_handle_input(self):
        """Test that handle_input processes input correctly."""
        intent_parser = Mock(spec=IntentParser)
        intent_parser.parse.return_value = {"action": "look"}
        
        scene_renderer = Mock(spec=SceneRenderer)
        scene_renderer.render.return_value = {"scene": "result"}

        engine = GameEngine(
            intent_parser=intent_parser,
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            story_director=Mock(spec=StoryDirector),
            scene_renderer=scene_renderer,
        )

        result = engine.handle_input("look around")
        
        assert result["scene"] == "result"
        assert "coherence" not in result

    def test_event_bus_is_shared(self):
        """Test that engine creates and shares EventBus."""
        engine = GameEngine()
        assert engine.event_bus is not None
        assert engine.game_loop.event_bus is engine.event_bus

    def test_custom_event_bus(self):
        """Test that custom EventBus is used."""
        custom_bus = EventBus()
        engine = GameEngine(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            story_director=Mock(spec=StoryDirector),
            scene_renderer=Mock(spec=SceneRenderer),
            event_bus=custom_bus,
        )
        assert engine.event_bus is custom_bus
        assert engine.game_loop.event_bus is custom_bus

    def test_tick_count_delegate(self):
        """Test tick_count delegates to loop."""
        engine = GameEngine(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            story_director=Mock(spec=StoryDirector),
            scene_renderer=Mock(spec=SceneRenderer),
        )
        assert engine.tick_count == 0
        engine.handle_input("test")
        assert engine.tick_count == 1

    def test_reset(self):
        """Test that reset clears engine state."""
        engine = GameEngine(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            story_director=Mock(spec=StoryDirector),
            scene_renderer=Mock(spec=SceneRenderer),
        )
        engine.handle_input("test")
        engine.event_bus.emit(Event("test"))
        engine.reset()
        
        assert engine.tick_count == 0
        assert engine.event_bus.pending_count == 0

    def test_callback_delegation(self):
        """Test callbacks are delegated to GameLoop."""
        engine = GameEngine(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            story_director=Mock(spec=StoryDirector),
            scene_renderer=Mock(spec=SceneRenderer),
        )
        
        pre_called = []
        post_called = []
        
        engine.on_pre_tick(lambda ctx: pre_called.append(ctx.tick_number))
        engine.on_post_tick(lambda ctx: post_called.append(ctx.tick_number))
        
        engine.handle_input("test")
        
        assert pre_called == [1]
        assert post_called == [1]


# ============================================================
# Integration (Unit Level) tests
# ============================================================

class TestPhase1Integration:
    """Integration tests at the unit level."""

    def test_full_pipeline_flow(self):
        """Test the full pipeline from input to output."""
        event_bus = EventBus()
        
        intent_parser = Mock(spec=IntentParser)
        intent_parser.parse.return_value = {"action": "explore", "target": "forest"}
        
        world = Mock(spec=WorldSystem)
        
        npc_system = Mock(spec=NPCSystem)
        
        story_director = Mock(spec=StoryDirector)
        story_director.process.return_value = {
            "narrative": "You venture into the forest",
            "mood": "mysterious",
        }
        
        scene_renderer = Mock(spec=SceneRenderer)
        scene_renderer.render.return_value = {
            "description": "A dark forest stretches before you",
            "options": ["Go deeper", "Turn back"],
        }

        engine = GameEngine(
            intent_parser=intent_parser,
            world=world,
            npc_system=npc_system,
            event_bus=event_bus,
            story_director=story_director,
            scene_renderer=scene_renderer,
        )

        result = engine.handle_input("explore the forest")

        # Verify full pipeline executed
        intent_parser.parse.assert_called_once_with("explore the forest")
        world.tick.assert_called_once()
        npc_system.update.assert_called_once()
        call_args = npc_system.update.call_args
        assert call_args[0][0] == {"action": "explore", "target": "forest"}
        assert "description" in result
        assert "options" in result

    def test_event_bus_decoupling(self):
        """Test that systems communicate via events, not direct calls."""
        event_bus = EventBus()
        
        # NPC system emits events instead of calling world directly
        npc_system = Mock(spec=NPCSystem)
        npc_system.update = lambda intent, eb: event_bus.emit(
            Event("npc_moved", {"npc_id": 1, "position": (5, 5)})
        )
        
        story_director = Mock(spec=StoryDirector)
        story_director.process.return_value = {}

        loop = GameLoop(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=npc_system,
            event_bus=event_bus,
            story_director=story_director,
            scene_renderer=Mock(spec=SceneRenderer),
        )
        
        loop.tick("test")
        
        # Verify event was collected and passed to director
        call_args = story_director.process.call_args
        events_passed = call_args[0][0]
        assert len(events_passed) == 1
        assert events_passed[0].type == "npc_moved"

    def test_deterministic_execution(self):
        """Test that execution order is deterministic."""
        execution_order = []
        
        def track_world_tick(event_bus):
            execution_order.append("world")
        
        def track_npc_update(intent, event_bus):
            execution_order.append("npc")
        
        world = Mock(spec=WorldSystem)
        world.tick.side_effect = track_world_tick
        
        npc_system = Mock(spec=NPCSystem)
        npc_system.update.side_effect = track_npc_update
        
        loop = GameLoop(
            intent_parser=Mock(spec=IntentParser),
            world=world,
            npc_system=npc_system,
            event_bus=EventBus(),
            story_director=Mock(spec=StoryDirector),
            scene_renderer=Mock(spec=SceneRenderer),
        )
        
        loop.tick("test")
        
        # Verify execution order matches spec
        assert execution_order == ["world", "npc"]

    def test_multiple_ticks_dont_interfere(self):
        """Test that multiple ticks maintain isolation."""
        event_bus = EventBus()
        
        loop = GameLoop(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            event_bus=event_bus,
            story_director=Mock(spec=StoryDirector),
            scene_renderer=Mock(spec=SceneRenderer),
        )
        
        # First tick
        event_bus.emit(Event("tick1_event"))
        loop.tick("first")
        
        # Second tick should have empty event queue
        loop.tick("second")
        
        # Director should only receive events from current tick
        call_args = loop.story_director.process.call_args
        events_passed = call_args[0][0]
        assert len(events_passed) == 0  # No events emitted during second tick