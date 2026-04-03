"""Functional tests for PHASE 1.5 — ENFORCEMENT PATCH components.

Tests the complete game flow from an end-user perspective,
verifying that all Phase 1.5 features work together correctly:
1. Context-local GameLoop using contextvars
2. EventBus enforcement for cross-system calls
3. EventBus event history for replay/debug
4. StoryDirector structured event types
5. Event source field for system identity
6. Tick ID injection for temporal debugging

Functional testing focuses on:
    - End-to-end game flow with Phase 1.5 features
    - System behavior under realistic scenarios
    - Event-driven architecture correctness
    - Observability and debugging capabilities
"""

import pytest
from unittest.mock import Mock, MagicMock

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
# Mock Implementations for Functional Testing
# ============================================================

class MockIntentParser:
    """Mock intent parser that returns structured intents."""
    
    def parse(self, player_input: str) -> dict:
        parts = player_input.lower().split()
        if parts:
            action = parts[0]
            target = " ".join(parts[1:]) if len(parts) > 1 else ""
            return {"action": action, "target": target}
        return {"action": "idle", "target": ""}


class MockWorld:
    """Mock world that emits events."""
    
    def __init__(self):
        self.tick_count = 0
        self.state = {"weather": "clear", "time": "day"}
    
    def tick(self, event_bus):
        self.tick_count += 1
        event_bus.emit(Event(
            "world_ticked",
            {
                "tick": self.tick_count,
                "state": self.state.copy(),
            },
            source="world"
        ))


class MockNPCSystem:
    """Mock NPC system that emits events on update."""
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.npcs_updated = 0
    
    def update(self, intent: dict, event_bus: EventBus):
        self.npcs_updated += 1
        event_bus.emit(Event(
            "npc_update",
            {
                "npcs_acted": 2,
                "intent": intent.get("action", "unknown"),
            },
            source="npc_system"
        ))


class MockSceneRenderer:
    """Mock scene renderer."""
    
    def render(self, narrative: dict) -> dict:
        return {
            "description": narrative.get("narrative", ""),
            "mood": narrative.get("mood", "neutral"),
            "ready": True,
        }


# ============================================================
# Event History Functional Tests
# ============================================================

class TestEventHistoryFunctional:
    """Tests for event history functionality in real scenarios."""

    def test_replay_capability(self):
        """Test that history enables event replay for debugging."""
        event_bus = EventBus(debug=True)
        
        class TwoEventNPC:
            def __init__(self, event_bus):
                self.event_bus = event_bus
            def update(self, intent, event_bus):
                event_bus.emit(Event("npc_think", {"thought": "thinking"}, source="npc"))
                event_bus.emit(Event("npc_act", {"action": "move"}, source="npc"))
        
        npc = TwoEventNPC(event_bus)
        story_director = UnifiedStoryDirector()
        
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=npc,
            story_director=story_director,
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        # Run multiple ticks
        engine.handle_input("explore")
        engine.handle_input("talk")
        
        # History should contain events from all ticks
        history = event_bus.history()
        assert len(history) > 0
        
        # Should be able to filter by source (2 ticks * 2 events = 4 npc events)
        npc_events = [e for e in history if e.source == "npc"]
        assert len(npc_events) == 4  # 2 ticks * 2 events per tick
        # Check first tick events
        tick1_events = [e for e in npc_events if e.payload.get("tick") == 1]
        assert len(tick1_events) == 2
        assert tick1_events[0].payload["thought"] == "thinking"
        assert tick1_events[1].payload["action"] == "move"

    def test_event_causality_tracking(self):
        """Test that history tracks event causality."""
        event_bus = EventBus(debug=True)
        director = UnifiedStoryDirector()
        
        class NPCWithEvents:
            def update(self, intent, event_bus):
                event_bus.emit(Event("npc_update", {"actor": "hero"}, source="npc"))
        
        npc = NPCWithEvents()
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=npc,
            story_director=director,
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        engine.handle_input("explore")
        
        history = event_bus.history()
        # Should see the causal chain: npc_update -> narrative_beat -> scene_generated
        types = [e.type for e in history]
        assert "npc_update" in types
        assert "narrative_beat_selected" in types
        assert "scene_generated" in types


