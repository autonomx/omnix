"""Phase 14.4 — Memory Decay / Reinforcement.

Add a deterministic maintenance pass for:
- short-term actor memory
- long-term actor memory
- generic memory lanes
- rumors

No probabilistic forgetting. Decay is a pure state transformation:
- no randomness
- same input state → same output state
- bounded outputs
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.memory.actor_memory_state import ensure_actor_memory_state
from app.rpg.memory.memory_state import ensure_memory_state
from app.rpg.memory.world_memory_state import ensure_world_memory_state


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


def _safe_int(value: Any, default: int = 0) -> int:
    return value if isinstance(value, int) else default


def _decay_entries(entries: List[Dict[str, Any]], *, current_tick: int, max_age: int) -> List[Dict[str, Any]]:
    """Remove entries older than max_age ticks."""
    out = []
    for item in _safe_list(entries):
        item = _safe_dict(item)
        tick = _safe_int(item.get("tick"), 0)
        age = max(0, current_tick - tick)
        if age <= max_age:
            out.append(item)
    return out


def _reinforce_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate entries by summary, keeping the most recent tick."""
    seen: Dict[str, Dict[str, Any]] = {}
    for raw in _safe_list(entries):
        item = _safe_dict(raw)
        key = _safe_str(item.get("summary")).strip().lower()
        if not key:
            continue
        if key not in seen:
            seen[key] = item
        else:
            existing = seen[key]
            existing_tick = _safe_int(existing.get("tick"), 0)
            new_tick = _safe_int(item.get("tick"), 0)
            if new_tick > existing_tick:
                seen[key] = item
    return list(seen.values())


def apply_memory_decay(simulation_state: Dict[str, Any], *, current_tick: int) -> Dict[str, Any]:
    """Apply deterministic decay/reinforcement pass to all memory state."""
    simulation_state = ensure_memory_state(_safe_dict(simulation_state))
    simulation_state = ensure_actor_memory_state(simulation_state)
    simulation_state = ensure_world_memory_state(simulation_state)

    memory_state = _safe_dict(simulation_state.get("memory_state"))

    # Decay and reinforce global memory lanes
    memory_state["short_term"] = _reinforce_entries(
        _decay_entries(_safe_list(memory_state.get("short_term")), current_tick=current_tick, max_age=12)
    )
    memory_state["long_term"] = _reinforce_entries(
        _decay_entries(_safe_list(memory_state.get("long_term")), current_tick=current_tick, max_age=999999)
    )
    memory_state["world_memory"] = _reinforce_entries(
        _decay_entries(_safe_list(memory_state.get("world_memory")), current_tick=current_tick, max_age=64)
    )

    # Decay and reinforce actor-specific memory
    actor_memory = _safe_dict(memory_state.get("actor_memory"))
    actor_out = {}
    for actor_id, payload in sorted(actor_memory.items(), key=lambda kv: _safe_str(kv[0])):
        payload = _safe_dict(payload)
        actor_out[_safe_str(actor_id)] = {
            "short_term": _reinforce_entries(
                _decay_entries(_safe_list(payload.get("short_term")), current_tick=current_tick, max_age=10)
            ),
            "long_term": _reinforce_entries(
                _decay_entries(_safe_list(payload.get("long_term")), current_tick=current_tick, max_age=999999)
            ),
        }
    memory_state["actor_memory"] = actor_out

    # Decay and adjust rumors (reach decreases with age, removed after 48 ticks)
    rumors = _safe_list(memory_state.get("rumors"))
    rumor_out = []
    for raw in rumors:
        rumor = _safe_dict(raw)
        tick = _safe_int(rumor.get("tick"), 0)
        age = max(0, current_tick - tick)
        if age > 48:
            continue
        reach = _safe_int(rumor.get("reach"), 0)
        rumor["reach"] = max(0, reach - (1 if age > 12 else 0))
        rumor_out.append(rumor)
    memory_state["rumors"] = rumor_out[-32:]

    return simulation_state