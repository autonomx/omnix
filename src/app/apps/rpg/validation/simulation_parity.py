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
from typing import Any, Callable, Dict, List

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

