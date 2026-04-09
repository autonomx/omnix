from __future__ import annotations

from typing import Any, Dict


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def get_default_conversation_settings() -> Dict[str, Any]:
    return {
        "ambient_conversations_enabled": True,
        "party_reaction_interrupts_enabled": True,
        "player_intervention_enabled": True,
        "avg_conversation_turns": 4,
        "max_conversation_turns": 8,
        "min_ticks_between_ambient_conversations_per_location": 2,
        "max_active_conversations_per_location": 1,
        "llm_expand_npc_conversations": False,
    }


def resolve_conversation_settings(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    defaults = get_default_conversation_settings()
    sim_settings = _safe_dict(_safe_dict(simulation_state).get("conversation_settings"))
    runtime_settings = _safe_dict(_safe_dict(runtime_state).get("conversation_settings"))

    merged = dict(defaults)
    merged.update(sim_settings)
    merged.update(runtime_settings)

    return {
        "ambient_conversations_enabled": _safe_bool(merged.get("ambient_conversations_enabled"), True),
        "party_reaction_interrupts_enabled": _safe_bool(merged.get("party_reaction_interrupts_enabled"), True),
        "player_intervention_enabled": _safe_bool(merged.get("player_intervention_enabled"), True),
        "avg_conversation_turns": max(1, _safe_int(merged.get("avg_conversation_turns"), 4)),
        "max_conversation_turns": max(1, _safe_int(merged.get("max_conversation_turns"), 8)),
        "min_ticks_between_ambient_conversations_per_location": max(0, _safe_int(merged.get("min_ticks_between_ambient_conversations_per_location"), 2)),
        "max_active_conversations_per_location": max(1, _safe_int(merged.get("max_active_conversations_per_location"), 1)),
        "llm_expand_npc_conversations": _safe_bool(merged.get("llm_expand_npc_conversations"), False),
    }
