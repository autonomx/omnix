"""Phase 14.0 — Memory system module.

Provides bounded short-term, long-term, and world memory lanes.
Memory is stateful but never grows unbounded.
"""
from __future__ import annotations

from typing import Any, Dict, List

_MAX_SHORT_TERM = 12
_MAX_LONG_TERM = 24
_MAX_WORLD_MEMORY = 32


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _normalize_memory_entry(value: Any) -> Dict[str, Any]:
    """Normalize a single memory entry into bounded deterministic state."""
    data = _safe_dict(value)
    return {
        "id": _safe_str(data.get("id")).strip(),
        "summary": _safe_str(data.get("summary")).strip(),
        "kind": _safe_str(data.get("kind")).strip() or "fact",
        "tick": int(data.get("tick")) if isinstance(data.get("tick"), int) else 0,
    }


def ensure_memory_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure memory_state exists with all three bounded lanes."""
    simulation_state = _safe_dict(simulation_state)
    memory_state = simulation_state.get("memory_state")
    if not isinstance(memory_state, dict):
        memory_state = {}
        simulation_state["memory_state"] = memory_state

    short_term = [
        _normalize_memory_entry(item)
        for item in _safe_list(memory_state.get("short_term"))
        if isinstance(item, dict)
    ][-_MAX_SHORT_TERM:]

    long_term = [
        _normalize_memory_entry(item)
        for item in _safe_list(memory_state.get("long_term"))
        if isinstance(item, dict)
    ][-_MAX_LONG_TERM:]

    world_memory = [
        _normalize_memory_entry(item)
        for item in _safe_list(memory_state.get("world_memory"))
        if isinstance(item, dict)
    ][-_MAX_WORLD_MEMORY:]

    memory_state["short_term"] = short_term
    memory_state["long_term"] = long_term
    memory_state["world_memory"] = world_memory
    return simulation_state


def append_short_term_memory(simulation_state: Dict[str, Any], entry: Dict[str, Any]) -> Dict[str, Any]:
    """Append entry to short-term memory lane (bounded)."""
    simulation_state = ensure_memory_state(simulation_state)
    memory_state = _safe_dict(simulation_state.get("memory_state"))
    items = _safe_list(memory_state.get("short_term"))
    items.append(_normalize_memory_entry(entry))
    memory_state["short_term"] = items[-_MAX_SHORT_TERM:]
    return simulation_state


def append_long_term_memory(simulation_state: Dict[str, Any], entry: Dict[str, Any]) -> Dict[str, Any]:
    """Append entry to long-term memory lane (bounded)."""
    simulation_state = ensure_memory_state(simulation_state)
    memory_state = _safe_dict(simulation_state.get("memory_state"))
    items = _safe_list(memory_state.get("long_term"))
    items.append(_normalize_memory_entry(entry))
    memory_state["long_term"] = items[-_MAX_LONG_TERM:]
    return simulation_state


def append_world_memory(simulation_state: Dict[str, Any], entry: Dict[str, Any]) -> Dict[str, Any]:
    """Append entry to world memory lane (bounded, shared/rumor style)."""
    simulation_state = ensure_memory_state(simulation_state)
    memory_state = _safe_dict(simulation_state.get("memory_state"))
    items = _safe_list(memory_state.get("world_memory"))
    items.append(_normalize_memory_entry(entry))
    memory_state["world_memory"] = items[-_MAX_WORLD_MEMORY:]
    return simulation_state