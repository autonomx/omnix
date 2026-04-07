"""Phase 14.3 — Memory → Dialogue Injection.

Provides deterministic memory context extraction for dialogue payloads.
Actor memory + world rumors injected into presentation dialogue context.
Optional LLM-facing memory block generation without making LLM output authoritative.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.memory.actor_memory_state import ensure_actor_memory_state, get_actor_memory
from app.rpg.memory.world_memory_state import ensure_world_memory_state


_MAX_DIALOGUE_ACTOR_SHORT = 4
_MAX_DIALOGUE_ACTOR_LONG = 4
_MAX_DIALOGUE_RUMORS = 4


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


def _memory_sort_key(item: Dict[str, Any]) -> tuple:
    return (
        -(item.get("tick") if isinstance(item.get("tick"), int) else 0),
        _safe_str(item.get("summary")).lower(),
        _safe_str(item.get("id")),
    )


def build_actor_dialogue_memory_context(
    simulation_state: Dict[str, Any],
    actor_id: str,
) -> Dict[str, Any]:
    """Build memory context for a single actor's dialogue."""
    simulation_state = ensure_actor_memory_state(_safe_dict(simulation_state))
    actor_memory = get_actor_memory(simulation_state, actor_id)

    short_term = sorted(
        [item for item in _safe_list(actor_memory.get("short_term")) if isinstance(item, dict)],
        key=_memory_sort_key,
    )[:_MAX_DIALOGUE_ACTOR_SHORT]

    long_term = sorted(
        [item for item in _safe_list(actor_memory.get("long_term")) if isinstance(item, dict)],
        key=_memory_sort_key,
    )[:_MAX_DIALOGUE_ACTOR_LONG]

    return {
        "actor_id": _safe_str(actor_id).strip(),
        "short_term": short_term,
        "long_term": long_term,
    }


def build_world_dialogue_memory_context(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Build world memory context for dialogue."""
    simulation_state = ensure_world_memory_state(_safe_dict(simulation_state))
    memory_state = _safe_dict(simulation_state.get("memory_state"))
    rumors = sorted(
        [item for item in _safe_list(memory_state.get("rumors")) if isinstance(item, dict)],
        key=_memory_sort_key,
    )[:_MAX_DIALOGUE_RUMORS]

    return {
        "rumors": rumors,
    }


def build_dialogue_memory_context(
    simulation_state: Dict[str, Any],
    actor_ids: List[str],
) -> Dict[str, Any]:
    """Build complete dialogue memory context for all actors and world."""
    simulation_state = _safe_dict(simulation_state)
    actor_contexts = [
        build_actor_dialogue_memory_context(simulation_state, actor_id)
        for actor_id in actor_ids
        if _safe_str(actor_id).strip()
    ]
    return {
        "actors": actor_contexts,
        "world": build_world_dialogue_memory_context(simulation_state),
    }


def build_llm_memory_prompt_block(memory_context: Dict[str, Any]) -> str:
    """Generate an LLM-facing memory prompt block from dialogue memory context."""
    memory_context = _safe_dict(memory_context)
    actor_blocks = []
    for actor in _safe_list(memory_context.get("actors")):
        actor = _safe_dict(actor)
        actor_id = _safe_str(actor.get("actor_id")).strip() or "unknown"
        short_term = [
            f"- {_safe_str(item.get('summary')).strip()}"
            for item in _safe_list(actor.get("short_term"))
            if _safe_str(_safe_dict(item).get("summary")).strip()
        ]
        long_term = [
            f"- {_safe_str(item.get('summary')).strip()}"
            for item in _safe_list(actor.get("long_term"))
            if _safe_str(_safe_dict(item).get("summary")).strip()
        ]
        block = [f"[Actor Memory: {actor_id}]"]
        if short_term:
            block.append("Recent:")
            block.extend(short_term)
        if long_term:
            block.append("Established:")
            block.extend(long_term)
        actor_blocks.append("\n".join(block))

    world_rumors = [
        f"- {_safe_str(_safe_dict(item).get('summary')).strip()}"
        for item in _safe_list(_safe_dict(memory_context.get("world")).get("rumors"))
        if _safe_str(_safe_dict(item).get("summary")).strip()
    ]

    parts = []
    if actor_blocks:
        parts.append("\n\n".join(actor_blocks))
    if world_rumors:
        parts.append("[World Rumors]\n" + "\n".join(world_rumors))
    return "\n\n".join(parts).strip()