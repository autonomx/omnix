"""Functional tests for PHASE 3 — BRANCHING TIMELINES + MULTIVERSE GRAPH.

Tests cover end-to-end branching timeline workflows:
- Basic fork and alternate timeline creation
- ReplayEngine branch selection
- GameEngine fork_timeline API
- Debug API (get_timeline_branch, list_branches)
- Full multiverse scenario: "What if I killed the guard?"
"""

import pytest

from app.rpg.core.timeline_graph import TimelineGraph
from app.rpg.core.event_bus import Event, EventBus
from app.rpg.core.replay_engine import ReplayEngine


# ==================== Helper Classes ====================


class MockIntentParser:
    """Mock intent parser for game loop tests."""
    def parse(self, player_input: str) -> dict:
        return {"action": player_input}


class TrackingWorldSystem:
    """Mock world system that tracks events."""
    def __init__(self):
        self.tick_count = 0
        self.events_handled = []

    def tick(self, event_bus: EventBus) -> None:
        self.tick_count += 1

    def handle_event(self, event: Event) -> None:
        self.events_handled.append(event)


class TrackingNPCSystem:
    """Mock NPC system that tracks events."""
    def __init__(self):
        self.update_count = 0
        self.events_handled = []

    def update(self, intent: dict, event_bus: EventBus) -> None:
        self.update_count += 1

    def handle_event(self, event: Event) -> None:
        self.events_handled.append(event)


class MockStoryDirector:
    """Mock story director for game loop tests."""
    def __init__(self):
        self.events_handled = []

    def process(self, events: list, intent: dict, event_bus: EventBus) -> dict:
        return {"narrative": "processed"}

    def handle_event(self, event: Event) -> None:
        self.events_handled.append(event)


class MockSceneRenderer:
    """Mock scene renderer for game loop tests."""
    def render(self, narrative: dict) -> dict:
        return {"scene": narrative}


def create_game_loop():
    """Create a functional game loop for tests."""
    from app.rpg.core.game_loop import GameLoop

    return GameLoop(
        intent_parser=MockIntentParser(),
        world=TrackingWorldSystem(),
        npc_system=TrackingNPCSystem(),
        story_director=MockStoryDirector(),
        scene_renderer=MockSceneRenderer(),
        event_bus=EventBus(),
    )


# ==================== Test Branch Creation ====================


class TestBranchCreation:
    """Test that branching creates alternate timelines."""

    def test_branch_creates_alternate_timeline(self):
        """Test full multiverse scenario: fork + alternate action."""
        # Build a timeline graph manually to simulate events
        graph = TimelineGraph()

        # e1: Player enters room
        graph.add_event("e1", parent_id=None)

        # e2: Player talks to guard
        graph.add_event("e2", parent_id="e1")

        # Branch A: e3a = Player bribes guard
        graph.add_event("e3a", parent_id="e2")

        # Branch B: e3b = Player attacks guard
        graph.add_event("e3b", parent_id="e2")

        # Verify both branches exist
        branch_a = graph.get_branch("e3a")
        branch_b = graph.get_branch("e3b")

        assert branch_a == ["e1", "e2", "e3a"]
        assert branch_b == ["e1", "e2", "e3b"]

        # Both branches share common history
        assert branch_a[:-1] == branch_b[:-1]

        # But diverge at the leaf
        assert branch_a[-1] != branch_b[-1]

    def test_fork_point_detected(self):
        """Test that fork points are correctly detected."""
        graph = TimelineGraph()
        graph.add_event("e1", parent_id=None)
        graph.add_event("e2", parent_id="e1")
        graph.add_event("e3a", parent_id="e2")
        graph.add_event("e3b", parent_id="e2")

        forks = graph.get_forks()
        assert "e2" in forks
        assert len(forks["e2"]) == 2


# ==================== Test ReplayEngine Branch Selection ====================


class TestReplayEngineBranchSelection:
    """Test ReplayEngine branch selection (PATCH 4)."""

    def test_replay_filters_to_branch(self):
        """Test that replay only includes events on the selected branch."""
        events = [
            Event("start", {"tick": 1}, source="test"),
            Event("talk", {"tick": 2}, source="test"),
            Event("bribe", {"tick": 3}, source="test"),
            Event("attack", {"tick": 4}, source="test"),
        ]

        # Set up parent IDs to create branching structure
        events[0].parent_id = None  # start is root
        events[1].parent_id = events[0].event_id  # talk -> start
        events[2].parent_id = events[1].event_id  # bribe -> talk (branch A)
        events[3].parent_id = events[1].event_id  # attack -> talk (branch B)

        def fresh_factory():
            return create_game_loop()

        engine = ReplayEngine(fresh_factory, config=None)

        # Replay branch A (bribe)
        loop_a = engine.replay(
            events,
            branch_leaf_id=events[2].event_id,  # bribe leaf
        )

        # Timeline should contain branch A events
        timeline = loop_a.event_bus.timeline
        # Timeline graph should have the events from the branch
        assert timeline.has_event(events[0].event_id)  # start
        assert timeline.has_event(events[1].event_id)  # talk
        assert timeline.has_event(events[2].event_id)  # bribe

    def test_replay_alternate_branch(self):
        """Test replaying the alternate branch produces different history."""
        events = [
            Event("start", {"tick": 1}, source="test"),
            Event("talk", {"tick": 2}, source="test"),
            Event("bribe", {"tick": 3}, source="test"),
            Event("attack", {"tick": 4}, source="test"),
        ]

        events[0].parent_id = None
        events[1].parent_id = events[0].event_id
        events[2].parent_id = events[1].event_id
        events[3].parent_id = events[1].event_id

        def fresh_factory():
            return create_game_loop()

        engine = ReplayEngine(fresh_factory, config=None)

        # Replay branch B (attack)
        loop_b = engine.replay(
            events,
            branch_leaf_id=events[3].event_id,  # attack leaf
        )

        timeline = loop_b.event_bus.timeline
        assert timeline.has_event(events[0].event_id)  # start
        assert timeline.has_event(events[1].event_id)  # talk
        assert timeline.has_event(events[3].event_id)  # attack


