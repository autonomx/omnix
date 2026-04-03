"""PHASE 5.1 — Determinism Validator

Ensures identical runs produce identical results.

This validator addresses the core requirement from rpg-design.txt:
- Determinism: same input -> same output

The validation strategy:
1. Create two identical game loops from the same factory
2. Feed both loops the same events
3. Run both loops for the same number of ticks
4. Compare state hashes

If hashes match, determinism is proven for the given inputs.
If hashes differ, the system has non-deterministic behavior.

KNOWN SOURCES OF NON-DETERMINISM:
- LLM randomness (temperature > 0, random seeds)
- Timestamps (wall clock time)
- unordered dicts / sets in state
- UUID randomness in event IDs
- Random number generators without fixed seeds

FIXES (from rpg-design.txt):
- temperature = 0, seed = fixed
- inject deterministic clock
- always sort dicts/sets
- deterministic ID generator in test mode
"""

from typing import Any, Callable, Dict, List, Optional

from .state_hash import compute_state_hash


class DeterminismValidator:
    """Ensures identical runs produce identical results.

    Usage:
        validator = DeterminismValidator(fresh_loop_factory)
        result = validator.run_twice_and_compare(sample_events)
        assert result["match"], "Non-deterministic behavior detected!"

    Attributes:
        engine_factory: Callable that returns a fresh GameLoop instance.
    """

    def __init__(self, engine_factory: Callable[[], Any]):
        """Initialize with a factory for creating fresh game loops.

        Args:
            engine_factory: Callable that returns a complete GameLoop
                           with all subsystems initialized.
        """
        self.engine_factory = engine_factory

    def run_twice_and_compare(
        self,
        events: List[Any],
        num_ticks: int = 10,
    ) -> Dict[str, Any]:
        """Run identical game loops twice and compare results.

        Args:
            events: List of events to emit in both loops.
            num_ticks: Number of ticks to run. Default 10.

        Returns:
            Dictionary with:
            - match: bool - whether hashes are identical
            - hash1: str - hash from first run
            - hash2: str - hash from second run
        """
        loop1 = self.engine_factory()
        loop2 = self.engine_factory()

        # Emit same events to both loops
        for e in events:
            loop1.event_bus.emit(e)
            loop2.event_bus.emit(e)

        # Run same number of ticks
        for _ in range(num_ticks):
            loop1.tick()
            loop2.tick()

        hash1 = compute_state_hash(loop1)
        hash2 = compute_state_hash(loop2)

        return {
            "match": hash1 == hash2,
            "hash1": hash1,
            "hash2": hash2,
        }

    def run_n_times(
        self,
        events: List[Any],
        num_runs: int = 5,
        num_ticks: int = 10,
    ) -> Dict[str, Any]:
        """Run identical game loops N times and compare all results.

        More thorough than run_twice_and_compare — catches rare
        non-determinism that might not manifest in just 2 runs.

        Args:
            events: List of events to emit in all loops.
            num_runs: Number of identical runs. Default 5.
            num_ticks: Number of ticks per run. Default 10.

        Returns:
            Dictionary with:
            - match: bool - whether ALL hashes are identical
            - hashes: list[str] - hash from each run
            - unique_count: int - number of unique hashes observed
        """
        hashes = []

        for _ in range(num_runs):
            loop = self.engine_factory()

            for e in events:
                loop.event_bus.emit(e)

            for _ in range(num_ticks):
                loop.tick()

            hashes.append(compute_state_hash(loop))

        unique_hashes = set(hashes)

        return {
            "match": len(unique_hashes) == 1,
            "hashes": hashes,
            "unique_count": len(unique_hashes),
        }

    def determine_break_point(
        self,
        events: List[Any],
        max_ticks: int = 50,
    ) -> Dict[str, Any]:
        """Find the tick where determinism breaks.

        Binary search approach: runs two loops tick by tick and
        checks if hashes diverge.

        Args:
            events: List of events to emit.
            max_ticks: Maximum ticks to check. Default 50.

        Returns:
            Dictionary with:
            - match: bool - whether all ticks matched
            - divergence_tick: Optional[int] - first tick with mismatch, or None
            - details: list[str] - per-tick comparison results
        """
        loop1 = self.engine_factory()
        loop2 = self.engine_factory()

        details: List[str] = []
        divergence_tick: Optional[int] = None

        # Emit events to both
        for e in events:
            loop1.event_bus.emit(e)
            loop2.event_bus.emit(e)

        for tick_num in range(1, max_ticks + 1):
            loop1.tick()
            loop2.tick()

            h1 = compute_state_hash(loop1)
            h2 = compute_state_hash(loop2)

            if h1 != h2 and divergence_tick is None:
                divergence_tick = tick_num
                details.append(f"Tick {tick_num}: DIVERGED")
            else:
                details.append(f"Tick {tick_num}: match")

        return {
            "match": divergence_tick is None,
            "divergence_tick": divergence_tick,
            "details": details,
        }