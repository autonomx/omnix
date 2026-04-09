from __future__ import annotations

from typing import Any, Dict, List

from .npc_conversations import (
    get_conversation_lines,
    list_active_conversations,
    list_recent_conversations,
)
from .player_interventions import build_intervention_options


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_conversation_payload(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any], location_id: str = "") -> Dict[str, Any]:
    active = list_active_conversations(simulation_state, location_id=location_id)
    recent = list_recent_conversations(simulation_state, location_id=location_id)

    active_payload: List[Dict[str, Any]] = []
    for conv in active:
        cid = conv.get("conversation_id")
        active_payload.append({
            "conversation_id": cid,
            "kind": conv.get("kind"),
            "topic": conv.get("topic"),
            "participants": conv.get("participants") or [],
            "turn_count": int(conv.get("turn_count", 0) or 0),
            "max_turns": int(conv.get("max_turns", 0) or 0),
            "player_can_intervene": bool(conv.get("player_can_intervene")),
            "lines": get_conversation_lines(simulation_state, cid),
            "intervention_options": build_intervention_options(conv, simulation_state, runtime_state),
        })

    recent_payload: List[Dict[str, Any]] = []
    for conv in recent[-10:]:
        cid = conv.get("conversation_id")
        recent_payload.append({
            "conversation_id": cid,
            "kind": conv.get("kind"),
            "topic": conv.get("topic"),
            "participants": conv.get("participants") or [],
            "lines": get_conversation_lines(simulation_state, cid),
            "close_reason": conv.get("close_reason", ""),
        })

    return {
        "active_conversations": active_payload,
        "recent_conversations": recent_payload,
    }
