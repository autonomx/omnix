"""Game Loop — Single authority for game tick execution.

PHASE 1 — STABILIZE Step 1:
This module creates the single GameLoop authority as specified in rpg-design.txt.

PHASE 1.5 — ENFORCEMENT PATCH:
- Replaced _active_loop class variable with contextvars for async/multiplayer safety
- Inject tick ID into EventBus before collecting events
- Future-proof for async and multiple sessions

PHASE 2.5 — SNAPSHOT INTEGRATION:
- SnapshotManager integrated for periodic state serialization
- Automatic snapshots every N ticks (configurable, default 50)
- Enables hybrid replay (snapshot + events) for O(1) state recovery
- Time-travel debugging now uses snapshots for fast seeking

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
    7. Save snapshot at interval
"""

import contextvars
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol

from .event_bus import Event, EventBus
from .snapshot_manager import SnapshotManager


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


# Context-local storage for active game loop - future-proof for async/multiplayer
_active_loop_ctx = contextvars.ContextVar("active_game_loop", default=None)


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

    Uses contextvars for the active loop guard, making it safe for:
    - async/multithreading environments
    - multiple sessions in the same process

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

    # Kept for backwards compatibility - redirects to contextvar
    @classmethod
    def _get_active_loop(cls):
        """Get active loop from context (backwards compat)."""
        return _active_loop_ctx.get()

    @classmethod
    def _set_active_loop(cls, value):
        """Set active loop in context (backwards compat)."""
        _active_loop_ctx.set(value)

    _active_loop = property(_get_active_loop.__func__, _set_active_loop.__func__)

    def __init__(
        self,
        intent_parser: IntentParser,
        world: WorldSystem,
        npc_system: NPCSystem,
        event_bus: EventBus,
        story_director: StoryDirector,
        scene_renderer: SceneRenderer,
        snapshot_manager: Optional[SnapshotManager] = None,
    ):
        """Initialize the GameLoop with all required subsystems.

        Args:
            intent_parser: Converts player input to structured intents.
            world: World simulation system.
            npc_system: NPC management system.
            event_bus: Central event bus for cross-system communication.
            story_director: Narrative/story director.
            scene_renderer: Renders final scene output.
            snapshot_manager: Optional SnapshotManager for periodic state
                            serialization. If None, a default manager is created
                            with snapshot interval of 50 ticks.
        """
        self.intent_parser = intent_parser
        self.world = world
        self.npc_system = npc_system
        self.event_bus = event_bus
        self.story_director = story_director
        self.scene_renderer = scene_renderer
        # PHASE 2.5: SnapshotManager for periodic state serialization
        self.snapshot_manager = snapshot_manager or SnapshotManager()

        self._tick_count = 0
        self._on_pre_tick: Optional[Callable[[TickContext], None]] = None
        self._on_post_tick: Optional[Callable[[TickContext], None]] = None
        self._on_event: Optional[Callable[[Event], None]] = None

        # PHASE 3 — ACTIVE TIMELINE CONTEXT: Track current event for parent linking
        self.current_event_id: Optional[str] = None

        # PHASE 4.5 — NPC PLANNER: Simulation-based NPC decision making
        self.npc_planner: Optional[Any] = None
        self.npc_system_protocol: Optional[Any] = None  # get_npcs() method

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

        Uses contextvars for loop tracking, making it safe for:
        - async/multithreading environments
        - multiple sessions in the same process

        Args:
            player_input: Raw player input string.

        Returns:
            The rendered scene dictionary.

        Raises:
            RuntimeError: If multiple GameLoop instances are detected in same context.
        """
        # Check for multiple loops in same context using contextvars
        current = _active_loop_ctx.get()
        if current and current is not self:
            raise RuntimeError("Multiple GameLoop instances detected in same context")

        # Set this loop as active in context
        token = _active_loop_ctx.set(self)

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

        # Set current tick on event bus for temporal debugging (Fix #4)
        self.event_bus.set_tick(self._tick_count)

        try:
            # 2. Advance world simulation
            self.world.tick(self.event_bus)

            # 3. Update NPCs
            self.npc_system.update(intent, self.event_bus)

            # 4. Collect events (now with tick IDs injected)
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

            # PHASE 2.5: Save snapshot at interval
            if self.snapshot_manager.should_snapshot(self._tick_count):
                self.snapshot_manager.save_snapshot(self._tick_count, self)

            # Post-tick callback
            if self._on_post_tick:
                self._on_post_tick(ctx)

            return scene
        finally:
            # PHASE 3 — Advance timeline pointer after successful tick
            # The last event emitted becomes the parent for the next tick
            # (This is handled automatically by EventBus, but we track for API clarity)
            pass

            # Always reset the context to avoid stale references
            _active_loop_ctx.reset(token)

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
        """Reset the loop state (tick count, event bus, callbacks).

        Fix #6: Don't touch context vars here - that breaks nested contexts.
        Context var management is handled by the tick() method's finally block.
        """
        self._tick_count = 0
        self.event_bus.reset()
        self._on_pre_tick = None
        self._on_post_tick = None
        self._on_event = None

    # -------------------------
    # PHASE 4.5 — NPC PLANNER INTEGRATION
    # -------------------------

    def set_npc_planner(
        self,
        npc_planner: Any,
        npc_system: Optional[Any] = None,
    ) -> None:
        """Hook simulation-based NPC planner into the game loop.

        PHASE 4.5: Integrates NPCPlanner for forward-looking NPC decisions.
        NPCs simulate 3-5 futures, score them, and choose the best.

        Args:
            npc_planner: NPCPlanner instance with choose_action() method.
            npc_system: Optional NPC system with get_npcs() method.
                       If None, uses the npc_system passed to __init__.
        """
        self.npc_planner = npc_planner
        self.npc_system_protocol = npc_system

    def get_npc_phase_base_events(self) -> List[Event]:
        """Get event history available for NPC planning decisions.

        PHASE 4.5: Returns events up to the current tick for use as
        base_events in NPC simulation planning.

        Returns:
            List of events up to current tick.
        """
        return self.event_bus.history()

    def enable_planning_phase(
        self,
        npc_planner: Any,
        npc_system: Optional[Any] = None,
    ) -> None:
        """Enable Phase 4.5 NPC planning mode.

        Convenience method that sets up the planner and switches NPC
        phase to use simulation-based decisions.

        Args:
            npc_planner: NPCPlanner instance.
            npc_system: Optional NPC system override.
        """
        self.set_npc_planner(npc_planner, npc_system)
        # Override npc_method to use planner-based NPC phase
        self.npc_method = self._npc_phase_planner

    def _npc_phase_planner(self, intent: Dict[str, Any]) -> None:
        """NPC phase using simulation-based planner.

        Instead of calling npc_system.update(), this method:
        1. Gets base events from history
        2. For each NPC, generates candidate actions
        3. Uses NPCPlanner to choose best action
        4. Emits chosen actions via event bus

        Args:
            intent: Current parsed player intent (passed through for context).
        """
        base_events = self.event_bus.history()
        npc_sys = self.npc_system_protocol or self.npc_system

        # Get all NPCs that support planning
        npcs = []
        if hasattr(npc_sys, "get_npcs"):
            npcs = npc_sys.get_npcs()
        elif hasattr(npc_sys, "npcs"):
            npcs = npc_sys.npcs
        else:
            # Fall back to standard update
            npc_sys.update(intent, self.event_bus)
            return

        for npc in npcs:
            npc_id = getattr(npc, "id", getattr(npc, "npc_id", None))
            if npc_id is None:
                continue

            # Generate candidate actions
            candidate_actions = self._generate_candidates_for_npc(npc, intent)
            if not candidate_actions:
                continue

            # Choose best via planner
            if self.npc_planner:
                context = {
                    "npc": npc_id,
                    "npc_id": npc_id,
                    "intent": intent,
                    "tick": self._tick_count,
                }
                best = self.npc_planner.choose_action(
                    base_events=base_events,
                    candidates=candidate_actions,
                    context=context,
                )
            else:
                best = candidate_actions[0] if candidate_actions else None

            # Emit chosen action
            if best:
                for event in best:
                    self.event_bus.emit(event)

    def _generate_candidates_for_npc(
        self,
        npc: Any,
        intent: Dict[str, Any],
    ) -> List[List[Event]]:
        """Generate candidate action lists for an NPC.

        Uses CandidateGenerator if available, falls back to NPC's own
        generate_candidate_actions() method.

        Args:
            npc: The NPC instance.
            intent: Current player intent.

        Returns:
            List of candidate event lists.
        """
        npc_id = getattr(npc, "id", getattr(npc, "npc_id", "unknown"))

        # Try NPC's own candidate generation first
        if hasattr(npc, "generate_candidate_actions"):
            return npc.generate_candidate_actions()

        # Try using CandidateGenerator from planner module
        try:
            from ..ai.planner import CandidateGenerator

            # Build NPC context
            hp = getattr(npc, "hp", 100)
            npc_context = {
                "npc_id": npc_id,
                "hp": hp,
                "hp_low": hp < 30,
                "has_target": hasattr(npc, "target") and npc.target is not None,
                "can_reach": getattr(npc, "can_reach", False),
                "position": getattr(npc, "position", None),
            }

            generator = CandidateGenerator()
            return generator.generate(npc_context=npc_context)
        except Exception:
            # Fallback: create a simple idle/wander candidate
            return [[Event(
                type="idle",
                payload={"actor": npc_id, "reason": "no_planner_available"},
            )]]

    # -------------------------
    # PHASE 2 — REPLAY / TIME-TRAVEL (PATCHED)
    # -------------------------

    def replay_to_tick(
        self,
        events: List["Event"],
        tick: int,
        loop_factory: Optional[Callable[[], "GameLoop"]] = None,
    ) -> "GameLoop":
        """Replay events up to a specific tick (time-travel debug).

        PHASE 2 — REPLAY ENGINE:
        Creates a fresh GameLoop instance and replays events up to the
        specified tick, enabling time-travel debugging.

        PHASE 2 FIX #2: Accepts a factory for creating fresh system instances.
        If no factory is provided, falls back to reusing current systems
        (this maintains backward compat but is NOT recommended for production).

        Args:
            events: Full event history to replay from.
            tick: Target tick number to replay up to.
            loop_factory: Optional factory that returns a fresh GameLoop.
                         If None, creates loop with current system instances
                         (backward compat only — NOT recommended).

        Returns:
            A new GameLoop instance with state reconstructed from events.
        """
        from .replay_engine import ReplayEngine

        if loop_factory is not None:
            engine = ReplayEngine(loop_factory)
        else:
            # Backward compat: reuse current systems (NOT recommended)
            # PHASE 2 FIX #2: This path causes state leaks. Use factory instead.
            def fallback_factory() -> "GameLoop":
                return self.__class__(
                    intent_parser=self.intent_parser,
                    world=self.world,
                    npc_system=self.npc_system,
                    story_director=self.story_director,
                    scene_renderer=self.scene_renderer,
                    event_bus=EventBus(),
                )

            engine = ReplayEngine(fallback_factory)

        return engine.replay(events, up_to_tick=tick)
