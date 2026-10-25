"""Deterministic RPG memory schema and post-turn writer.

This module is intentionally pure: callers pass a session snapshot plus the
resolved turn payload and receive a copied session with memory entries appended.
Later slices can wire the writer into runtime persistence, retrieval, prompt
context, reports, and grounding guards without changing the schema contract.
"""
from __future__ import annotations

from typing import Any, Dict
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict, safe_list as _safe_list

MEMORY_SCHEMA_VERSION = "rpg_memory_v1"
MAX_MEMORY_TEXT = 500


def memory_state_from_session(session: Dict[str, Any]) -> Dict[str, Any]:
    """Return a normalized memory state from a session snapshot."""
    runtime = _safe_dict(_safe_dict(session).get("runtime_state"))
    memory = _safe_dict(runtime.get("memory"))
    entries = [entry for entry in _safe_list(memory.get("entries")) if isinstance(entry, dict)]
    next_sequence = memory.get("next_sequence")
    if not isinstance(next_sequence, int) or next_sequence < 1:
        next_sequence = len(entries) + 1
    return {
        "version": MEMORY_SCHEMA_VERSION,
        "next_sequence": next_sequence,
        "entries": [dict(entry) for entry in entries],
    }
