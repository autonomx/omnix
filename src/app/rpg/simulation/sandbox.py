"""PHASE 4.5 — Simulation Sandbox (ISOLATED ENGINE)

Fully isolated simulation environment for "what-if" hypothesis testing.

This module creates FRESH game loop instances using a factory pattern,
replays base timeline events to reconstruct state, injects hypothetical
future events, and simulates forward ticks.

CRITICAL SAFETY RULES:
- NEVER mutates real game state
- Uses factory pattern for complete isolation
- All mutations happen inside sandbox only

Example:
    def fresh_engine():
        return MyGameEngine(...)

    sandbox = SimulationSandbox(fresh_engine)
    result = sandbox.run(
        base_events=current_history,
        future_events=[hypothetical_action],
        max_ticks=5,
    )
    print(result.final_tick)  # 5
    print(len(result.events))  # All events including hypothetical
"""

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from ..core.event_bus import Event


@dataclass
class SimulationResult:
    """Result of a sandbox simulation run.

    Attributes:
        events: Complete event history including base + hypothetical + simulated.
        final_tick: The final tick count after simulation.
        tick_count: Number of forward ticks that were simulated.
    """

    events: List[Event] = field(default_factory=list)
    final_tick: int = 0
    tick_count: int = 0


class SimulationSandbox:
    """Fully isolated simulation environment.

    This sandbox provides a clean, isolated game loop for testing
    "what-if" scenarios. It uses a factory to create fresh engine
    instances, ensuring no state leaks between simulations.

    Pipeline:
        1. Create fresh engine via factory
        2. Replay base events to reconstruct current state
        3. Inject hypothetical future events
        4. Run forward simulation ticks
        5. Collect and return results

    Thread Safety:
        Each sandbox run creates its own isolated engine instance.
        Multiple sandboxes can run in parallel safely.
    """

    def __init__(self, engine_factory: Callable[[], Any]):
        """Initialize the sandbox with an engine factory.

        Args:
            engine_factory: Callable that returns a fresh game engine/loop
                           instance with NEW subsystem instances.
                           Must return an object with:
                           - create_game_loop() method OR be a GameLoop directly
                           - event_bus attribute for event access
        """
        self.engine_factory = engine_factory

    def run(
        self,
        base_events: List[Event],
        future_events: List[Event],
        max_ticks: int = 10,
    ) -> SimulationResult:
        """Run an isolated simulation.

        Args:
            base_events: Event history to replay for state reconstruction.
                        These events establish the "current" game state.
            future_events: Hypothetical events to inject before simulation.
                          These are the "what-if" actions being tested.
            max_ticks: Maximum number of forward ticks to simulate.
                      Default 10. Must be > 0.

        Returns:
            SimulationResult with complete event history and final state.

        Raises:
            RuntimeError: If engine_factory fails to create a valid engine.
            ValueError: If max_ticks <= 0.
        """
        if max_ticks <= 0:
            raise ValueError(f"max_ticks must be > 0, got {max_ticks}")

        # Create fresh engine (CRITICAL for isolation)
        engine = self.engine_factory()

        # Get or create the game loop from the engine
        loop = self._get_game_loop(engine)

        # Record starting tick
        start_tick = getattr(loop, "_tick_count", 0) or getattr(loop, "tick_count", 0)

        # PHASE 5.5 — Enter simulation mode before running
        if hasattr(loop, "set_mode"):
            loop.set_mode("simulation")

        # Rebuild current state via replay
        self._replay_events(loop, base_events)

        # PHASE 5.5 — Use try/finally to ensure mode is always restored
        try:
            # Inject hypothetical future events
            for event in future_events:
                loop.event_bus.emit(event)

            # Simulate forward ticks
            ticks_simulated = 0
            for _ in range(max_ticks):
                if hasattr(loop, "tick"):
                    loop.tick("")
                ticks_simulated += 1
        finally:
            # PHASE 5.5 — Always return to live mode, even if simulation fails
            if hasattr(loop, "set_mode"):
                loop.set_mode("live")

        # Collect results
        history = self._get_event_history(loop)

        return SimulationResult(
            events=history,
            final_tick=getattr(loop, "_tick_count", start_tick + ticks_simulated),
            tick_count=ticks_simulated,
        )

    def _get_game_loop(self, engine: Any) -> Any:
        """Extract or return the game loop from an engine.

        Supports multiple engine patterns:
        - Direct GameLoop instance
        - Engine with create_game_loop() method
        - Engine with loop attribute

        Args:
            engine: The engine instance from factory.

        Returns:
            A game loop instance with tick() and event_bus attributes.
        """
        # If it IS a game loop (has tick and event_bus)
        if hasattr(engine, "tick") and hasattr(engine, "event_bus"):
            return engine

        # If it has create_game_loop method
        if hasattr(engine, "create_game_loop") and callable(engine.create_game_loop):
            return engine.create_game_loop()

        # If it has loop attribute
        if hasattr(engine, "loop"):
            return engine.loop

        raise RuntimeError(
            f"Engine {type(engine).__name__} does not expose a game loop. "
            "Expected: tick() method, event_bus attribute, or create_game_loop() method."
        )

    def _replay_events(self, loop: Any, events: List[Event]) -> None:
        """Replay events to reconstruct game state.

        Uses ReplayEngine if available, otherwise emits events directly.

        Args:
            loop: The game loop instance.
            events: Events to replay.
        """
        if not events:
            return

        if hasattr(loop, "replay_to_tick"):
            # Use ReplayEngine for proper state reconstruction
            loop.replay_to_tick(events, tick=max(
                (e.payload.get("tick", 0) for e in events if e.payload.get("tick") is not None),
                default=0,
            ))
        else:
            # Direct event emission fallback
            for event in events:
                loop.event_bus.emit(event, replay=True)

    def _get_event_history(self, loop: Any) -> List[Event]:
        """Extract event history from loop.

        Args:
            loop: The game loop instance.

        Returns:
            List of events from the event bus history.
        """
        event_bus = getattr(loop, "event_bus", None)
        if event_bus is None:
            return []

        if hasattr(event_bus, "get_history"):
            return event_bus.get_history()
        elif hasattr(event_bus, "history"):
            history = event_bus.history
            return history if isinstance(history, list) else list(history)
        elif hasattr(event_bus, "get_events"):
            return event_bus.get_events()

        return []