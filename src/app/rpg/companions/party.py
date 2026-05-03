from __future__ import annotations

from typing import Any, Dict, List

MAX_PARTY_MEMBERS = 6
MAX_COMPANION_HISTORY = 100


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def normalize_party_member(value: Dict[str, Any], *, npc_id: str = "") -> Dict[str, Any]:
    value = _safe_dict(value)
    normalized_npc_id = _safe_str(value.get("npc_id")) or npc_id
    return {
        "npc_id": normalized_npc_id,
        "status": _safe_str(value.get("status")) or "active",
        "joined_turn": _safe_int(value.get("joined_turn"), 0),
        "role": _safe_str(value.get("role")),
        "motivation": _safe_str(value.get("motivation")),
        "source_offer_id": _safe_str(value.get("source_offer_id")),
        "metadata": dict(_safe_dict(value.get("metadata"))),
    }


def normalize_companion_offer_record(value: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(value)
    return {
        "offer_id": _safe_str(value.get("offer_id")),
        "npc_id": _safe_str(value.get("npc_id")),
        "status": _safe_str(value.get("status")) or "unknown",
        "turn_index": _safe_int(value.get("turn_index"), 0),
        "reason": _safe_str(value.get("reason")),
        "details": dict(_safe_dict(value.get("details"))),
    }


def normalize_party_state(value: Dict[str, Any] | None) -> Dict[str, Any]:
    value = _safe_dict(value)
    members = {}
    for npc_id, row in _safe_dict(value.get("members")).items():
        npc_id = str(npc_id or "")
        if not npc_id:
            continue
        members[npc_id] = normalize_party_member(row, npc_id=npc_id)
    history = [
        normalize_companion_offer_record(row)
        for row in _safe_list(value.get("companion_offer_history"))
        if isinstance(row, dict)
    ][-MAX_COMPANION_HISTORY:]
    return {
        "version": 1,
        "members": members,
        "companion_offer_history": history,
        "max_party_members": MAX_PARTY_MEMBERS,
        "max_companion_history": MAX_COMPANION_HISTORY,
    }


def ensure_party_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    state = normalize_party_state(simulation_state.get("party_state"))
    simulation_state["party_state"] = state
    return state


def get_party_member(
    simulation_state: Dict[str, Any],
    npc_id: str,
) -> Dict[str, Any] | None:
    state = ensure_party_state(simulation_state)
    return state.get("members", {}).get(npc_id)


def is_party_member(simulation_state: Dict[str, Any], npc_id: str) -> bool:
    member = get_party_member(simulation_state, npc_id)
    return bool(member and member.get("status") == "active")


def add_party_member(
    simulation_state: Dict[str, Any],
    *,
    npc_id: str,
    role: str = "",
    motivation: str = "",
    source_offer_id: str = "",
    turn_index: int = 0,
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    state = ensure_party_state(simulation_state)
    members = state.setdefault("members", {})
    if npc_id in members and members[npc_id].get("status") == "active":
        return {
            "ok": True,
            "reason": "already_party_member",
            "npc_id": npc_id,
            "member": members[npc_id],
        }
    active_count = len([row for row in members.values() if row.get("status") == "active"])
    if active_count >= MAX_PARTY_MEMBERS:
        return {
            "ok": False,
            "reason": "party_full",
            "npc_id": npc_id,
            "active_count": active_count,
            "max_party_members": MAX_PARTY_MEMBERS,
        }
    member = normalize_party_member(
        {
            "npc_id": npc_id,
            "status": "active",
            "joined_turn": turn_index,
            "role": role,
            "motivation": motivation,
            "source_offer_id": source_offer_id,
            "metadata": metadata or {},
        },
        npc_id=npc_id,
    )
    members[npc_id] = member
    simulation_state["party_state"] = normalize_party_state(state)
    return {
        "ok": True,
        "reason": "party_member_added",
        "npc_id": npc_id,
        "member": simulation_state["party_state"]["members"][npc_id],
    }


def append_companion_offer_history(
    simulation_state: Dict[str, Any],
    *,
    offer_id: str,
    npc_id: str,
    status: str,
    turn_index: int = 0,
    reason: str = "",
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    state = ensure_party_state(simulation_state)
    history = list(state.get("companion_offer_history") or [])
    row = normalize_companion_offer_record(
        {
            "offer_id": offer_id,
            "npc_id": npc_id,
            "status": status,
            "turn_index": turn_index,
            "reason": reason,
            "details": details or {},
        }
    )
    history.append(row)
    state["companion_offer_history"] = history[-MAX_COMPANION_HISTORY:]
    simulation_state["party_state"] = normalize_party_state(state)
    return {
        "ok": True,
        "reason": "companion_offer_history_recorded",
        "record": row,
    }


def has_companion_offer_status(
    simulation_state: Dict[str, Any],
    *,
    offer_id: str,
    status: str,
) -> bool:
    state = ensure_party_state(simulation_state)
    return any(
        row.get("offer_id") == offer_id and row.get("status") == status
        for row in state.get("companion_offer_history") or []
    )