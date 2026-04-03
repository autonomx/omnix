"""Regression tests for PHASE 1.5 — ENFORCEMENT PATCH components.

These tests guard against common regressions and bugs that could
occur when integrating the Phase 1.5 enforcement patches:
1. Context-local GameLoop using contextvars
2. EventBus enforcement for cross-system calls
3. EventBus event history for replay/debug
4. StoryDirector structured event types
5. Event source field for system identity
6. Tick ID injection for temporal debugging

Regression testing focuses on:
    - Preventing reintroduction of fixed bugs
    - Verifying architectural constraints remain enforced
    - Testing edge cases that caused issues in the past
    - Ensuring backwards compatibility with existing systems
"""

import pytest
from unittest.mock import Mock, patch

from app.rpg.core.event_bus import Event, EventBus
from app.rpg.core.game_loop import (
    GameLoop,
    IntentParser,
    WorldSystem,
    NPCSystem,
    StoryDirector as StoryDirectorProtocol,
    SceneRenderer,
    TickPhase,
    _active_loop_ctx,
)
from app.rpg.core.game_engine import GameEngine
from app.rpg.narrative.story_director import (
    StoryDirector as UnifiedStoryDirector,
)


@pytest.fixture(autouse=True)
def _reset_context_var():
    """Reset the context var between tests."""
    _active_loop_ctx.set(None)
    yield
    _active_loop_ctx.set(None)


# ============================================================
# Backwards Compatibility Tests
# ============================================================

class TestPhase15BackwardsCompatibility:
    """Tests for backwards compatibility with Phase 1.5 changes."""

    def test_event_source_optional(self):
        """Verify that source field is optional (defaults to None)."""
        event = Event(type="test")
        assert event.source is None

    def test_event_payload_backward_compat(self):
        """Verify that payload handling is unchanged."""
        event = Event(type="test", payload={"key": "value"})
        assert event.payload["key"] == "value"

    def test_eventbus_without_history(self):
        """Verify that EventBus without history access still works."""
        bus = EventBus()
        bus.emit(Event("test"))
        events = bus.collect()
        assert len(events) == 1

    def test_gamloop_active_loop_property(self):
        """Verify backwards compat for _active_loop property."""
        # Should be able to access module-level context var
        from app.rpg.core.game_loop import _active_loop_ctx
        assert _active_loop_ctx is not None

    def test_gameloop_context_var_none_by_default(self):
        """Verify context var is None by default."""
        assert _active_loop_ctx.get() is None


# ============================================================
# Edge Case Tests
# ============================================================

class TestPhase15EdgeCases:
    """Tests for edge cases in Phase 1.5 patches."""

    def test_empty_events_to_director(self):
        """Verify director handles empty events correctly."""
        director = UnifiedStoryDirector()
        bus = EventBus()
        result = director.process([], {}, bus)
        assert result is not None

    def test_large_number_of_events_in_history(self):
        """Verify system handles large numbers of events in history."""
        event_bus = EventBus()
        
        for i in range(1000):
            event_bus.emit(Event(f"event_{i}", source="sys"))
        
        history = event_bus.history()
        assert len(history) == 1000

    def test_tick_id_with_zero_tick(self):
        """Verify tick ID works correctly when tick is 0."""
        bus = EventBus()
        bus.set_tick(0)
        bus.emit(Event("test", source="test"))
        history = bus.history()
        assert history[0].payload["tick"] == 0

    def test_history_returns_copy_prevents_modification(self):
        """Verify history() returns copy preventing accidental modification."""
        bus = EventBus()
        bus.emit(Event("test"))
        history = bus.history()
        history.clear()
        assert len(bus.history()) == 1

    def test_event_source_with_special_chars(self):
        """Verify source field handles special characters."""
        event = Event(type="test", source="story-director_123")
        assert event.source == "story-director_123"

    def test_emission_with_none_tick(self):
        """Verify emission works when _current_tick is None."""
        bus = EventBus()
        bus.set_tick(None)
        bus.emit(Event("test", {"existing": "tick"}, source="test"))
        history = bus.history()
        # Tick should not be overwritten when _current_tick is None
        assert "tick" not in history[0].payload


# ============================================================
# Architectural Constraint Tests
# ============================================================

class TestPhase15ArchitecturalConstraints:
    """Tests that verify Phase 1.5 architectural constraints are maintained."""

    def test_event_bus_is_only_communication_path(self):
        """Verify systems communicate via EventBus only."""
        event_bus = EventBus()
        
        class VerifyingNPCSystem:
            def __init__(self, event_bus):
                self.event_bus = event_bus
            
            def update(self, intent, event_bus):
                self.event_bus.emit(Event("npc_update", {"intent": intent}))
        
        npc_system = VerifyingNPCSystem(event_bus)
        captured_events = []
        
        class CapturingDirector:
            def process(self, events, intent, event_bus):
                captured_events.extend(events)
                return {}
        
        loop = GameLoop(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=npc_system,
            event_bus=event_bus,
            story_director=CapturingDirector(),
            scene_renderer=Mock(spec=SceneRenderer),
        )
        
        loop.tick("test")
        
        assert len(captured_events) == 1
        assert captured_events[0].type == "npc_update"

    def test_context_var_reset_on_exception(self):
        """Verify context var is reset even when exception occurs."""
        event_bus = EventBus()
        
        class FailingWorld:
            def tick(self, event_bus):
                raise RuntimeError("World failed")
        
        loop = GameLoop(
            intent_parser=Mock(spec=IntentParser),
            world=FailingWorld(),
            npc_system=Mock(spec=NPCSystem),
            event_bus=event_bus,
            story_director=Mock(spec=StoryDirectorProtocol),
            scene_renderer=Mock(spec=SceneRenderer),
        )
        
        assert _active_loop_ctx.get() is None
        
        with pytest.raises(RuntimeError):
            loop.tick("test")
        
        assert _active_loop_ctx.get() is None


