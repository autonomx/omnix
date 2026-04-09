from __future__ import annotations

from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def build_intervention_options(conversation: Dict[str, Any], simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    conversation = _safe_dict(conversation)
    participants = [x for x in (_safe_str(p) for p in conversation.get("participants") or []) if x]
    if not conversation.get("player_can_intervene") or len(participants) < 2:
        return []

    a = participants[0]
    b = participants[1]

    return [
        {"id": f"support:{a}", "text": f"Support {a}"},
        {"id": f"support:{b}", "text": f"Support {b}"},
        {"id": "clarify", "text": "Ask for clarification"},
        {"id": "end_discussion", "text": "End the discussion"},
        {"id": "continue", "text": "Keep listening"},
    ]


def apply_player_intervention(conversation_id: str, option_id: str, simulation_state: Dict[str, Any], runtime_state: Dict[str, Any], tick: int) -> Dict[str, Any]:
    runtime_state = runtime_state if isinstance(runtime_state, dict) else {}
    runtime_state["last_conversation_intervention"] = {
        "conversation_id": _safe_str(conversation_id),
        "option_id": _safe_str(option_id),
        "tick": int(tick or 0),
    }
    return {
        "success": True,
        "conversation_id": _safe_str(conversation_id),
        "option_id": _safe_str(option_id),
        "tick": int(tick or 0),
    }
