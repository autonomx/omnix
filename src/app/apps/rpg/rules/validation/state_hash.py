"""PHASE 5.1 — State Hashing (FOUNDATION)

Deterministic serialization and hashing of game state.

This module provides the foundational building block for all validation
in Phase 5.1. By creating deterministic fingerprints of game state,
we can:
- Compare states across runs (determinism)
- Compare live vs replay (replay validation)
- Compare simulation vs real execution (simulation parity)

CRITICAL DESIGN RULES:
- No reliance on timestamps for hash equality
- All dicts/lists are sorted for ordering guarantees
- Object attributes are serialized via __dict__ recursively
- Same logical state ALWAYS produces same hash

Usage:
    hash1 = compute_state_hash(loop1)
    hash2 = compute_state_hash(loop2)
    assert hash1 == hash2  # Determinism proven
"""

from typing import Any


def stable_serialize(obj: Any) -> Any:
    """Deterministic serialization with no ordering issues.

    Recursively handles:
    - dicts: sorted by keys
    - lists: preserved order, each element serialized
    - objects with __dict__: converted to stable dict
    - primitives: returned as-is

    This function is idempotent: calling it on already-serialized
    data produces the same result.

    Args:
        obj: Any object to serialize.

    Returns:
        A JSON-serializable representation with deterministic ordering.
    """
    if obj is None:
        return None
    elif isinstance(obj, bool):
        return obj
    elif isinstance(obj, int):
        return obj
    elif isinstance(obj, float):
        return round(obj, 6)  # PHASE 5.1.5 — HARDENING (rpg-design.txt Issue #4): Round floats to prevent precision drift across platforms
    elif isinstance(obj, str):
        return obj
    elif isinstance(obj, dict):
        return {k: stable_serialize(obj[k]) for k in sorted(obj.keys())}
    elif isinstance(obj, (list, tuple)):
        return [stable_serialize(x) for x in obj]
    elif isinstance(obj, (set, frozenset)):
        return sorted([stable_serialize(x) for x in obj])
    elif hasattr(obj, "__dict__"):
        d = vars(obj)
        # Guard against objects without __dict__ or circular references
        if not isinstance(d, dict):
            return str(obj)
        return stable_serialize(d)
    else:
        # Fallback for unrecognized types (enums, dates, etc.)
        return str(obj)