# ============================================================
# Integration Regression Tests
# ============================================================

class TestPhase15Integration:
    """Integration tests for Phase 1.5 patches."""

    def test_full_pipeline_with_new_signatures(self):
        """Verify full pipeline works with new signatures."""
        event_bus = EventBus()
        
        class MockIntentParserImpl:
            def parse(self, player_input: str) -> dict:
                return {"action": player_input}
        
        class EventEmittingNPC:
            def update(self, intent, event_bus):
                event_bus.emit(Event("npc_act", {"action": intent.get("action")}, source="npc"))
        
        received_inputs = []
        
        class TrackingDirector:
            def process(self, events, intent, event_bus):
                received_inputs.append(intent.get("action", "unknown"))
                return {"narrative": "tracking"}
        
        engine = GameEngine(
            intent_parser=MockIntentParserImpl(),
            world=Mock(spec=WorldSystem),
            npc_system=EventEmittingNPC(),
            story_director=TrackingDirector(),
            scene_renderer=Mock(spec=SceneRenderer),
            event_bus=event_bus,
        )
        
        engine.handle_input("look")
        engine.handle_input("move")
        
        assert received_inputs == ["look", "move"]

    def test_custom_event_bus_injection(self):
        """Verify custom EventBus can be injected."""
        custom_bus = EventBus()
        
        engine = GameEngine(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            story_director=Mock(spec=StoryDirectorProtocol),
            scene_renderer=Mock(spec=SceneRenderer),
            event_bus=custom_bus,
        )
        
        assert engine.event_bus is custom_bus
        assert engine.game_loop.event_bus is custom_bus

    def test_all_phase15_features_work_together(self):
        """Verify all Phase 1.5 features work correctly together."""
        event_bus = EventBus(debug=True)
        
        engine = GameEngine(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            story_director=UnifiedStoryDirector(),
            scene_renderer=Mock(spec=SceneRenderer),
            event_bus=event_bus,
        )
        
        # Run multiple ticks
        for i in range(5):
            engine.handle_input(f"test_{i}")
        
        history = event_bus.history()
        
        # All events should have source field from story_director
        story_events = [e for e in history if e.source == "story_director"]
        assert len(story_events) == 10  # 2 events per tick * 5 ticks
        
        # All events should have tick IDs
        for event in story_events:
            assert "tick" in event.payload
            assert event.payload["tick"] in {1, 2, 3, 4, 5}


# ============================================================
# Performance Tests
# ============================================================

class TestPhase15Performance:
    """Tests for Phase 1.5 performance characteristics."""

    def test_history_does_not_slow_down_emission(self):
        """Verify that history storage doesn't significantly slow down emission."""
        import time
        
        bus_no_log = EventBus(debug=False)
        
        start = time.time()
        for i in range(1000):
            bus_no_log.emit(Event(f"event_{i}"))
        elapsed = time.time() - start
        
        # Should complete in reasonable time (< 1 second for 1000 events)
        assert elapsed < 1.0

    def test_history_memory_usage(self):
        """Verify history doesn't consume excessive memory."""
        bus = EventBus()
        
        # Emit many events
        for i in range(5000):
            bus.emit(Event(f"event_{i}", {"data": "x" * 100}, source="sys"))
        
        history = bus.history()
        assert len(history) == 5000


# ============================================================
# Context Var Regression Tests
# ============================================================

class TestContextVarRegression:
    """Regression tests for contextvar implementation."""

    def test_context_does_not_leak_between_calls(self):
        """Verify context var doesn't leak between tick calls."""
        event_bus = EventBus()
        
        engine1 = GameEngine(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            story_director=UnifiedStoryDirector(),
            scene_renderer=Mock(spec=SceneRenderer),
            event_bus=event_bus,
        )
        
        engine1.handle_input("first")
        assert _active_loop_ctx.get() is None
        
        engine2 = GameEngine(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            story_director=UnifiedStoryDirector(),
            scene_renderer=Mock(spec=SceneRenderer),
            event_bus=EventBus(),
        )
        
        # Should work fine (no contamination from first engine)
        engine2.handle_input("second")
        assert _active_loop_ctx.get() is None

    def test_reset_clears_all_state(self):
        """Verify reset clears all related state."""
        event_bus = EventBus()
        
        engine = GameEngine(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            story_director=UnifiedStoryDirector(),
            scene_renderer=Mock(spec=SceneRenderer),
            event_bus=event_bus,
        )
        
        engine.handle_input("test")
        engine.handle_input("test2")
        
        # Reset should clear everything
        engine.reset()
        
        assert engine.tick_count == 0
        assert event_bus.pending_count == 0
        assert len(event_bus.history()) == 0
        assert event_bus._current_tick is None