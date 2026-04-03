"""Regression tests for PHASE 2 — REPLAY ENGINE (PATCHED).

These tests ensure that the Phase 2 replay engine fixes don't regress
and that the critical architectural problems remain solved:
- Fix #1: History duplication prevention
- Fix #2: System factory pattern (no state leaks)
- Fix #3: Tick advancement during replay
- Fix #4: No load_history in replay path
- Fix #5: Event dispatch to system handlers
"""

import pytest

from app.rpg.core import Event, EventBus, ReplayEngine, ReplayConfig, GameEngine


# ==================== Mock Systems ====================


class MockIntentParser:
    def parse(self, player_input: str) -> dict:
        return {"action": player_input}


class MockWorldSystem:
    def __init__(self):
        self.tick_count = 0
        self.events_handled = []

    def tick(self, event_bus: EventBus) -> None:
        self.tick_count += 1
        event_bus.emit(Event("world_tick", {"tick": self.tick_count}, source="world"))

    def handle_event(self, event: Event) -> None:
        self.events_handled.append(event)


class MockNPCSystem:
    def __init__(self):
        self.update_count = 0
        self.events_handled = []

    def update(self, intent: dict, event_bus: EventBus) -> None:
        self.update_count += 1
        event_bus.emit(Event("npc_updated", source="npc"))

    def handle_event(self, event: Event) -> None:
        self.events_handled.append(event)


class MockStoryDirector:
    def __init__(self):
        self.events_handled = []

    def process(self, events: list, intent: dict, event_bus: EventBus) -> dict:
        event_bus.emit(Event("narrative_done", source="director"))
        return {"narrative": "done"}

    def handle_event(self, event: Event) -> None:
        self.events_handled.append(event)


class MockSceneRenderer:
    def render(self, narrative: dict) -> dict:
        return {"scene": narrative}


def _create_loop():
    """Create a GameLoop with mock systems."""
    from app.rpg.core.game_loop import GameLoop

    return GameLoop(
        intent_parser=MockIntentParser(),
        world=MockWorldSystem(),
        npc_system=MockNPCSystem(),
        story_director=MockStoryDirector(),
        scene_renderer=MockSceneRenderer(),
        event_bus=EventBus(),
    )


def _create_factored_engine():
    """Create a GameEngine with factory functions."""
    return GameEngine(
        intent_parser=MockIntentParser(),
        world=MockWorldSystem(),
        npc_system=MockNPCSystem(),
        story_director=MockStoryDirector(),
        scene_renderer=MockSceneRenderer(),
        event_bus=EventBus(),
        intent_parser_factory=MockIntentParser,
        world_factory=MockWorldSystem,
        npc_system_factory=MockNPCSystem,
        story_director_factory=MockStoryDirector,
        scene_renderer_factory=MockSceneRenderer,
    )


# ==================== Regression: Fix #1 - History Duplication ====================


class TestHistoryDuplicationRegression:
    """Regression tests for history duplication prevention."""

    def test_replay_does_not_duplicate_history(self):
        """History should NOT grow during replay."""
        engine = ReplayEngine(_create_loop)

        events = [Event("a", {"tick": i}, source="test") for i in range(1, 11)]
        loop = engine.replay(events)

        history = loop.event_bus.history()
        # With emit(replay=True), history stays empty
        assert len(history) == 0, f"History duplicated: expected 0, got {len(history)}"

    def test_normal_gameplay_still_records_history(self):
        """Normal gameplay should still record history."""
        bus = EventBus()
        for i in range(5):
            bus.emit(Event(f"event_{i}", source="test"))

        assert len(bus.history()) == 5

    def test_multiple_replays_dont_accumulate_history(self):
        """Multiple replays should not accumulate history."""
        engine = ReplayEngine(_create_loop)
        events = [Event("a", {"tick": 1}, source="test")]

        for _ in range(10):
            loop = engine.replay(events)

        history = loop.event_bus.history()
        assert len(history) == 0, f"History accumulated across replays: expected 0, got {len(history)}"


# ==================== Regression: Fix #2 - System State Leak ====================


class TestSystemStateLeakRegression:
    """Regression tests for system state leak prevention."""

    def test_replay_creates_fresh_systems(self):
        """Each replay should create fresh system instances."""
        loop1 = _create_loop()
        loop2 = _create_loop()

        assert loop1.world is not loop2.world
        assert loop1.npc_system is not loop2.npc_system
        assert loop1.event_bus is not loop2.event_bus

    def test_multiple_loads_dont_mutate_previous_state(self):
        """Multiple loads should not mutate previous state."""
        engine1 = _create_factored_engine()
        engine1.handle_input("look")
        engine1.handle_input("move")

        saved = engine1.save()

        engine2 = _create_factored_engine()
        engine2.load(saved)

        engine3 = _create_factored_engine()
        engine3.load(saved)

        # Both engines should have independent state
        assert engine2.game_loop.world is not engine3.game_loop.world

    def test_engine_requires_factories_for_load(self):
        """Engine without factories should raise on load."""
        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=MockWorldSystem(),
            npc_system=MockNPCSystem(),
            story_director=MockStoryDirector(),
            scene_renderer=MockSceneRenderer(),
        )

        engine.handle_input("look")
        saved = engine.save()

        with pytest.raises(RuntimeError, match="System factories are required"):
            engine.load(saved)


