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


def build_memory_ui_summary(simulation_state: dict) -> dict:
    """Build compact memory UI summary for the player panel."""
    sim = _safe_dict(simulation_state)

    # Gather memory entries from various sources
    memory_entries: List[Dict[str, Any]] = []

    # Actor memories
    actor_memory = sim.get("actor_memory_state", {})
    if isinstance(actor_memory, dict):
        for actor_id, memories in actor_memory.items():
            if isinstance(memories, list):
                for m in memories[:5]:
                    if isinstance(m, dict):
                        memory_entries.append({
                            "source": str(actor_id),
                            "text": str(m.get("text") or m.get("content") or ""),
                            "strength": float(m.get("strength", 0.5)),
                            "category": "actor",
                        })

    # World memories
    world_memory = sim.get("world_memory_state", {})
    if isinstance(world_memory, dict):
        rumors = world_memory.get("rumors", [])
        if isinstance(rumors, list):
            for r in rumors[:5]:
                if isinstance(r, dict):
                    memory_entries.append({
                        "source": "world",
                        "text": str(r.get("text") or r.get("content") or ""),
                        "strength": float(r.get("strength", 0.5)),
                        "category": "world",
                    })

    # Sort by strength descending
    memory_entries.sort(key=lambda m: m.get("strength", 0), reverse=True)

    # Deduplicate by text
    seen: set = set()
    deduped: List[Dict[str, Any]] = []
    for m in memory_entries:
        text = m.get("text", "")
        if text and text not in seen:
            seen.add(text)
            deduped.append(m)

    # Build summary
    important = [m for m in deduped if m.get("strength", 0) >= 0.7][:3]
    recent = deduped[:5]

    # Recent world events from progression log or world state
    world_events: List[Dict[str, Any]] = []
    player_state = _safe_dict(sim.get("player_state"))
    prog_log = list(player_state.get("progression_log") or [])
    for entry in reversed(prog_log[-5:]):
        if isinstance(entry, dict):
            world_events.append({
                "type": str(entry.get("type", "")),
                "text": str(entry.get("source") or entry.get("type", "")),
            })

    return {
        "important_memory": important,
        "recent_memory": recent,
        "recent_world_events": world_events[:5],
        "total_memories": len(deduped),
        "expanded": deduped,
    }
