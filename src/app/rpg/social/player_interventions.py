from __future__ import annotations

from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def build_intervention_options(conversation: Dict[str, Any], simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    conversation = _safe_dict(conversation)
    participants = [x for x in (_safe_str(p) for p in conversation.get("participants") or []) if x]
    if not conversation.get("player_can_intervene") or len(participants) < 2:
        return []

    npc_index = _safe_dict(_safe_dict(simulation_state).get("npc_index"))
    a_name = _safe_str(_safe_dict(npc_index.get(participants[0])).get("name")) or participants[0]
    b_name = _safe_str(_safe_dict(npc_index.get(participants[1])).get("name")) or participants[1]

    return [
        {"id": f"support:{participants[0]}", "text": f"Support {a_name}", "effect": "trust_boost"},
        {"id": f"support:{participants[1]}", "text": f"Support {b_name}", "effect": "trust_boost"},
        {"id": "clarify", "text": "Ask for clarification", "effect": "respect_boost"},
        {"id": "end_discussion", "text": "End the discussion", "effect": "close_conversation"},
        {"id": "continue", "text": "Keep listening", "effect": "none"},
    ]


def _update_npc_belief(simulation_state: Dict[str, Any], npc_id: str, target_id: str, key: str, delta: float) -> None:
    """Mutate NPC belief in npc_minds for the given NPC."""
    npc_minds = simulation_state.setdefault("npc_minds", {}) if isinstance(simulation_state, dict) else {}
    if not isinstance(npc_minds, dict):
        npc_minds = {}
        simulation_state["npc_minds"] = npc_minds

    mind = npc_minds.setdefault(npc_id, {})
    if not isinstance(mind, dict):
        mind = {}
        npc_minds[npc_id] = mind
    beliefs = mind.setdefault("beliefs", {})
    if not isinstance(beliefs, dict):
        beliefs = {}
        mind["beliefs"] = beliefs
    record = beliefs.setdefault(target_id, {"trust": 0.0, "fear": 0.0, "respect": 0.0, "hostility": 0.0})
    if not isinstance(record, dict):
        record = {"trust": 0.0, "fear": 0.0, "respect": 0.0, "hostility": 0.0}
        beliefs[target_id] = record
    record[key] = _clamp(_safe_float(record.get(key), 0.0) + delta)


def apply_player_intervention(conversation_id: str, option_id: str, simulation_state: Dict[str, Any], runtime_state: Dict[str, Any], tick: int) -> Dict[str, Any]:
    runtime_state = runtime_state if isinstance(runtime_state, dict) else {}
    simulation_state = simulation_state if isinstance(simulation_state, dict) else {}

    runtime_state["last_conversation_intervention"] = {
        "conversation_id": _safe_str(conversation_id),
        "option_id": _safe_str(option_id),
        "tick": int(tick or 0),
    }

    # Find the conversation to get participants
    from .npc_conversations import ensure_conversation_state, get_conversation, close_conversation
    ensure_conversation_state(simulation_state)
    conv = _safe_dict(get_conversation(simulation_state, conversation_id))
    participants = [x for x in (_safe_str(p) for p in conv.get("participants") or []) if x]

    effects: List[str] = []

    option_id = _safe_str(option_id)
    if option_id.startswith("support:"):
        # Player supports one participant; boost trust with supported, reduce with others
        supported_id = option_id[len("support:"):]
        for npc_id in participants:
            if npc_id == supported_id:
                _update_npc_belief(simulation_state, npc_id, "player", "trust", 0.15)
                _update_npc_belief(simulation_state, npc_id, "player", "respect", 0.05)
                effects.append(f"trust_boost:{npc_id}")
            else:
                _update_npc_belief(simulation_state, npc_id, "player", "trust", -0.05)
                _update_npc_belief(simulation_state, npc_id, "player", "hostility", 0.05)
                effects.append(f"friction:{npc_id}")
    elif option_id == "clarify":
        # Asking for clarification boosts respect from all participants
        for npc_id in participants:
            _update_npc_belief(simulation_state, npc_id, "player", "respect", 0.10)
        effects.append("respect_all")
    elif option_id == "end_discussion":
        # End the conversation immediately
        if conversation_id:
            close_conversation(simulation_state, conversation_id, reason="player_ended")
        effects.append("conversation_closed")
    elif option_id == "continue":
        # No gameplay effect, player is just observing
        effects.append("none")

    return {
        "success": True,
        "conversation_id": _safe_str(conversation_id),
        "option_id": _safe_str(option_id),
        "tick": int(tick or 0),
        "effects": effects,
    }
