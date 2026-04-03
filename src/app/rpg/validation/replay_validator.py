"""PHASE 5.1 — Replay vs Live Validator

Ensures replay reconstructs exact same state as live execution.

This validator addresses the core requirement from rpg-design.txt:
- Replay = Live execution

The validation strategy:
1. Run a live game loop with events
2. Run a fresh loop and replay the same events via ReplayEngine
3. Compare state hashes

If hashes match, replay parity is proven.
If hashes differ, replay is missing or corrupting state.

KNOWN SOURCES OF REPLAY MISMATCH:
- ReplayEngine calling load_history() (deprecated, causes duplication)
- Replay not advancing loop._tick_count (causes tick collision)
- Replay not dispatching to system handle_event() (state not reconstructed)
- Events sorted differently in replay vs live
- Non-deterministic timestamps between runs
"""

from typing import Any, Callable, Dict, List, Optional

from ..core.replay_engine import ReplayEngine, ReplayConfig
from .state_hash import compute_state_hash


class ReplayValidator:
    """Ensures replay reconstructs exact same state as live execution.

    Usage:
        validator = ReplayValidator(fresh_loop_factory)
        result = validator.validate(sample_events)
        assert result["match"], "Replay state does not match live state!"

    Attributes:
        engine_factory: Callable that returns a fresh GameLoop instance.
    """

    def __init__(
        self,
        engine_factory: Callable[[], Any],
        config: Optional[ReplayConfig] = None,
    ):
        """Initialize with a factory for creating fresh game loops.

        Args:
            engine_factory: Callable that returns a complete GameLoop
                           with all subsystems initialized.
            config: Optional replay configuration. Defaults to
                    ReplayConfig(dispatch_to_systems=True, advance_ticks=True).
        """
        self.engine_factory = engine_factory
        self.config = config or ReplayConfig()

    def validate(self, events: List[Any]) -> Dict[str, Any]:
        """Compare live run vs replay run state.

        Args:
            events: List of events to run in both live and replay modes.

        Returns:
            Dictionary with:
            - match: bool - whether live and replay hashes match
            - live_hash: str - hash from live execution
            - replay_hash: str - hash from replay execution
        """
        # --- Live run ---
        loop_live = self.engine_factory()

        for e in events:
            loop_live.event_bus.emit(e)

        # Run some ticks to let systems process events
        num_ticks = max(1, len(events))
        for _ in range(num_ticks):
            loop_live.tick()

        live_hash = compute_state_hash(loop_live)

        # --- Replay run ---
        loop_replay = self.engine_factory()

        replay_engine = ReplayEngine(
            game_loop_factory=self.engine_factory,
            config=self.config,
        )

        # Use the replay engine with the live events
        replay_engine.replay(events)

        replay_hash = compute_state_hash(loop_replay)

        return {
            "match": live_hash == replay_hash,
            "live_hash": live_hash,
            "replay_hash": replay_hash,
        }

    def validate_with_tick_check(self, events: List[Any]) -> Dict[str, Any]:
        """Compare live vs replay AND verify tick counts match.

        This catches the common bug where replay doesn't advance
        the loop tick counter, causing future tick collisions.

        Args:
            events: List of events to run.

        Returns:
            Dictionary with all validation fields plus:
            - tick_match: bool - whether live and replay tick counts match
            - live_tick: int - tick count from live execution
            - replay_tick: int - tick count from replay execution
        """
        result = self.validate(events)

        loop_live = self.engine_factory()
        for e in events:
            loop_live.event_bus.emit(e)
        num_ticks = max(1, len(events))
        for _ in range(num_ticks):
            loop_live.tick()

        # For replay tick, we need to create a loop and replay events into it
        loop_replay = self.engine_factory()
        replay_engine = ReplayEngine(
            game_loop_factory=self.engine_factory,
            config=self.config,
        )
        replay_engine.replay(events)

        live_tick = getattr(loop_live, "_tick_count", getattr(loop_live, "tick_count", 0))
        replay_tick = getattr(loop_replay, "_tick_count", getattr(loop_replay, "tick_count", 0))

        result["tick_match"] = live_tick == replay_tick
        result["live_tick"] = live_tick
        result["replay_tick"] = replay_tick

        return result

    def validate_branch(
        self,
        events: List[Any],
        branch_event_id: str,
    ) -> Dict[str, Any]:
        """Validate replay of a specific branch (time-travel).

        This validates that branch replay (only events up to a
        specific event in the parent chain) produces the expected state.

        Args:
            events: Full event history.
            branch_event_id: Event ID to trace branch from.

        Returns:
            Dictionary with branch replay validation results.
        """
        # Create fresh loop and replay with branch selection
        loop_branch = self.engine_factory()
        replay_engine = ReplayEngine(
            game_loop_factory=self.engine_factory,
            config=self.config,
        )

        replay_engine.replay(events, branch_leaf_id=branch_event_id)

        branch_hash = compute_state_hash(loop_branch)

        return {
            "branch_hash": branch_hash,
            "branch_event_id": branch_event_id,
        }