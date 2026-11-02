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
from typing import Any

from app.runtime.clock import current_turn_context

# Bump this only when intentionally changing deterministic event identity rules.


def rng_seed_from_session_id(session_id: str) -> int:
    """Derive the stable 64-bit RNG seed used to upcast pre-seed sessions."""

    session_id = str(session_id)
    if not session_id.strip():
        raise ValueError("session_id is required to derive the RPG RNG seed")
    return int.from_bytes(hashlib.sha256(session_id.encode("utf-8")).digest()[:8], "big")


def rng_for(
    session_seed: int,
    turn_index: int,
    purpose: str,
    sub_index: int = 0,
) -> random.Random:
    """Create a replay-stable RNG stream for one named turn decision."""

    if (
        not isinstance(turn_index, int)
        or isinstance(turn_index, bool)
        or not isinstance(sub_index, int)
        or isinstance(sub_index, bool)
        or turn_index < 0
        or sub_index < 0
    ):
        raise ValueError("turn_index and sub_index must be non-negative")
    if not isinstance(session_seed, int) or isinstance(session_seed, bool) or not 0 <= session_seed < 2**64:
        raise ValueError("session_seed must be an unsigned 64-bit integer")
    if not isinstance(purpose, str) or not purpose.strip():
        raise ValueError("purpose is required for a deterministic RPG RNG stream")
    material = f"{session_seed}:{turn_index}:{purpose}:{sub_index}".encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    return random.Random(seed)


def stable_sub_index(value: Any) -> int:
    """Derive a stable stream index from a JSON-safe decision subject."""

    digest = hashlib.sha256(stable_json(value).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def deterministic_rng(purpose: str, subject: Any = None) -> random.Random:
    """A named decision stream: the active turn's, or outside a turn one fixed by purpose and subject (RQ-4.6).

    Use it wherever game or narration code would otherwise reach for module-level ``random``.
    """
    sub_index = stable_sub_index(subject) if subject is not None else 0
    context = current_turn_context()
    if context is not None and context.session_seed is not None and context.turn_index is not None:
        return rng_for(context.session_seed, context.turn_index, purpose, sub_index)
    material = f"outside-turn:{purpose}:{sub_index}".encode("utf-8")
    return random.Random(int.from_bytes(hashlib.sha256(material).digest()[:8], "big"))


@dataclass
class DeterminismConfig:
    """Configuration for deterministic execution.

    Attributes:
        seed: Random seed for seeded RNG.
        strict_replay: If True, fail hard on missing replay data.
        replay_mode: If True, the system is in replay mode (no fresh side effects).
        record_llm: If True, record LLM prompt/response pairs during live runs.
        use_recorded_llm: If True, use recorded LLM responses instead of calling LLM.
        record_tools: If True, record tool/runtime call results during live runs.
        use_recorded_tools: If True, use recorded tool results instead of live calls.
        record_host: If True, record host/runtime boundary results during live runs.
        use_recorded_host: If True, use recorded host/runtime results instead of live calls.
    """
    seed: int = 0
    strict_replay: bool = True
    replay_mode: bool = False
    record_llm: bool = False
    use_recorded_llm: bool = False
    record_tools: bool = False
    use_recorded_tools: bool = False
    record_host: bool = False
    use_recorded_host: bool = False


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
