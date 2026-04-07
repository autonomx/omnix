"""Phase 14.4 — Memory decay / reinforcement engine (canonical).

Deterministic, bounded decay and reinforcement for session memory state.
Ensures predictable behavior with deduplication and length caps.
"""
from __future__ import annotations

from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def decay_memory_state(
    simulation_state: Dict[str, Any],
    decay_step: float = 0.05,
    min_strength: float = 0.0,
) -> Dict[str, Any]:
    """Apply one deterministic decay pass to all memory entries.

    - Actor memory entries decay individually, bounded [0.0, 1.0]
    - World rumors decay and are deduplicated by text
    - All collections are re-sorted and capped to 50 entries
    """
    simulation_state = _safe_dict(simulation_state)
    memory_state = _safe_dict(simulation_state.get("memory_state"))

    # Decay actor memories
    actor_memory = _safe_dict(memory_state.get("actor_memory"))
    new_actor_memory: Dict[str, Any] = {}
    for actor_id, bucket in actor_memory.items():
        bucket = _safe_dict(bucket)
        entries = bucket.get("entries", [])
        if not isinstance(entries, list):
            entries = []

        new_entries: List[Dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            strength = _clamp(float(entry.get("strength") or 0.0) - decay_step, min_strength)
            new_entry = dict(entry)
            new_entry["strength"] = strength
            new_entries.append(new_entry)

        # Sort deterministically and cap
        new_entries.sort(
            key=lambda item: (
                -float(item.get("strength") or 0.0),
                _safe_str(item.get("text")).strip(),
            )
        )
        new_entries = new_entries[:50]
        bucket["entries"] = new_entries
        new_actor_memory[actor_id] = bucket

    # Decay world rumors
    world_memory = _safe_dict(memory_state.get("world_memory"))
    rumors = world_memory.get("rumors", [])
    if not isinstance(rumors, list):
        rumors = []

    new_rumors: List[Dict[str, Any]] = []
    for rumor in rumors:
        if not isinstance(rumor, dict):
            continue
        strength = _clamp(float(rumor.get("strength") or 0.0) - decay_step, min_strength)
        new_rumor = dict(rumor)
        new_rumor["strength"] = strength
        new_rumors.append(new_rumor)

    # Deduplicate rumors by text (keep highest strength)
    deduped: Dict[str, Dict[str, Any]] = {}
    for item in new_rumors:
        key = _safe_str(item.get("text")).strip()
        if not key:
            continue
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = item
        else:
            if float(item.get("strength") or 0.0) > float(existing.get("strength") or 0.0):
                deduped[key] = item
    new_rumors = list(deduped.values())

    # Sort deterministically and cap
    new_rumors.sort(
        key=lambda item: (
            -float(item.get("strength") or 0.0),
            -int(item.get("reach") or 0),
            _safe_str(item.get("text")).strip(),
        )
    )
    new_rumors = new_rumors[:50]
    world_memory["rumors"] = new_rumors

    memory_state["actor_memory"] = new_actor_memory
    memory_state["world_memory"] = world_memory
    simulation_state["memory_state"] = memory_state
    return simulation_state


def reinforce_actor_memory(
    simulation_state: Dict[str, Any],
    actor_id: str,
    text: str,
    amount: float = 0.2,
    max_entries: int = 50,
) -> Dict[str, Any]:
    """Reinforce (or add) an actor memory entry by text.

    - If entry exists, increases strength by amount (clamped to 1.0)
    - If entry does not exist, creates new entry at given strength
    - Re-sorts and caps entries deterministically
    """
    simulation_state = _safe_dict(simulation_state)
    memory_state = _safe_dict(simulation_state.get("memory_state"))
    actor_memory = _safe_dict(memory_state.get("actor_memory"))

    actor_id = _safe_str(actor_id).strip()
    text = _safe_str(text).strip()
    amount = float(amount)

    bucket = _safe_dict(actor_memory.get(actor_id))
    entries = bucket.get("entries", [])
    if not isinstance(entries, list):
        entries = []

    found = False
    new_entries: List[Dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_text = _safe_str(entry.get("text")).strip()
        if entry_text == text:
            strength = _clamp(float(entry.get("strength") or 0.0) + amount)
            entry = dict(entry)
            entry["strength"] = strength
            found = True
        new_entries.append(entry)

    if not found:
        new_entries.append({
            "text": text,
            "strength": _clamp(amount),
        })

    # Sort deterministically and cap
    new_entries.sort(
        key=lambda item: (
            -float(item.get("strength") or 0.0),
            _safe_str(item.get("text")).strip(),
        )
    )
    new_entries = new_entries[:max_entries]

    bucket["entries"] = new_entries
    actor_memory[actor_id] = bucket
    memory_state["actor_memory"] = actor_memory
    simulation_state["memory_state"] = memory_state
    return simulation_state