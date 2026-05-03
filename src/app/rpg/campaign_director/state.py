from __future__ import annotations

from typing import Any, Dict, List


MAX_DIRECTOR_TICK_HISTORY = 100


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    return default


def normalize_director_tick_record(value: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(value)
    return {
        "turn_index": _safe_int(value.get("turn_index"), 0),
        "mode": str(value.get("mode") or ""),
        "eligible_count": _safe_int(value.get("eligible_count"), 0),
        "applied_count": _safe_int(value.get("applied_count"), 0),
        "applied_rule_ids": [
            str(item)
            for item in _safe_list(value.get("applied_rule_ids"))
            if str(item)
        ][:20],
        "applied_event_ids": [
            str(item)
            for item in _safe_list(value.get("applied_event_ids"))
            if str(item)
        ][:20],
        "skipped_reasons": [
            dict(row)
            for row in _safe_list(value.get("skipped_reasons"))
            if isinstance(row, dict)
        ][:20],
    }


def normalize_campaign_director_state(value: Dict[str, Any] | None) -> Dict[str, Any]:
    value = _safe_dict(value)
    history = [
        normalize_director_tick_record(row)
        for row in _safe_list(value.get("tick_history"))
        if isinstance(row, dict)
    ][-MAX_DIRECTOR_TICK_HISTORY:]
    return {
        "version": 1,
        "enabled": _safe_bool(value.get("enabled"), True),
        "last_tick_turn": _safe_int(value.get("last_tick_turn"), 0),
        "last_mode": str(value.get("last_mode") or ""),
        "tick_history": history,
        "max_tick_history": MAX_DIRECTOR_TICK_HISTORY,
    }


def ensure_campaign_director_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    state = normalize_campaign_director_state(simulation_state.get("campaign_director_state"))
    simulation_state["campaign_director_state"] = state
    return state


def record_campaign_director_tick(
    simulation_state: Dict[str, Any],
    *,
    turn_index: int,
    mode: str,
    eligible_count: int = 0,
    applied_rule_ids: List[str] | None = None,
    applied_event_ids: List[str] | None = None,
    skipped_reasons: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    state = ensure_campaign_director_state(simulation_state)
    applied_rule_ids = applied_rule_ids or []
    applied_event_ids = applied_event_ids or []
    row = normalize_director_tick_record(
        {
            "turn_index": turn_index,
            "mode": mode,
            "eligible_count": eligible_count,
            "applied_count": len(applied_event_ids),
            "applied_rule_ids": applied_rule_ids,
            "applied_event_ids": applied_event_ids,
            "skipped_reasons": skipped_reasons or [],
        }
    )
    history = list(state.get("tick_history") or [])
    history.append(row)
    state["tick_history"] = history[-MAX_DIRECTOR_TICK_HISTORY:]
    state["last_tick_turn"] = int(turn_index or 0)
    state["last_mode"] = str(mode or "")
    simulation_state["campaign_director_state"] = normalize_campaign_director_state(state)
    return {
        "ok": True,
        "reason": "director_tick_recorded",
        "tick": row,
        "state": simulation_state["campaign_director_state"],
    }