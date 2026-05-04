from __future__ import annotations

from typing import Any, Dict, List

MAX_STORY_PACK_ACTIVATION_HISTORY = 100


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _normalize_activation_row(value: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(value)
    return {
        "pack_id": _safe_str(value.get("pack_id")),
        "status": _safe_str(value.get("status")) or "inactive",
        "activated_turn": _safe_int(value.get("activated_turn"), 0),
        "deactivated_turn": _safe_int(value.get("deactivated_turn"), 0),
        "reason": _safe_str(value.get("reason")),
        "metadata": dict(_safe_dict(value.get("metadata"))),
    }


def _normalize_history_row(value: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(value)
    return {
        "pack_id": _safe_str(value.get("pack_id")),
        "action": _safe_str(value.get("action")),
        "turn_index": _safe_int(value.get("turn_index"), 0),
        "reason": _safe_str(value.get("reason")),
        "metadata": dict(_safe_dict(value.get("metadata"))),
    }


def normalize_story_pack_activation_state(value: Dict[str, Any] | None) -> Dict[str, Any]:
    value = _safe_dict(value)
    packs = {}
    for pack_id, row in _safe_dict(value.get("packs")).items():
        pack_id = str(pack_id or "")
        if not pack_id:
            continue
        normalized = _normalize_activation_row(row)
        normalized["pack_id"] = pack_id
        if normalized["status"] not in {"active", "inactive"}:
            normalized["status"] = "inactive"
        packs[pack_id] = normalized

    history = [
        _normalize_history_row(row)
        for row in _safe_list(value.get("history"))
        if isinstance(row, dict)
    ][-MAX_STORY_PACK_ACTIVATION_HISTORY:]

    return {
        "version": 1,
        "packs": packs,
        "history": history,
        "max_history": MAX_STORY_PACK_ACTIVATION_HISTORY,
    }


def ensure_story_pack_activation_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    state = normalize_story_pack_activation_state(simulation_state.get("story_pack_activation_state"))
    simulation_state["story_pack_activation_state"] = state
    return state


def _append_history(
    simulation_state: Dict[str, Any],
    *,
    pack_id: str,
    action: str,
    turn_index: int = 0,
    reason: str = "",
    metadata: Dict[str, Any] | None = None,
) -> None:
    state = ensure_story_pack_activation_state(simulation_state)
    history = list(state.get("history") or [])
    history.append(
        _normalize_history_row(
            {
                "pack_id": pack_id,
                "action": action,
                "turn_index": turn_index,
                "reason": reason,
                "metadata": metadata or {},
            }
        )
    )
    state["history"] = history[-MAX_STORY_PACK_ACTIVATION_HISTORY:]
    simulation_state["story_pack_activation_state"] = normalize_story_pack_activation_state(state)


def activate_story_pack(
    simulation_state: Dict[str, Any],
    pack_id: str,
    *,
    turn_index: int = 0,
    reason: str = "activated",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    pack_id = str(pack_id or "")
    if not pack_id:
        return {"ok": False, "reason": "missing_pack_id"}

    story_pack_state = _safe_dict(simulation_state.get("story_pack_state"))
    imported = _safe_dict(story_pack_state.get("imported_packs"))
    if pack_id not in imported:
        return {"ok": False, "reason": "story_pack_not_imported", "pack_id": pack_id}

    state = ensure_story_pack_activation_state(simulation_state)
    current = _safe_dict(state.get("packs", {}).get(pack_id))
    if current.get("status") == "active":
        return {
            "ok": True,
            "reason": "already_active",
            "pack_id": pack_id,
            "activation": current,
        }

    row = _normalize_activation_row(
        {
            "pack_id": pack_id,
            "status": "active",
            "activated_turn": turn_index,
            "deactivated_turn": 0,
            "reason": reason,
            "metadata": metadata or {},
        }
    )
    state.setdefault("packs", {})[pack_id] = row
    simulation_state["story_pack_activation_state"] = normalize_story_pack_activation_state(state)
    _append_history(
        simulation_state,
        pack_id=pack_id,
        action="activate",
        turn_index=turn_index,
        reason=reason,
        metadata=metadata,
    )
    return {
        "ok": True,
        "reason": "activated",
        "pack_id": pack_id,
        "activation": ensure_story_pack_activation_state(simulation_state)["packs"][pack_id],
    }


def deactivate_story_pack(
    simulation_state: Dict[str, Any],
    pack_id: str,
    *,
    turn_index: int = 0,
    reason: str = "deactivated",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    pack_id = str(pack_id or "")
    if not pack_id:
        return {"ok": False, "reason": "missing_pack_id"}

    state = ensure_story_pack_activation_state(simulation_state)
    current = _safe_dict(state.get("packs", {}).get(pack_id))
    if current.get("status") != "active":
        return {
            "ok": True,
            "reason": "already_inactive",
            "pack_id": pack_id,
            "activation": current or {"pack_id": pack_id, "status": "inactive"},
        }

    row = dict(current)
    row["status"] = "inactive"
    row["deactivated_turn"] = int(turn_index or 0)
    row["reason"] = reason
    row["metadata"] = dict(metadata or row.get("metadata") or {})
    state.setdefault("packs", {})[pack_id] = _normalize_activation_row(row)
    simulation_state["story_pack_activation_state"] = normalize_story_pack_activation_state(state)
    _append_history(
        simulation_state,
        pack_id=pack_id,
        action="deactivate",
        turn_index=turn_index,
        reason=reason,
        metadata=metadata,
    )
    return {
        "ok": True,
        "reason": "deactivated",
        "pack_id": pack_id,
        "activation": ensure_story_pack_activation_state(simulation_state)["packs"][pack_id],
    }


def is_story_pack_active(simulation_state: Dict[str, Any], pack_id: str) -> bool:
    state = ensure_story_pack_activation_state(simulation_state)
    return _safe_dict(state.get("packs", {}).get(str(pack_id or ""))).get("status") == "active"


def list_active_story_pack_ids(simulation_state: Dict[str, Any]) -> List[str]:
    state = ensure_story_pack_activation_state(simulation_state)
    return [
        pack_id
        for pack_id, row in _safe_dict(state.get("packs")).items()
        if _safe_dict(row).get("status") == "active"
    ]


def build_story_pack_activation_snapshot(simulation_state: Dict[str, Any], *, limit: int = 20) -> Dict[str, Any]:
    limit = max(0, min(50, int(limit or 20)))
    state = ensure_story_pack_activation_state(simulation_state)
    story_pack_state = _safe_dict(simulation_state.get("story_pack_state"))
    imported = _safe_dict(story_pack_state.get("imported_packs"))
    rows = []
    for pack_id, imported_pack in imported.items():
        activation = _safe_dict(state.get("packs", {}).get(pack_id))
        proposal = _safe_dict(_safe_dict(imported_pack).get("proposal"))
        rows.append(
            {
                "pack_id": str(pack_id),
                "proposal_id": str(proposal.get("proposal_id") or _safe_dict(imported_pack).get("proposal_id") or ""),
                "title": str(proposal.get("title") or _safe_dict(imported_pack).get("title") or ""),
                "status": activation.get("status") or "inactive",
                "activated_turn": int(activation.get("activated_turn") or 0),
                "deactivated_turn": int(activation.get("deactivated_turn") or 0),
                "reason": activation.get("reason") or "",
                "counts": {
                    "lore_entries": len(proposal.get("lore_entries") or []),
                    "story_arcs": len(proposal.get("story_arcs") or []),
                    "story_events": len(proposal.get("story_events") or []),
                    "escalation_rules": len(proposal.get("escalation_rules") or []),
                },
            }
        )
    rows.sort(key=lambda row: (row["status"] != "active", row["pack_id"]))
    return {
        "ok": True,
        "format_version": "story_pack_activation_snapshot_v1",
        "packs": rows[:limit],
        "active_pack_ids": list_active_story_pack_ids(simulation_state)[:limit],
        "history": list(state.get("history") or [])[-limit:],
        "bounded": {
            "limit": limit,
            "max_history": MAX_STORY_PACK_ACTIVATION_HISTORY,
        },
    }