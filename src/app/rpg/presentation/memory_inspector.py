"""Phase 16.2 — Memory inspector builder."""
from __future__ import annotations

from typing import Any, Dict, List


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def build_memory_inspector_payload(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    memory_state = _safe_dict(simulation_state.get("memory_state"))

    actor_memory = _safe_dict(memory_state.get("actor_memory"))
    actor_rows = []
    for actor_id in sorted(actor_memory.keys()):
        bucket = _safe_dict(actor_memory.get(actor_id))
        entries = [_safe_dict(item) for item in _safe_list(bucket.get("entries"))]
        entries.sort(key=lambda item: (-float(item.get("strength") or 0.0), _safe_str(item.get("text")).strip()))
        actor_rows.append(
            {
                "actor_id": actor_id,
                "entry_count": len(entries),
                "entries": entries[:20],
            }
        )

    world_memory = _safe_dict(memory_state.get("world_memory"))
    rumors = [_safe_dict(item) for item in _safe_list(world_memory.get("rumors"))]
    rumors.sort(key=lambda item: (-float(item.get("strength") or 0.0), -int(item.get("reach") or 0), _safe_str(item.get("text")).strip()))

    return {
        "actor_memory": actor_rows,
        "world_rumors": rumors[:50],
        "actions": {
            "reinforce_route": "/api/rpg/memory/reinforce",
            "decay_route": "/api/rpg/memory/decay",
        },
    }
