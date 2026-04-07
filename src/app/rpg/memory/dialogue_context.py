"""Phase 14.3 — Dialogue memory context builder (canonical).

Builds deterministic, bounded memory context for dialogue injection.
Ensures stable ordering and prompt-safe text sizes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Union

ActorIds = Union[str, List[str]]


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _score_memory(item: Dict[str, Any]) -> tuple:
    """Deterministic sort key: strength desc, then updated_at, then text."""
    item = _safe_dict(item)
    strength = float(item.get("strength") or 0.0)
    updated_at = _safe_str(item.get("updated_at")).strip()
    text = _safe_str(item.get("text")).strip()
    return (-strength, updated_at, text)


def build_dialogue_memory_context(
    simulation_state: Dict[str, Any],
    actor_ids: ActorIds,
) -> Dict[str, Any]:
    """Build dialogue memory context for one or more actors.

    Returns deterministic, bounded output suitable for LLM prompt injection.
    """
    if isinstance(actor_ids, str):
        actor_ids = [actor_ids]

    simulation_state = _safe_dict(simulation_state)
    memory_state = _safe_dict(simulation_state.get("memory_state"))
    actor_memory = _safe_dict(memory_state.get("actor_memory"))
    world_memory = _safe_dict(memory_state.get("world_memory"))

    collected_actor_memory: List[Dict[str, Any]] = []
    for aid in actor_ids:
        aid = _safe_str(aid).strip()
        if not aid:
            continue
        entries = _safe_dict(actor_memory.get(aid)).get("entries", [])
        if not isinstance(entries, list):
            entries = []
        for entry in entries:
            if isinstance(entry, dict):
                collected_actor_memory.append(entry)

    # Deterministic sort by strength, then text
    collected_actor_memory.sort(key=_score_memory)
    # Cap total entries
    collected_actor_memory = collected_actor_memory[:50]

    world_rumors = world_memory.get("rumors", [])
    if not isinstance(world_rumors, list):
        world_rumors = []
    world_rumors = [r for r in world_rumors if isinstance(r, dict)]
    # Sort rumors deterministically
    world_rumors.sort(key=lambda item: (
        -float(item.get("strength") or 0.0),
        _safe_str(item.get("text")).strip(),
    ))
    world_rumors = world_rumors[:25]

    return {
        "actor_memory": collected_actor_memory,
        "world_rumors": world_rumors,
        "actor_ids": [_safe_str(a).strip() for a in actor_ids if _safe_str(a).strip()],
    }


def build_llm_memory_prompt_block(
    dialogue_memory_context: Dict[str, Any],
) -> str:
    """Build a bounded text block for LLM memory prompt injection.

    Capped at 16 lines total, each text field bounded to 240 chars.
    """
    dialogue_memory_context = _safe_dict(dialogue_memory_context)
    lines: List[str] = []

    actor_memory = dialogue_memory_context.get("actor_memory", [])
    if isinstance(actor_memory, list):
        for item in actor_memory:
            item = _safe_dict(item)
            text = _safe_str(item.get("text")).strip()[:240]
            strength = item.get("strength", 0.0)
            if text:
                lines.append(f"[Memory] (s={strength}) {text}")

    world_rumors = dialogue_memory_context.get("world_rumors", [])
    if isinstance(world_rumors, list):
        for item in world_rumors:
            item = _safe_dict(item)
            text = _safe_str(item.get("text")).strip()[:240]
            strength = item.get("strength", 0.0)
            if text:
                lines.append(f"[Rumor] (s={strength}) {text}")

    # Cap total lines to keep prompt bounded
    if len(lines) > 16:
        lines = lines[:16]

    return "\n".join(lines) if lines else "(no memory context)"