"""Functional tests for PHASE 1 — STABILIZE components (Phase 1.5 enforcement).

Tests the complete game flow from an end-user perspective,
verifying that the single game loop, event bus, and story director
work together as specified in rpg-design.txt.

Functional testing focuses on:
    - End-to-end game flow
    - System behavior under realistic scenarios
    - Event-driven architecture correctness
    - Single authority enforcement
"""

import pytest
from unittest.mock import Mock, MagicMock

from app.rpg.core.event_bus import Event, EventBus
from app.rpg.core.game_loop import (
    GameLoop,
    IntentParser,
    WorldSystem,
    NPCSystem,
    StoryDirector,
    SceneRenderer,
    TickContext,
    TickPhase,
)
from app.rpg.core.game_engine import GameEngine


@pytest.fixture(autouse=True)
def _reset_single_loop_guard():
    """Reset the GameLoop single-loop guard between tests."""
    GameLoop._active_loop = None
    yield
    GameLoop._active_loop = None


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
    """Mock world that tracks state changes."""
    
    def __init__(self):
        self.tick_count = 0
        self.state = {"weather": "clear", "time": "day"}
    
    def tick(self, event_bus):
        self.tick_count += 1


class MockNPCSystem:
    """Mock NPC system that emits events on update."""
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.npcs_updated = 0
    
    def update(self, intent: dict, event_bus: EventBus):
        self.npcs_updated += 1
        self.event_bus.emit(Event(
            "npc_update",
            {
                "npcs_acted": 2,
                "intent": intent.get("action", "unknown"),
            }
        ))


class MockStoryDirector:
    """Mock story director that generates narrative."""
    
    def __init__(self):
        self.process_count = 0
        self.events_received = []
    
    def process(self, events: list, intent: dict, event_bus: EventBus) -> dict:
        self.process_count += 1
        self.events_received = events[:]
        
        # Generate narrative based on events
        if events:
            narrative = f"Processed {len(events)} events"
        else:
            narrative = "Nothing of note happened"
        
        # Emit scene_generated event (PATCH 2)
        event_bus.emit(Event(
            "scene_generated",
            {
                "narrative": narrative,
                "events_processed": len(events),
            }
        ))
        
        return {
            "narrative": narrative,
            "mood": "neutral",
            "events_processed": len(events),
        }


class MockSceneRenderer:
    """Mock scene renderer."""
    
    def render(self, narrative: dict) -> dict:
        return {
            "description": narrative.get("narrative", ""),
            "mood": narrative.get("mood", "neutral"),
            "ready": True,
        }


# ============================================================
# Single Game Loop Authority Tests
# ============================================================

class TestSingleGameLoopAuthority:
    """Tests verifying single game loop authority."""

    def test_game_loop_is_single_entry_point(self):
        """Verify that GameLoop.tick() is the only execution path."""
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=MockNPCSystem(EventBus()),
            story_director=MockStoryDirector(),
            scene_renderer=MockSceneRenderer(),
        )
        
        # All input goes through handle_input -> loop.tick
        result = engine.handle_input("look around")
        
        assert result["ready"] is True
        assert engine.tick_count == 1

    def test_world_tick_called_once_per_input(self):
        """Verify world.tick() is called exactly once per tick."""
        world = MockWorld()
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=world,
            npc_system=MockNPCSystem(EventBus()),
            story_director=MockStoryDirector(),
            scene_renderer=MockSceneRenderer(),
        )
        
        engine.handle_input("first input")
        engine.handle_input("second input")
        engine.handle_input("third input")
        
        assert world.tick_count == 3

    def test_npc_system_updated_each_tick(self):
        """Verify NPC system is updated each tick."""
        event_bus = EventBus()
        npc_system = MockNPCSystem(event_bus)
        
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=npc_system,
            story_director=MockStoryDirector(),
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        engine.handle_input("explore")
        assert npc_system.npcs_updated == 1
        
        engine.handle_input("talk")
        assert npc_system.npcs_updated == 2


# ============================================================
# Event Bus Decoupling Tests
# ============================================================