# ==================== Test EventBus Timeline Integration ====================


class TestEventBusTimelineIntegration:
    """Test EventBus timeline integration."""

    def test_emit_builds_dag(self):
        """Test that emit builds DAG structure."""
        bus = EventBus()

        e1 = Event("start", {"tick": 1}, source="game", parent_id=None)
        bus.emit(e1)

        e2 = Event("action", {"tick": 2}, source="player", parent_id=e1.event_id)
        bus.emit(e2)

        e3 = Event("action", {"tick": 3}, source="player", parent_id=e2.event_id)
        bus.emit(e3)

        assert bus.timeline.node_count() == 3
        branch = bus.timeline.get_branch(e3.event_id)
        assert len(branch) == 3

    def test_branch_from_emitted_events(self):
        """Test getting branch from events emitted via EventBus."""
        bus = EventBus()

        e1 = Event("start", {"tick": 1}, source="game", parent_id=None)
        bus.emit(e1)

        e2 = Event("fork", {"tick": 2}, source="player", parent_id=e1.event_id)
        bus.emit(e2)

        # Branch from leaf
        branch = bus.timeline.get_branch(e2.event_id)
        assert e1.event_id in branch
        assert e2.event_id in branch


# ==================== Test Debug API ====================


class TestDebugAPI:
    """Test Debug API methods on GameEngine (PATCH 8)."""

    def test_get_timeline_branch_returns_chain(self):
        """Test get_timeline_branch returns parent→leaf chain."""
        from app.rpg.core import GameEngine

        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=TrackingWorldSystem(),
            npc_system=TrackingNPCSystem(),
            story_director=MockStoryDirector(),
            scene_renderer=MockSceneRenderer(),
            intent_parser_factory=MockIntentParser,
            world_factory=TrackingWorldSystem,
            npc_system_factory=TrackingNPCSystem,
            story_director_factory=MockStoryDirector,
            scene_renderer_factory=MockSceneRenderer,
        )

        # Emit events to build timeline
        e1 = Event("start", {"tick": 1}, source="game", parent_id=None)
        engine.event_bus.emit(e1)

        e2 = Event("action", {"tick": 2}, source="player", parent_id=e1.event_id)
        engine.event_bus.emit(e2)

        branch = engine.get_timeline_branch(e2.event_id)
        assert e1.event_id in branch
        assert e2.event_id in branch

    def test_list_branches_shows_fork_points(self):
        """Test list_branches shows events with multiple children."""
        from app.rpg.core import GameEngine

        engine = GameEngine(
            intent_parser=MockIntentParser(),
            world=TrackingWorldSystem(),
            npc_system=TrackingNPCSystem(),
            story_director=MockStoryDirector(),
            scene_renderer=MockSceneRenderer(),
            intent_parser_factory=MockIntentParser,
            world_factory=TrackingWorldSystem,
            npc_system_factory=TrackingNPCSystem,
            story_director_factory=MockStoryDirector,
            scene_renderer_factory=MockSceneRenderer,
        )

        # Build branching structure
        e1 = Event("start", {"tick": 1}, source="game", parent_id=None)
        engine.event_bus.emit(e1)

        e2 = Event("fork", {"tick": 2}, source="player", parent_id=e1.event_id)
        engine.event_bus.emit(e2)

        e3a = Event("bribe", {"tick": 3}, source="player", parent_id=e2.event_id)
        engine.event_bus.emit(e3a)

        e3b = Event("attack", {"tick": 4}, source="player", parent_id=e2.event_id)
        engine.event_bus.emit(e3b)

        branches = engine.list_branches()
        assert e2.event_id in branches
        assert len(branches[e2.event_id]) == 2  # e3a, e3b


# ==================== End-to-End Multiverse Test ====================


class TestMultiverseScenario:
    """Test full multiverse scenario from design spec."""

    def test_what_if_i_killed_the_king(self):
        """Simulate: What if I killed the king instead of talking?"""
        graph = TimelineGraph()

        # Common history
        graph.add_event("e1", parent_id=None)  # Player enters castle
        graph.add_event("e2", parent_id="e1")  # Player meets king

        # Branch A: Player talks to king (normal path)
        graph.add_event("e3_talk", parent_id="e2")
        graph.add_event("e4_peace", parent_id="e3_talk")

        # Branch B: Player kills king (alternate path)
        graph.add_event("e3_kill", parent_id="e2")
        graph.add_event("e4_chaos", parent_id="e3_kill")

        # Verify both paths exist
        peace_branch = graph.get_branch("e4_peace")
        chaos_branch = graph.get_branch("e4_chaos")

        # Both start the same
        assert peace_branch[:2] == ["e1", "e2"]
        assert chaos_branch[:2] == ["e1", "e2"]

        # But diverge
        assert peace_branch[2] == "e3_talk"
        assert chaos_branch[2] == "e3_kill"

        # Fork point is e2
        forks = graph.get_forks()
        assert "e2" in forks
        assert set(forks["e2"]) == {"e3_talk", "e3_kill"}