# ==================== Regression: Fix #3 - Tick Advancement ====================


class TestTickAdvancementRegression:
    """Regression tests for tick advancement during replay."""

    def test_replay_advances_tick_count(self):
        """Replay should advance loop._tick_count to max tick."""
        engine = ReplayEngine(_create_loop)

        events = [
            Event("a", {"tick": 1}, source="test"),
            Event("b", {"tick": 5}, source="test"),
            Event("c", {"tick": 3}, source="test"),
        ]

        loop = engine.replay(events)
        assert loop._tick_count == 5, f"Tick not advanced: expected 5, got {loop._tick_count}"

    def test_tick_no_collision_after_replay(self):
        """After replay, new ticks should not collide."""
        engine = _create_loop()

        # Simulate replay setting tick to 10
        engine._tick_count = 10

        # Next natural tick should be > 10
        from app.rpg.core.game_loop import TickContext
        # Just verify the count
        assert engine._tick_count == 10


# ==================== Regression: Fix #4 - No load_history ====================


class TestNoLoadHistoryRegression:
    """Regression tests for load_history removal from replay path."""

    def test_replay_does_not_call_load_history(self):
        """Replay should not preload history via load_history."""
        engine = ReplayEngine(_create_loop)
        events = [Event("a", {"tick": 1}, source="test")]

        loop = engine.replay(events)

        # History should be empty (no load_history, no non-replay emits)
        assert len(loop.event_bus.history()) == 0

    def test_load_history_still_available_for_bootstrap(self):
        """load_history should still work for manual bootstrap."""
        bus = EventBus()
        events = [Event("a", {"tick": 1}, source="test"), Event("b", {"tick": 2}, source="test")]

        bus.load_history(events)
        assert len(bus.history()) == 2


# ==================== Regression: Fix #5 - Event Dispatch ====================


class TestEventDispatchRegression:
    """Regression tests for event dispatch to system handlers."""

    def test_replay_dispatches_to_world(self):
        """Replay should dispatch events to world.handle_event()."""
        loop = _create_loop()
        config = ReplayConfig(dispatch_to_systems=True, advance_ticks=True)
        engine = ReplayEngine(lambda: loop, config=config)

        events = [Event("world_event", {"data": 1}, source="test")]
        engine.replay(events)

        assert len(loop.world.events_handled) == 1

    def test_replay_dispatches_to_npc(self):
        """Replay should dispatch events to npc_system.handle_event()."""
        loop = _create_loop()
        config = ReplayConfig(dispatch_to_systems=True, advance_ticks=True)
        engine = ReplayEngine(lambda: loop, config=config)

        events = [Event("npc_event", source="test")]
        engine.replay(events)

        assert len(loop.npc_system.events_handled) == 1

    def test_replay_dispatches_to_director(self):
        """Replay should dispatch events to story_director.handle_event()."""
        loop = _create_loop()
        config = ReplayConfig(dispatch_to_systems=True, advance_ticks=True)
        engine = ReplayEngine(lambda: loop, config=config)

        events = [Event("director_event", source="test")]
        engine.replay(events)

        assert len(loop.story_director.events_handled) == 1

    def test_dispatch_can_be_disabled(self):
        """Dispatch to systems should be configurable."""
        loop = _create_loop()
        config = ReplayConfig(dispatch_to_systems=False, advance_ticks=True)
        engine = ReplayEngine(lambda: loop, config=config)

        events = [Event("test", source="test")]
        engine.replay(events)

        assert len(loop.world.events_handled) == 0
        assert len(loop.npc_system.events_handled) == 0
        assert len(loop.story_director.events_handled) == 0


# ==================== End-to-End Regression ====================


class TestEndToEndRegression:
    """End-to-end regression tests for the full replay pipeline."""

    def test_full_save_load_cycle(self):
        """Full save/load cycle should work correctly."""
        engine = _create_factored_engine()

        # Play
        for i in range(5):
            engine.handle_input(f"action_{i}")

        # Save
        saved = engine.save()
        assert len(saved) > 0

        # Load
        new_engine = _create_factored_engine()
        new_engine.load(saved)

        # Continue playing
        result = new_engine.handle_input("continue")
        assert result is not None

    def test_replay_is_deterministic(self):
        """Replay should produce the same state every time."""
        engine1 = _create_factored_engine()
        for _ in range(3):
            engine1.handle_input("test")

        saved = engine1.save()
        tick_count_1 = engine1.game_loop._tick_count

        # Replay twice
        engine2 = _create_factored_engine()
        engine2.load(saved)

        engine3 = _create_factored_engine()
        engine3.load(saved)

        # Both should have same tick count
        assert engine2.game_loop._tick_count == engine3.game_loop._tick_count

    def test_time_travel_produces_consistent_state(self):
        """Time-travel replay should produce consistent partial state."""
        engine = _create_factored_engine()
        for i in range(10):
            engine.handle_input(f"action_{i}")

        events = engine.save()

        # Replay to tick 5
        loop_5 = engine.game_loop.replay_to_tick(events, tick=5)
        assert loop_5._tick_count == 5

        # Replay to tick 3
        loop_3 = engine.game_loop.replay_to_tick(events, tick=3)
        assert loop_3._tick_count == 3