class TestEventBusDecoupling:
    """Tests verifying event bus decoupling."""

    def test_events_flow_from_npc_to_director(self):
        """Verify events emitted by NPC system reach the director."""
        event_bus = EventBus()
        npc_system = MockNPCSystem(event_bus)
        story_director = MockStoryDirector()
        
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=npc_system,
            story_director=story_director,
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        engine.handle_input("interact")
        
        # Director should have received the NPC event
        assert story_director.process_count == 1
        assert len(story_director.events_received) == 1
        assert story_director.events_received[0].type == "npc_update"

    def test_multiple_event_sources(self):
        """Verify events from multiple sources are collected."""
        event_bus = EventBus()
        
        # Create NPC system that emits multiple events
        class MultiEventNPCSystem:
            def __init__(self, event_bus):
                self.event_bus = event_bus
            
            def update(self, intent, event_bus):
                self.event_bus.emit(Event("npc_thinking", {"thought": "I should move"}))
                self.event_bus.emit(Event("npc_moving", {"from": (0, 0), "to": (1, 1)}))
                self.event_bus.emit(Event("npc_arriving", {"location": "market"}))
        
        npc_system = MultiEventNPCSystem(event_bus)
        story_director = MockStoryDirector()
        
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=npc_system,
            story_director=story_director,
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        engine.handle_input("wait")
        
        # Director should receive all 3 events
        assert story_director.events_received[0].type == "npc_thinking"
        assert story_director.events_received[1].type == "npc_moving"
        assert story_director.events_received[2].type == "npc_arriving"

    def test_events_cleared_between_ticks(self):
        """Verify events from NPC systems are cleared between ticks."""
        event_bus = EventBus()
        
        # Use a simpler director that does NOT emit events
        class SilentDirector:
            def __init__(self):
                self.events_received = []
            def process(self, events, intent, event_bus):
                self.events_received = events[:]
                return {"narrative": "silent", "mood": "neutral"}
        
        class TwoShotNPCSystem:
            def __init__(self, event_bus):
                self.event_bus = event_bus
                self.tick_count = 0
            
            def update(self, intent, event_bus):
                self.tick_count += 1
                self.event_bus.emit(Event(f"tick_{self.tick_count}"))
        
        npc_system = TwoShotNPCSystem(event_bus)
        director1 = SilentDirector()
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=npc_system,
            story_director=director1,
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        engine.handle_input("tick1")
        assert len(director1.events_received) == 1
        assert director1.events_received[0].type == "tick_1"
        
        director2 = SilentDirector()
        engine.game_loop.story_director = director2
        engine.handle_input("tick2")
        # Director2 should receive tick_2 event from this tick, not tick_1
        assert len(director2.events_received) == 1
        assert director2.events_received[0].type == "tick_2"


# ============================================================
# Phase 1.5 — StoryDirector Emits Events (PATCH 2)
# ============================================================

class TestPhase15StoryDirectorEvents:
    """Tests for PATCH 2: StoryDirector emits scene_generated event."""

    def test_director_emits_scene_generated_event(self):
        """Verify that StoryDirector emits scene_generated event."""
        event_bus = EventBus()
        director = MockStoryDirector()
        
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=MockNPCSystem(event_bus),
            story_director=director,
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        engine.handle_input("look around")
        
        # StoryDirector should have emitted scene_generated event
        events = event_bus.collect()
        scene_events = [e for e in events if e.type == "scene_generated"]
        assert len(scene_events) == 1
        assert "events_processed" in scene_events[0].payload

    def test_director_emits_event_after_processing(self):
        """Verify scene_generated is emitted after narrative processing."""
        event_bus = EventBus(debug=True)
        director = MockStoryDirector()
        
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=MockNPCSystem(event_bus),
            story_director=director,
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        # NPC emits npc_update, then director emits scene_generated
        engine.handle_input("interact")
        
        # Check log for both event types (collect clears events)
        log = event_bus.log
        event_types = [e.type for e in log]
        # Both npc_update and scene_generated should be present in the log
        assert "npc_update" in event_types
        assert "scene_generated" in event_types


# ============================================================
# Narrative Director Pipeline Tests
# ============================================================

class TestNarrativeDirectorPipeline:
    """Tests verifying the narrative director pipeline."""

    def test_director_analyzes_events(self):
        """Verify director properly analyzes event data."""
        event_bus = EventBus()
        npc = MockNPCSystem(event_bus)
        director = MockStoryDirector()
        
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=npc,
            story_director=director,
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        engine.handle_input("attack goblin")
        
        assert director.events_received[0].payload["intent"] == "attack"

    def test_scene_rendering_pipeline(self):
        """Verify scene rendering receives narrative data."""
        class NarrativeDirector:
            def process(self, events, intent, event_bus):
                return {
                    "narrative": "A tale of adventure",
                    "mood": "exciting",
                    "characters": ["hero", "companion"],
                }
        
        class VerifyingRenderer:
            def __init__(self):
                self.received_narrative = None
            
            def render(self, narrative):
                self.received_narrative = narrative
                return {"description": narrative["narrative"]}
        
        renderer = VerifyingRenderer()
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=MockNPCSystem(EventBus()),
            story_director=NarrativeDirector(),
            scene_renderer=renderer,
            event_bus=EventBus(),
        )
        
        result = engine.handle_input("explore")
        
        assert renderer.received_narrative["mood"] == "exciting"
        assert "characters" in renderer.received_narrative