# ============================================================
# Tick ID Functional Tests
# ============================================================

class TestTickIDFunctional:
    """Tests for tick ID injection in production scenarios."""

    def test_tick_id_tracks_timeline(self):
        """Test that tick IDs create a clear timeline."""
        event_bus = EventBus(debug=True)
        director = UnifiedStoryDirector()
        world = MockWorld()
        
        class NPCWithTickTracking:
            def update(self, intent, event_bus):
                event_bus.emit(Event("npc_action", source="npc"))
        
        npc = NPCWithTickTracking()
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=world,
            npc_system=npc,
            story_director=director,
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        # Run multiple ticks
        engine.handle_input("first")
        engine.handle_input("second")
        engine.handle_input("third")
        
        history = event_bus.history()
        
        # Group events by tick
        ticks_seen = set()
        for e in history:
            if "tick" in e.payload:
                ticks_seen.add(e.payload["tick"])
        
        assert ticks_seen == {1, 2, 3}  # 3 ticks

    def test_tick_id_enables_debug_filtering(self):
        """Test that tick IDs enable filtering events by time."""
        event_bus = EventBus(debug=True)
        director = UnifiedStoryDirector()
        
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=MockNPCSystem(event_bus),
            story_director=director,
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        engine.handle_input("tick1")
        engine.handle_input("tick2")
        
        history = event_bus.history()
        
        # Filter events for tick 1
        tick1_events = [e for e in history if e.payload.get("tick") == 1]
        tick2_events = [e for e in history if e.payload.get("tick") == 2]
        
        assert len(tick1_events) > 0
        assert len(tick2_events) > 0


# ============================================================
# Context-Local Loop Functional Tests
# ============================================================

class TestContextLocalLoop:
    """Tests for contextvars-based loop safety."""

    def test_loop_resets_context_after_tick(self):
        """Test that loop always resets context var after tick."""
        event_bus = EventBus()
        director = UnifiedStoryDirector()
        
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=MockNPCSystem(event_bus),
            story_director=director,
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        # Context should be None before
        assert _active_loop_ctx.get() is None
        
        engine.handle_input("test")
        
        # Context should be None after (cleanup worked)
        assert _active_loop_ctx.get() is None

    def test_loop_handles_exceptions_gracefully(self):
        """Test that context is reset even if tick fails."""
        event_bus = EventBus()
        
        class FailingWorld:
            def tick(self, event_bus):
                raise ValueError("World error")
        
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=FailingWorld(),
            npc_system=MockNPCSystem(event_bus),
            story_director=UnifiedStoryDirector(),
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        # Context should be None before
        assert _active_loop_ctx.get() is None
        
        with pytest.raises(ValueError):
            engine.handle_input("test")
        
        # Context should still be None after exception (finally worked)
        assert _active_loop_ctx.get() is None


# ============================================================
# Structured Event Types Functional Tests
# ============================================================

class TestStructuredEventsFunctional:
    """Tests for structured event types in production."""

    def test_narrative_beat_tracking(self):
        """Test that narrative_beat_selected events track story progression."""
        event_bus = EventBus(debug=True)
        director = UnifiedStoryDirector()
        
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=MockNPCSystem(event_bus),
            story_director=director,
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        engine.handle_input("explore")
        engine.handle_input("fight")
        
        history = event_bus.history()
        beat_events = [e for e in history if e.type == "narrative_beat_selected"]
        
        assert len(beat_events) == 2
        for beat in beat_events:
            assert beat.source == "story_director"
            assert "beat" in beat.payload
            assert "tick" in beat.payload

    def test_scene_generated_for_debugging(self):
        """Test that scene_generated events include full debug context."""
        event_bus = EventBus(debug=True)
        director = UnifiedStoryDirector()
        
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=MockNPCSystem(event_bus),
            story_director=director,
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        engine.handle_input("look")
        
        history = event_bus.history()
        scene_events = [e for e in history if e.type == "scene_generated"]
        
        assert len(scene_events) == 1
        scene_event = scene_events[0]
        
        # Should have full context
        assert scene_event.source == "story_director"
        assert scene_event.payload["tick"] == 1
        assert "beat" in scene_event.payload
        assert "scene" in scene_event.payload


