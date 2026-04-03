"""PHASE 5.1 — Simulation Parity Validator

Ensures simulation matches real execution.

This validator addresses the core requirement from rpg-design.txt:
- Simulation = Real outcome (parity)

The validation strategy:
1. Run sandbox simulation with base events + future events
2. Run real execution with same events
3. Compare state hashes

If hashes match, simulation trust is proven.
If hashes differ, simulation is not faithfully reproducing real behavior.

KNOWN SOURCES OF SIMULATION MISMATCH:
- Sandbox not replaying base events correctly
- FutureSimulator using different seed/random state
- LLM non-determinism in simulation vs real
- EventBus not properly isolated in sandbox
- History ordering differences between runs
"""

import hashlib
import json
from typing import Any, Callable, Dict, List, Optional

from ..simulation.sandbox import SimulationSandbox
from .state_hash import compute_state_hash, stable_serialize


class SimulationParityValidator:
    """Ensures simulation matches real execution.

    Usage:
        validator = SimulationParityValidator(fresh_loop_factory)
        result = validator.validate(base_events, future_events)
        assert result["match"], "Simulation state does not match real state!"

    Attributes:
        engine_factory: Callable that returns a fresh GameLoop instance.
        sandbox: SimulationSandbox instance for running simulations.
    """

    def __init__(self, engine_factory: Callable[[], Any]):
        """Initialize with a factory for creating fresh game loops.

        Args:
            engine_factory: Callable that returns a complete GameLoop
                           with all subsystems initialized.
        """
        self.engine_factory = engine_factory
        self.sandbox = SimulationSandbox(engine_factory)

    def validate(
        self,
        base_events: List[Any],
        future_events: List[Any],
        max_ticks: int = 5,
    ) -> Dict[str, Any]:
        """Compare simulation vs real execution state.

        Args:
            base_events: Event history to replay for state reconstruction.
            future_events: Hypothetical events to inject before simulation.
            max_ticks: Number of forward ticks to simulate. Default 5.

        Returns:
            Dictionary with:
            - match: bool - whether sim and real hashes match
            - sim_hash: str - hash from simulation
            - real_hash: str - hash from real execution
        """
        # --- Simulated future ---
        sim_result = self.sandbox.run(
            base_events,
            future_events,
            max_ticks=max_ticks,
        )

        sim_hash = self._hash_from_events(sim_result.events)

        # --- Real execution ---
        loop = self.engine_factory()

        for e in base_events:
            loop.event_bus.emit(e)

        for e in future_events:
            loop.event_bus.emit(e)

        for _ in range(max_ticks):
            loop.tick()

        real_hash = compute_state_hash(loop)

        return {
            "match": sim_hash == real_hash,
            "sim_hash": sim_hash,
            "real_hash": real_hash,
        }

    def _hash_from_events(self, events: List[Any]) -> str:
        """Create a deterministic hash from a list of events.

        PHASE 5.1.5 — FIX #2: Hash full event structure.
        
        Previous version only hashed event IDs, which was too weak:
        Two runs could produce same IDs but different payloads/outcomes
        and the validator would incorrectly report "match".

        Now hashes: event_id, type, and full payload for complete parity checking.

        This is used for comparing simulation results against
        real execution results.

        Args:
            events: List of Event objects to hash.

        Returns:
            SHA-256 hex digest of event sequence.
        """
        event_data = []
        for e in events:
            event_data.append({
                "id": getattr(e, "event_id", None),
                "type": getattr(e, "type", None),
                "payload": stable_serialize(getattr(e, "payload", {})),
            })

        serialized = json.dumps(
            stable_serialize(event_data),
            sort_keys=True,
        )

        return hashlib.sha256(serialized.encode()).hexdigest()

    def validate_multi_candidate(
        self,
        base_events: List[Any],
        candidate_sets: List[List[Any]],
        max_ticks: int = 3,
    ) -> List[Dict[str, Any]]:
        """Validate simulation parity for multiple candidate sets.

        This is useful when testing "what-if" scenarios across
        many possible futures.

        Args:
            base_events: Event history to replay.
            candidate_sets: List of candidate event lists to test.
            max_ticks: Ticks per simulation. Default 3.

        Returns:
            List of validation results, one per candidate set.
        """
        results = []

        for i, candidates in enumerate(candidate_sets):
            result = self.validate(base_events, candidates, max_ticks)
            result["candidate_index"] = i
            results.append(result)

        return results

    def validate_progressive(
        self,
        base_events: List[Any],
        future_events: List[Any],
        tick_range: range = range(1, 10),
    ) -> List[Dict[str, Any]]:
        """Validate simulation parity at increasing tick counts.

        This catches bugs where simulation matches for few ticks
        but diverges over longer periods.

        Args:
            base_events: Event history to replay.
            future_events: Future events to simulate.
            tick_range: Range of tick counts to test.

        Returns:
            List of results for each tick count.
        """
        results = []

        for max_ticks in tick_range:
            result = self.validate(base_events, future_events, max_ticks)
            result["ticks"] = max_ticks
            results.append(result)

        return results

    def divergence_detection(
        self,
        base_events: List[Any],
        future_events: List[Any],
        max_tick: int = 20,
    ) -> Dict[str, Any]:
        """Find the exact tick where simulation diverges from reality.

        Args:
            base_events: Event history to replay.
            future_events: Future events to simulate.
            max_tick: Maximum ticks to check. Default 20.

        Returns:
            Dictionary with:
            - match: bool - whether all ticks matched
            - divergence_tick: int or None - first divergent tick
            - details: list of per-tick match results
        """
        details: List[str] = []
        divergence_tick: Optional[int] = None

        # Create fresh loop for real execution
        loop_real = self.engine_factory()
        for e in base_events:
            loop_real.event_bus.emit(e)
        for e in future_events:
            loop_real.event_bus.emit(e)

        # Run simulation sandbox separately
        sim_result = self.sandbox.run(base_events, future_events, max_ticks=max_tick)
        sim_event_ids = {getattr(e, "event_id", None) for e in sim_result.events}

        for tick_num in range(1, max_tick + 1):
            loop_real.tick()

            # Get real events at this tick
            real_events = loop_real.event_bus.history()
            real_event_ids = {getattr(e, "event_id", None) for e in real_events}

            # Compare at this tick level
            if sim_event_ids != real_event_ids and divergence_tick is None:
                divergence_tick = tick_num

            status = "DIVERGED" if divergence_tick and tick_num >= divergence_tick else "match"
            details.append(f"Tick {tick_num}: {status}")

        return {
            "match": divergence_tick is None,
            "divergence_tick": divergence_tick,
            "details": details,
        }