# ============================================================
# Phase 1.5 — TickPhase Tests (PATCH 6)
# ============================================================

class TestTickPhase:
    """Tests for PATCH 6: TickPhase enumeration."""

    def test_tick_phase_values(self):
        """Test that TickPhase has expected values."""
        assert TickPhase.PRE_WORLD.value == "pre_world"
        assert TickPhase.POST_WORLD.value == "post_world"
        assert TickPhase.PRE_NPC.value == "pre_npc"
        assert TickPhase.POST_NPC.value == "post_npc"


# ============================================================
# Game Engine Integration Tests
# ============================================================

class TestGameEngineIntegration:
    """Tests verifying GameEngine integration."""

    def test_engine_creates_shared_event_bus(self):
        """Verify engine creates and shares EventBus correctly."""
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=MockNPCSystem(EventBus()),
            story_director=MockStoryDirector(),
            scene_renderer=MockSceneRenderer(),
        )
        
        # Engine should have created EventBus
        assert engine.event_bus is not None
        
        # Loop should use same EventBus
        assert engine.game_loop.event_bus is engine.event_bus

    def test_engine_resets_completely(self):
        """Verify reset clears all engine state."""
        event_bus = EventBus()
        npc = MockNPCSystem(event_bus)
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=npc,
            story_director=MockStoryDirector(),
            scene_renderer=MockSceneRenderer(),
            event_bus=event_bus,
        )
        
        # Do some work
        engine.handle_input("first")
        engine.handle_input("second")
        
        # Reset
        engine.reset()
        
        # All state should be cleared
        assert engine.tick_count == 0
        assert event_bus.pending_count == 0

    def test_engine_callbacks_work(self):
        """Verify engine callback registration works end-to-end."""
        tick_contexts = []
        
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=MockNPCSystem(EventBus()),
            story_director=MockStoryDirector(),
            scene_renderer=MockSceneRenderer(),
        )
        
        engine.on_post_tick(lambda ctx: tick_contexts.append({
            "tick": ctx.tick_number,
            "input": ctx.player_input,
        }))
        
        engine.handle_input("look")
        engine.handle_input("move north")
        
        assert len(tick_contexts) == 2
        assert tick_contexts[0]["input"] == "look"
        assert tick_contexts[1]["input"] == "move north"


# ============================================================
# Regression-Style Functional Tests
# ============================================================

class TestFunctionalRegression:
    """Functional regression tests for common failure scenarios."""

    def test_empty_input_handled(self):
        """Test that empty input doesn't crash the system."""
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=MockNPCSystem(EventBus()),
            story_director=MockStoryDirector(),
            scene_renderer=MockSceneRenderer(),
        )
        
        result = engine.handle_input("")
        assert result["ready"] is True

    def test_special_characters_handled(self):
        """Test that special characters don't crash the system."""
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=MockNPCSystem(EventBus()),
            story_director=MockStoryDirector(),
            scene_renderer=MockSceneRenderer(),
        )
        
        result = engine.handle_input("!@#$%^&*()")
        assert result["ready"] is True

    def test_very_long_input_handled(self):
        """Test that very long input doesn't crash the system."""
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=MockNPCSystem(EventBus()),
            story_director=MockStoryDirector(),
            scene_renderer=MockSceneRenderer(),
        )
        
        long_input = "explore " * 1000
        result = engine.handle_input(long_input)
        assert result["ready"] is True

    def test_rapid_succession_ticks(self):
        """Test rapid tick execution."""
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=MockNPCSystem(EventBus()),
            story_director=MockStoryDirector(),
            scene_renderer=MockSceneRenderer(),
        )
        
        for i in range(100):
            result = engine.handle_input(f"action_{i}")
            assert result["ready"] is True
        
        assert engine.tick_count == 100

    def test_event_bus_does_not_accumulate_after_reset(self):
        """Test that reset prevents event accumulation."""
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorld(),
            npc_system=MockNPCSystem(EventBus()),
            story_director=MockStoryDirector(),
            scene_renderer=MockSceneRenderer(),
        )
        
        # Run some ticks
        for _ in range(10):
            engine.handle_input("test")
        
        # Reset
        engine.reset()
        
        # Verify clean state
        assert engine.event_bus.pending_count == 0
        assert engine.game_loop.tick_count == 0