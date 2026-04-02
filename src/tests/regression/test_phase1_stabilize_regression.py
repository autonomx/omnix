"""Regression tests for PHASE 1.5 — ENFORCEMENT PATCH components.

These tests guard against common regressions and bugs that could
occur when integrating the Phase 1.5 enforcement patches:
- Event bus enforcement (enforce flag)
- Single loop authority enforcement
- StoryDirector event emission
- Deprecated module blocking

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
    StoryDirector,
    SceneRenderer,
    TickPhase,
)
from app.rpg.core.game_engine import GameEngine
from app.rpg.narrative.story_director import (
    StoryDirector as UnifiedStoryDirector,
)


@pytest.fixture(autouse=True)
def _reset_single_loop_guard():
    """Reset the GameLoop single-loop guard between tests."""
    GameLoop._active_loop = None
    yield
    GameLoop._active_loop = None


# ============================================================
# Phase 1.5 — Architectural Constraint Tests
# ============================================================

class TestPhase15ArchitecturalConstraints:
    """Tests that verify Phase 1.5 architectural constraints are maintained."""

    def test_event_bus_is_only_communication_path(self):
        """Verify systems communicate via EventBus only."""
        event_bus = EventBus()
        
        class VerifyingNPCSystem:
            """NPC system that ONLY communicates via EventBus."""
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

    def test_world_tick_receives_event_bus(self):
        """Verify world.tick() receives event_bus parameter."""
        event_bus = EventBus()
        tick_calls = []
        
        class TrackedWorld:
            def tick(self, event_bus):
                tick_calls.append(("world", event_bus))
        
        world = TrackedWorld()
        
        engine = GameEngine(
            intent_parser=Mock(spec=IntentParser),
            world=world,
            npc_system=Mock(spec=NPCSystem),
            story_director=Mock(spec=StoryDirector),
            scene_renderer=Mock(spec=SceneRenderer),
            event_bus=event_bus,
        )
        
        engine.handle_input("test")
        
        assert len(tick_calls) == 1
        assert tick_calls[0][1] is event_bus

    def test_npc_update_receives_event_bus(self):
        """Verify npc_system.update() receives event_bus parameter."""
        event_bus = EventBus()
        update_calls = []
        
        class TrackedNPCSystem:
            def update(self, intent, event_bus):
                update_calls.append(("npc", event_bus))
        
        npc_system = TrackedNPCSystem()
        
        engine = GameEngine(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=npc_system,
            story_director=Mock(spec=StoryDirector),
            scene_renderer=Mock(spec=SceneRenderer),
            event_bus=event_bus,
        )
        
        engine.handle_input("test")
        
        assert len(update_calls) == 1
        assert update_calls[0][1] is event_bus

    def test_story_director_process_receives_event_bus(self):
        """Verify story_director.process() receives event_bus parameter."""
        event_bus = EventBus()
        process_calls = []
        
        class TrackedDirector:
            def process(self, events, intent, event_bus):
                process_calls.append(("director", event_bus))
                return {}
        
        director = TrackedDirector()
        
        engine = GameEngine(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            story_director=director,
            scene_renderer=Mock(spec=SceneRenderer),
            event_bus=event_bus,
        )
        
        engine.handle_input("test")
        
        assert len(process_calls) == 1
        assert process_calls[0][1] is event_bus


# ============================================================
# Phase 1.5 — StoryDirector Event Emission (PATCH 2)
# ============================================================

class TestPhase15StoryDirectorEvents:
    """Tests for PATCH 2: StoryDirector emits scene_generated event."""

    def test_story_director_emits_scene_generated(self):
        """Verify StoryDirector emits scene_generated event on process."""
        event_bus = EventBus(debug=True)
        director = UnifiedStoryDirector()
        
        director.process([], {}, event_bus)
        
        log = event_bus.log
        scene_events = [e for e in log if e.type == "scene_generated"]
        assert len(scene_events) == 1
        assert "tick" in scene_events[0].payload
        assert "beat" in scene_events[0].payload

    def test_story_director_emits_after_processing(self):
        """Verify event is emitted after narrative processing."""
        event_bus = EventBus(debug=True)
        director = UnifiedStoryDirector()
        
        npc_event = Event("npc_move", {"position": (1, 2)})
        event_bus.emit(npc_event)  # npc_event must be in event_bus
        director.process([], {"action": "look"}, event_bus)
        
        log = event_bus.log
        event_types = [e.type for e in log]
        assert "npc_move" in event_types
        assert "scene_generated" in event_types


# ============================================================
# Phase 1.5 — Single Loop Enforcement (PATCH 3)
# ============================================================

class TestPhase15SingleLoopEnforcement:
    """Tests for PATCH 3: Single loop enforcement."""

    def test_single_loop_allows_one_instance(self):
        """Verify single loop allows one instance."""
        engine = GameEngine(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            story_director=Mock(spec=StoryDirector),
            scene_renderer=Mock(spec=SceneRenderer),
        )
        
        # Should work fine
        result = engine.handle_input("test")
        assert result is not None

    def test_multiple_loop_instances_detected(self):
        """Verify multiple loop instances are detected."""
        engine1 = GameEngine(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            story_director=Mock(spec=StoryDirector),
            scene_renderer=Mock(spec=SceneRenderer),
        )
        engine2 = GameEngine(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            story_director=Mock(spec=StoryDirector),
            scene_renderer=Mock(spec=SceneRenderer),
        )
        
        engine1.handle_input("first")
        
        with pytest.raises(RuntimeError, match="Multiple GameLoop instances"):
            engine2.handle_input("second")

    def test_loop_reset_clears_guard(self):
        """Verify loop reset allows reuse."""
        engine = GameEngine(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            story_director=Mock(spec=StoryDirector),
            scene_renderer=Mock(spec=SceneRenderer),
        )
        
        engine.handle_input("first")
        GameLoop._active_loop = None  # Simulate reset
        
        # Should work again
        engine.handle_input("second")


# ============================================================
# Phase 1.5 — TickPhase Tests (PATCH 6)
# ============================================================

class TestTickPhaseEnumeration:
    """Tests for PATCH 6: TickPhase enumeration."""

    def test_tick_phase_values(self):
        """Verify TickPhase has expected values."""
        assert TickPhase.PRE_WORLD.value == "pre_world"
        assert TickPhase.POST_WORLD.value == "post_world"
        assert TickPhase.PRE_NPC.value == "pre_npc"
        assert TickPhase.POST_NPC.value == "post_npc"

    def test_tick_phase_from_core(self):
        """Verify TickPhase can be imported from core."""
        from app.rpg.core import TickPhase as CoreTickPhase
        assert CoreTickPhase.PRE_WORLD.value == "pre_world"


# ============================================================
# Edge Case Tests
# ============================================================

class TestPhase15EdgeCases:
    """Tests for edge cases in Phase 1.5 patches."""

    def test_empty_events_to_director_with_event_bus(self):
        """Verify director handles empty events with event_bus."""
        director = UnifiedStoryDirector()
        bus = EventBus()
        result = director.process([], {}, bus)
        assert result is not None

    def test_large_number_of_events(self):
        """Verify system handles large numbers of events."""
        event_bus = EventBus()
        
        for i in range(1000):
            event_bus.emit(Event(f"event_{i}"))
        
        engine = GameEngine(
            intent_parser=Mock(spec=IntentParser),
            world=Mock(spec=WorldSystem),
            npc_system=Mock(spec=NPCSystem),
            story_director=Mock(spec=StoryDirector),
            scene_renderer=Mock(spec=SceneRenderer),
            event_bus=event_bus,
        )
        
        result = engine.handle_input("test")
        assert result is not None

    def test_event_bus_enforce_flag(self):
        """Verify enforce flag doesn't break normal operation."""
        bus = EventBus(enforce=True)
        bus.emit(Event("test", {}))
        assert bus.pending_count == 1

    def test_director_emits_event_even_with_no_events(self):
        """Verify director emits scene_generated even with no input events."""
        event_bus = EventBus(debug=True)
        director = UnifiedStoryDirector()
        
        director.process([], {}, event_bus)
        
        events = event_bus.collect()
        assert any(e.type == "scene_generated" for e in events)


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
                event_bus.emit(Event("npc_act", {"action": intent.get("action")}))
        
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
            story_director=Mock(spec=StoryDirector),
            scene_renderer=Mock(spec=SceneRenderer),
            event_bus=custom_bus,
        )
        
        assert engine.event_bus is custom_bus
        assert engine.game_loop.event_bus is custom_bus


# ============================================================
# Backwards Compatibility Tests
# ============================================================

class TestPhase15BackwardsCompatibility:
    """Tests for backwards compatibility with Phase 1.5 changes."""

    def test_deprecated_event_bus_raises_error(self):
        """Verify deprecated event_bus module raises RuntimeError."""
        with pytest.raises(RuntimeError, match="DEPRECATED"):
            import app.rpg.event_bus

    def test_deprecated_director_raises_error(self):
        """Verify deprecated director module raises RuntimeError."""
        with pytest.raises(RuntimeError, match="DEPRECATED"):
            import app.rpg.director.director

    def test_core_module_exports_new_components(self):
        """Verify core module exports new components."""
        from app.rpg.core import Event, EventBus, GameLoop, GameEngine, TickPhase
        assert callable(Event)
        assert callable(EventBus)
        assert callable(GameLoop)
        assert callable(GameEngine)
        assert callable(TickPhase)