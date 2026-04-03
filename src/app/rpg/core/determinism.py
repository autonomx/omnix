"""Deterministic identity primitives for the RPG event system.

This module provides:
- DeterminismConfig: Configuration for deterministic execution
- SeededRNG: Per-engine seeded RNG (never use module-level random directly)
- stable_json: Deterministic JSON serialization
- compute_deterministic_event_id: SHA256-based deterministic event IDs

DESIGN RULES:
- Event identity is derived from causal history, not process-global state
- All replay/live/sandbox engines must use the same seed for equivalence
- Module-level random should NEVER be used for game logic
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from typing import Any, Dict, Optional


# Bump this only when intentionally changing deterministic event identity rules.
IDENTITY_VERSION = 1


@dataclass
class DeterminismConfig:
    """Configuration for deterministic execution.

    Attributes:
        seed: Random seed for seeded RNG.
        strict_replay: If True, fail hard on missing replay data.
        replay_mode: If True, the system is in replay mode (no fresh side effects).
        record_llm: If True, record LLM prompt/response pairs during live runs.
        use_recorded_llm: If True, use recorded LLM responses instead of calling LLM.
    """
    seed: int = 0
    strict_replay: bool = True
    replay_mode: bool = False
    record_llm: bool = False
    use_recorded_llm: bool = False


class SeededRNG:
    """Per-engine seeded RNG. Never use module-level random directly."""

    def __init__(self, seed: int = 0):
        self._seed = seed
        self._rng = random.Random(seed)

    @property
    def seed(self) -> int:
        return self._seed

    def randint(self, a: int, b: int) -> int:
        return self._rng.randint(a, b)

    def random(self) -> float:
        return self._rng.random()

    def choice(self, seq):
        if not seq:
            raise IndexError("Cannot choose from empty sequence")
        return seq[self._rng.randrange(len(seq))]

    def shuffle(self, x) -> None:
        self._rng.shuffle(x)

    def getstate(self):
        """Expose underlying RNG state for snapshots."""
        return self._rng.getstate()

    def setstate(self, state) -> None:
        """Restore underlying RNG state from snapshots."""
        self._rng.setstate(state)

    def serialize_state(self) -> Dict[str, Any]:
        return {"state": self._rng.getstate(), "seed": self._seed}

    def deserialize_state(self, state: Dict[str, Any]) -> None:
        self._rng.setstate(state["state"])


def stable_json(obj: Any) -> str:
    """Deterministic JSON serialization."""
    def normalize(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: normalize(v[k]) for k in sorted(v)}
        if isinstance(v, list):
            return [normalize(x) for x in v]
        if isinstance(v, set):
            return [normalize(x) for x in sorted(v, key=lambda i: repr(i))]
        if isinstance(v, float):
            return round(v, 6)
        if hasattr(v, "__dict__"):
            return normalize(vars(v))
        return v

    return json.dumps(normalize(obj), sort_keys=True, separators=(",", ":"))


def compute_deterministic_event_id(
    *,
    seed: int,
    event_type: str,
    payload: Dict[str, Any],
    source: Optional[str],
    parent_id: Optional[str],
    tick: Optional[int],
    seq: int,
) -> str:
    """
    Deterministic event identity derived from causal input, not process-global state.

    Identity is execution-path based, not semantic-equivalence based.
    That means:
    same seed + same canonical payload + same parent + same tick + same seq
    => same event_id
    """
    data = {
        "v": IDENTITY_VERSION,
        "seed": seed,
        "type": event_type,
        "payload": payload,
        "source": source,
        "parent_id": parent_id,
        "tick": tick,
        "seq": seq,
    }
    digest = hashlib.sha256(stable_json(data).encode()).hexdigest()
    return f"evt_{digest[:20]}"