"""Game Engine — Single entry point for the RPG system.

PHASE 1 — STABILIZE Step 6:
This is the SINGLE entry point for all game operations as specified in rpg-design.txt.

All other entry points (main.py, player_loop.py run methods, etc.) are DEPRECATED
and should route through this class.

PHASE 2 — REPLAY ENGINE FIX #2: System Factories
Previously, replay reused system instances (world, npc_system, etc.) causing
state leaks that broke determinism. Now this class uses factory functions to
create FRESH system instances for each new GameLoop.

ARCHITECTURE RULE:
This system must NOT directly call other systems.
Use EventBus for all cross-system communication.

Usage:
    engine = GameEngine(
        intent_parser_factory=MyParser,
        world_factory=MyWorld,
        npc_system_factory=MyNPCs,
        story_director_factory=MyDirector,
        scene_renderer_factory=MyRenderer,
    )
    scene = engine.handle_input("look around")
"""

from typing import Any, Callable, Dict, List, Optional

from .event_bus import EventBus
from .game_loop import (
    GameLoop,
    IntentParser,
    NPCSystem,
    SceneRenderer,
    StoryDirector,
    TickContext,
    WorldSystem,
)


class GameEngine:
    """Single entry point for the RPG game system.

    This class wraps the GameLoop and EventBus to provide a clean,
    single-interface API for game operations.

    PHASE 2 FIX #2: Factory Pattern for Fresh Systems
    Before: _new_loop() reused system instances -> state leaks
    After:  _new_loop() calls factories -> fresh instances every time

    This ensures that replay/load creates a completely clean simulation
    without mutated state from previous gameplay sessions.
    """

    def __init__(
        self,
        intent_parser: Optional[IntentParser] = None,
        world: Optional[WorldSystem] = None,
        npc_system: Optional[NPCSystem] = None,
        story_director: Optional[StoryDirector] = None,
        scene_renderer: Optional[SceneRenderer] = None,
        event_bus: Optional[EventBus] = None,
        # PHASE 2 FIX #2: Factory functions for creating fresh systems
        intent_parser_factory: Optional[Callable[[], IntentParser]] = None,
        world_factory: Optional[Callable[[], WorldSystem]] = None,
        npc_system_factory: Optional[Callable[[], NPCSystem]] = None,
        story_director_factory: Optional[Callable[[], StoryDirector]] = None,
        scene_renderer_factory: Optional[Callable[[], SceneRenderer]] = None,
    ):
        """Initialize the GameEngine with all required subsystems.

        Args:
            intent_parser: Converts player input to structured intents.
            world: World simulation system.
            npc_system: NPC management system.
            story_director: Narrative/story director.
            scene_renderer: Renders final scene output.
            event_bus: Optional external EventBus. If None, creates internal one.
            intent_parser_factory: Factory for creating fresh IntentParser instances.
            world_factory: Factory for creating fresh WorldSystem instances.
            npc_system_factory: Factory for creating fresh NPCSystem instances.
            story_director_factory: Factory for creating fresh StoryDirector instances.
            scene_renderer_factory: Factory for creating fresh SceneRenderer instances.
        """
        self.event_bus = event_bus or EventBus()

        # Store initial systems for first run
        self._intent_parser = intent_parser
        self._world = world
        self._npc_system = npc_system
        self._story_director = story_director
        self._scene_renderer = scene_renderer

        # PHASE 2 FIX #2: Store factories for creating fresh systems during replay
        self._intent_parser_factory = intent_parser_factory
        self._world_factory = world_factory
        self._npc_system_factory = npc_system_factory
        self._story_director_factory = story_director_factory
        self._scene_renderer_factory = scene_renderer_factory

        self.loop = GameLoop(
            intent_parser=intent_parser or (self._intent_parser_factory() if self._intent_parser_factory else None),
            world=world or (self._world_factory() if self._world_factory else None),
            npc_system=npc_system or (self._npc_system_factory() if self._npc_system_factory else None),
            event_bus=self.event_bus,
            story_director=story_director or (self._story_director_factory() if self._story_director_factory else None),
            scene_renderer=scene_renderer or (self._scene_renderer_factory() if self._scene_renderer_factory else None),
        )

    def handle_input(self, player_input: str) -> Dict[str, Any]:
        """Process player input and return the resulting scene.

        This is the PRIMARY entry point for all game interaction.

        Args:
            player_input: Raw player input string.

        Returns:
            The rendered scene dictionary.
        """
        return self.loop.tick(player_input)

    @property
    def event_bus(self) -> EventBus:
        """Access the shared EventBus instance."""
        return self._event_bus

    @event_bus.setter
    def event_bus(self, bus: EventBus) -> None:
        """Set the EventBus instance."""
        self._event_bus = bus

    @property
    def game_loop(self) -> GameLoop:
        """Access the internal GameLoop."""
        return self.loop

    @property
    def tick_count(self) -> int:
        """Number of ticks processed so far."""
        return self.loop.tick_count

    def reset(self) -> None:
        """Reset the engine state (clears loops, events, tick count)."""
        self.loop.reset()
        self.event_bus.reset()

    # Convenient hook registrations delegate to GameLoop

    def on_pre_tick(self, callback: Callable[[TickContext], None]) -> None:
        """Register a pre-tick callback.

        Args:
            callback: Function called before the tick pipeline runs.
        """
        self.loop.on_pre_tick(callback)

    def on_post_tick(self, callback: Callable[[TickContext], None]) -> None:
        """Register a post-tick callback.

        Args:
            callback: Function called after the tick pipeline completes.
        """
        self.loop.on_post_tick(callback)

    def on_event(self, callback: Callable) -> None:
        """Register an event callback.

        Args:
            callback: Function called for each event.
        """
        self.loop.on_event(callback)

    # -------------------------
    # PHASE 2 — SAVE / LOAD
    # -------------------------

    def save(self) -> List["Event"]:
        """Return full event history (save game).

        PHASE 2 — REPLAY ENGINE:
        The save system works by persisting the event history
        rather than snapshotting world state. This enables:
        - Deterministic replay
        - Time-travel debugging
        - Branching timelines

        Returns:
            Complete list of events emitted during gameplay.
        """
        return self._event_bus.history()

    def load(self, events: List["Event"]) -> None:
        """Load game state from event history.

        PHASE 2 — REPLAY ENGINE:
        Reconstructs game state by replaying all events into a fresh
        GameLoop instance using the ReplayEngine.

        PHASE 2 FIX #2: Uses factory pattern to create fresh system instances,
        preventing state leaks from previous gameplay sessions.

        Args:
            events: List of events from a previous save().
        """
        from .replay_engine import ReplayEngine

        replay = ReplayEngine(self._new_loop)
        self.loop = replay.replay(events)
        # Update internal reference
        self._event_bus = self.loop.event_bus

    def _new_loop(self) -> GameLoop:
        """Factory for fresh loop (used by replay).

        PHASE 2 FIX #2: This method now uses factory functions to create
        COMPLETELY FRESH system instances for each call.

        Old behavior (broken):
            return GameLoop(
                intent_parser=self.loop.intent_parser,  # REUSED - state leak!
                world=self.loop.world,                   # REUSED - state leak!
                ...
            )

        New behavior (correct):
            return GameLoop(
                intent_parser=self._intent_parser_factory(),  # NEW instance
                world=self._world_factory(),                   # NEW instance
                ...
            )

        Returns:
            A new GameLoop instance with fresh system instances.

        Raises:
            RuntimeError: If factories are not configured.
        """
        if not all([
            self._intent_parser_factory,
            self._world_factory,
            self._npc_system_factory,
            self._story_director_factory,
            self._scene_renderer_factory,
        ]):
            raise RuntimeError(
                "System factories are required for replay/load. "
                "Initialize GameEngine with *_factory parameters."
            )

        return GameLoop(
            intent_parser=self._intent_parser_factory(),
            world=self._world_factory(),
            npc_system=self._npc_system_factory(),
            story_director=self._story_director_factory(),
            scene_renderer=self._scene_renderer_factory(),
            event_bus=EventBus(),
        )

    # -------------------------
    # PHASE 3 — BRANCHING TIMELINES (PATCH 5)
    # -------------------------

    def fork_timeline(self, from_event_id: str) -> "GameLoop":
        """Create a new branch starting from a past event.

        PHASE 3 — FORK API:
        Replays state up to the fork point, then returns a fresh loop
        that the player can continue from. The player's next action will
        create a NEW child of from_event_id, forming a branch.

        Example:
            # Player goes: "go north" -> e1, "talk to guard" -> e2
            fork_loop = engine.fork_timeline(e1.event_id)
            # Now from e1, player does "attack guard" -> creates e3_alt
            # Original timeline: e1 -> e2
            # New branch:        e1 -> e3_alt

        Args:
            from_event_id: The event ID to fork from (must exist in history).

        Returns:
            A fresh GameLoop with state reconstructed up to the fork point,
            ready for new player input that will create a branch.
        """
        from .replay_engine import ReplayEngine

        # Get event history
        events = self._event_bus.history()

        # Replay up to the fork point
        replay_engine = ReplayEngine(self._new_loop)
        loop = replay_engine.replay(
            events,
            branch_leaf_id=from_event_id,
        )

        # Update the active event bus reference
        self._event_bus = loop.event_bus

        return loop

    # -------------------------
    # PHASE 3 — DEBUG API (PATCH 8)
    # -------------------------

    def get_timeline_branch(self, event_id: str) -> List[str]:
        """Get the full branch path from root to the specified event.

        PHASE 3 — DEBUG API:
        Returns the chain of event IDs from the root to the given event,
        useful for understanding the causal history of any point in the timeline.

        Args:
            event_id: The event to trace back from.

        Returns:
            List of event IDs from root to the specified event.

        Raises:
            KeyError: If the event is not found in the timeline graph.
        """
        return self._event_bus.timeline.get_branch(event_id)

    def list_branches(self) -> Dict[str, List[str]]:
        """List all branch points in the timeline.

        PHASE 3 — DEBUG API:
        Returns events that have multiple children (fork points).
        Useful for understanding the shape of the timeline graph.

        Returns:
            Dictionary mapping fork point event IDs to their child event IDs.
        """
        return {
            eid: node.children
            for eid, node in self._event_bus.timeline.nodes.items()
            if node.children
        }
