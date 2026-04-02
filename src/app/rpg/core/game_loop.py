"""Game Loop — Single authority for game tick execution.

PHASE 1 — STABILIZE Step 1:
This module creates the single GameLoop authority as specified in rpg-design.txt.

ARCHITECTURE RULE:
This system must NOT directly call other systems.
Use EventBus for all cross-system communication.

Before this refactor:
    - player_loop.py had its own while True loop
    - world_loop.py had its own while True loop
    - Multiple tick() methods existed across systems

After this refactor:
    - ONLY GameLoop.tick() controls execution
    - All other loops are removed/deprecated

Tick Pipeline:
    1. Parse player intent
    2. Advance world simulation
    3. Update NPCs
    4. Collect events from the bus
    5. Process narrative via Director
    6. Render scene
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol

from .event_bus import Event, EventBus


class TickPhase(Enum):
    """Enumeration of tick phases for ordered execution phases."""
    PRE_WORLD = "pre_world"
    POST_WORLD = "post_world"
    PRE_NPC = "pre_npc"
    POST_NPC = "post_npc"


class IntentParser(Protocol):
    """Protocol for intent parser implementations."""
    def parse(self, player_input: str) -> Dict[str, Any]:
        """Parse player input into structured intent."""
        ...


class WorldSystem(Protocol):
    """Protocol for world simulation systems."""
    def tick(self, event_bus: EventBus) -> None:
        """Advance world state by one tick.

        Args:
            event_bus: The shared EventBus for emitting world events.
        """
        ...


class NPCSystem(Protocol):
    """Protocol for NPC update systems."""
    def update(self, intent: Dict[str, Any], event_bus: EventBus) -> None:
        """Update NPC states based on the parsed player intent.

        Args:
            intent: The parsed player intent dictionary.
            event_bus: The shared EventBus for emitting NPC events.
        """
        ...


class StoryDirector(Protocol):
    """Protocol for story director implementations."""
    def process(
        self, events: List[Event], intent: Dict[str, Any], event_bus: EventBus
    ) -> Dict[str, Any]:
        """Process events and intent into narrative output.

        Args:
            events: Events collected from the EventBus.
            intent: The parsed player intent dictionary.
            event_bus: The shared EventBus for emitting narrative events.

        Returns:
            Narrative data for scene rendering.
        """
        ...


class SceneRenderer(Protocol):
    """Protocol for scene rendering implementations."""
    def render(self, narrative: Dict[str, Any]) -> Dict[str, Any]:
        """Render a scene from narrative data.

        Args:
            narrative: Narrative data from the StoryDirector.

        Returns:
            Final scene data to present to the player.
        """
        ...


@dataclass
class TickContext:
    """Context data passed to tick hooks.

    Attributes:
        tick_number: The current tick number (1-based).
        player_input: Raw player input string.
        intent: Parsed intent dictionary.
        events: Events emitted during this tick.
        scene: The rendered scene output.
    """
    tick_number: int = 0
    player_input: str = ""
    intent: Dict[str, Any] = field(default_factory=dict)
    events: List[Event] = field(default_factory=list)
    scene: Dict[str, Any] = field(default_factory=dict)


class GameLoop:
    """The single authority for game tick execution.

    This class enforces a clean, deterministic game loop:
        1. Parse player intent
        2. Advance world simulation
        3. Update NPCs
        4. Collect events
        5. Narrative processing
        6. Render scene

    It also provides hooks for pre/post tick callbacks and event processing
    callbacks to allow extension without modification.

    Example:
        loop = GameLoop(
            intent_parser=MyParser(),
            world=MyWorld(),
            npc_system=MyNPCs(),
            event_bus=EventBus(),
            story_director=MyDirector(),
            scene_renderer=MyRenderer(),
        )
        scene = loop.tick("look around")
    """

    _active_loop = None

    def __init__(
        self,
        intent_parser: IntentParser,
        world: WorldSystem,
        npc_system: NPCSystem,
        event_bus: EventBus,
        story_director: StoryDirector,
        scene_renderer: SceneRenderer,
    ):
        """Initialize the GameLoop with all required subsystems.

        Args:
            intent_parser: Converts player input to structured intents.
            world: World simulation system.
            npc_system: NPC management system.
            event_bus: Central event bus for cross-system communication.
            story_director: Narrative/story director.
            scene_renderer: Renders final scene output.
        """
        self.intent_parser = intent_parser
        self.world = world
        self.npc_system = npc_system
        self.event_bus = event_bus
        self.story_director = story_director
        self.scene_renderer = scene_renderer

        self._tick_count = 0
        self._on_pre_tick: Optional[Callable[[TickContext], None]] = None
        self._on_post_tick: Optional[Callable[[TickContext], None]] = None
        self._on_event: Optional[Callable[[Event], None]] = None

    def tick(self, player_input: str) -> Dict[str, Any]:
        """Execute one game tick.

        This is the ONLY tick method that should drive game execution.
        All other loop-like mechanisms have been deprecated.

        Pipeline:
            1. Parse player intent
            2. Pre-tick hooks
            3. Advance world
            4. Update NPCs
            5. Collect and process events
            6. Narrative processing
            7. Render scene
            8. Post-tick hooks

        Args:
            player_input: Raw player input string.

        Returns:
            The rendered scene dictionary.

        Raises:
            RuntimeError: If multiple GameLoop instances are detected.
        """
        if GameLoop._active_loop and GameLoop._active_loop is not self:
            raise RuntimeError("Multiple GameLoop instances detected")

        GameLoop._active_loop = self

        self._tick_count += 1

        # 1. Parse player intent
        intent = self.intent_parser.parse(player_input)

        # Build tick context
        ctx = TickContext(
            tick_number=self._tick_count,
            player_input=player_input,
            intent=intent,
        )

        # Pre-tick callback
        if self._on_pre_tick:
            self._on_pre_tick(ctx)

        # 2. Advance world simulation
        self.world.tick(self.event_bus)

        # 3. Update NPCs
        self.npc_system.update(intent, self.event_bus)

        # 4. Collect events
        events = self.event_bus.collect()
        ctx.events = events

        # Process event callbacks
        if self._on_event:
            for event in events:
                self._on_event(event)

        # 5. Narrative processing
        narrative = self.story_director.process(events, intent, self.event_bus)

        # 6. Render scene
        scene = self.scene_renderer.render(narrative)
        ctx.scene = scene

        # Post-tick callback
        if self._on_post_tick:
            self._on_post_tick(ctx)

        return scene

    @property
    def tick_count(self) -> int:
        """Number of ticks processed so far."""
        return self._tick_count

    def on_pre_tick(self, callback: Callable[[TickContext], None]) -> None:
        """Register a pre-tick callback.

        Args:
            callback: Function called before the tick pipeline runs.
        """
        self._on_pre_tick = callback

    def on_post_tick(self, callback: Callable[[TickContext], None]) -> None:
        """Register a post-tick callback.

        Args:
            callback: Function called after the tick pipeline completes.
        """
        self._on_post_tick = callback

    def on_event(self, callback: Callable[[Event], None]) -> None:
        """Register an event callback.

        This is called for each event during the tick,
        after events are collected but before narrative processing.

        Args:
            callback: Function called for each event.
        """
        self._on_event = callback

    def reset(self) -> None:
        """Reset the loop state (tick count, event bus, callbacks)."""
        self._tick_count = 0
        self.event_bus.reset()
        self._on_pre_tick = None
        self._on_post_tick = None
        self._on_event = None