# ============================================================
# Source Identity Functional Tests
# ============================================================

class TestSourceIdentityFunctional:
    """Tests for system identity tracking."""

    def test_source_identifies_event_origin(self):
        """Test that source field identifies where events came from."""
        event_bus = EventBus(debug=True)
        world = MockWorld()
        
        class SourceTrackingNPC:
            def update(self, intent, event_bus):
                event_bus.emit(Event("npc_action", source="npc_system"))
        
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=world,
            npc_system=SourceTrackingNPC(),
            story_director=UnifiedStoryDirector(),
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        engine.handle_input("test")
        
        history = event_bus.history()
        
        # Check different sources
        sources = set(e.source for e in history if e.source)
        assert "npc_system" in sources
        assert "story_director" in sources
        assert "world" in sources

    def test_source_enables_event_filtering(self):
        """Test that source allows filtering events by origin."""
        event_bus = EventBus(debug=True)
        
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=MockNPCSystem(event_bus),
            story_director=UnifiedStoryDirector(),
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        engine.handle_input("test")
        
        history = event_bus.history()
        
        # Filter by source
        director_events = [e for e in history if e.source == "story_director"]
        world_events = [e for e in history if e.source == "world"]
        npc_events = [e for e in history if e.source == "npc_system"]
        
        assert len(director_events) == 2  # narrative_beat + scene_generated
        assert len(world_events) == 1
        assert len(npc_events) == 1


# ============================================================
# Full Pipeline Integration Functional Tests
# ============================================================

class TestPhase15FullPipeline:
    """Full pipeline tests integrating all Phase 1.5 features."""

    def test_complete_pipeline_with_all_features(self):
        """Test complete game loop with all Phase 1.5 features active."""
        event_bus = EventBus(debug=True)
        director = UnifiedStoryDirector()
        world = MockWorld()
        npc = MockNPCSystem(event_bus)
        
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=world,
            npc_system=npc,
            story_director=director,
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        # Run multiple ticks
        for i in range(3):
            result = engine.handle_input(f"action_{i}")
            assert result["ready"] is True
        
        history = event_bus.history()
        
        # Verify history is complete
        assert len(history) > 0
        
        # Verify tick IDs are sequential
        ticks_in_history = set()
        for e in history:
            if "tick" in e.payload:
                ticks_in_history.add(e.payload["tick"])
        assert len(ticks_in_history) == 3
        
        # Verify all sources are present
        sources = set(e.source for e in history if e.source)
        assert "world" in sources
        assert "npc_system" in sources
        assert "story_director" in sources
        
        # Verify structured events
        beat_events = [e for e in history if e.type == "narrative_beat_selected"]
        scene_events = [e for e in history if e.type == "scene_generated"]
        assert len(beat_events) == 3
        assert len(scene_events) == 3

    def test_observability_is_high(self):
        """Test that all debugging/observability features work together."""
        event_bus = EventBus(debug=True)
        director = UnifiedStoryDirector()
        
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=MockNPCSystem(event_bus),
            story_director=director,
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        engine.handle_input("observe")
        
        history = event_bus.history()
        
        # Each event should have: type, payload with tick, and source
        for event in history:
            assert event.type is not None
            if event.source == "story_director":
                assert "tick" in event.payload
            assert event.source is not None
        
        # Can reconstruct what happened by filtering
        by_source = {}
        for event in history:
            source = event.source or "unknown"
            if source not in by_source:
                by_source[source] = []
            by_source[source].append(event)
        
        # Verify each system's events are isolated
        assert "story_director" in by_source
        assert "world" in by_source
        assert "npc_system" in by_source

    def test_rapid_succession_with_phase15(self):
        """Test rapid execution maintains event integrity."""
        event_bus = EventBus(debug=True)
        
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=MockNPCSystem(event_bus),
            story_director=UnifiedStoryDirector(),
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        for i in range(50):
            result = engine.handle_input(f"action_{i}")
            assert result["ready"] is True
        
        history = event_bus.history()
        
        # All 50 ticks should have proper events
        ticks_seen = set()
        for e in history:
            if "tick" in e.payload:
                ticks_seen.add(e.payload["tick"])
        
        # Should have 50 different ticks
        assert len(ticks_seen) == 50