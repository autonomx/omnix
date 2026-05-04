from __future__ import annotations

from typing import Any, Dict, List

MAX_PINNED_OBJECTIVES = 10
MAX_QUEST_LOG_HISTORY = 100


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


def _unique_strings(values: Any, *, limit: int) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in _safe_list(values):
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def normalize_quest_log_history_item(value: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(value)
    return {
        "objective_id": _safe_str(value.get("objective_id")),
        "action": _safe_str(value.get("action")),
        "turn_index": _safe_int(value.get("turn_index"), 0),
        "reason": _safe_str(value.get("reason")),
        "metadata": dict(_safe_dict(value.get("metadata"))),
    }


def normalize_quest_log_state(value: Dict[str, Any] | None) -> Dict[str, Any]:
    value = _safe_dict(value)
    pinned = _unique_strings(value.get("pinned_objective_ids"), limit=MAX_PINNED_OBJECTIVES)
    history = [
        normalize_quest_log_history_item(row)
        for row in _safe_list(value.get("history"))
        if isinstance(row, dict)
    ][-MAX_QUEST_LOG_HISTORY:]
    return {
        "version": 1,
        "pinned_objective_ids": pinned,
        "history": history,
        "max_pinned_objectives": MAX_PINNED_OBJECTIVES,
        "max_history": MAX_QUEST_LOG_HISTORY,
    }


def ensure_quest_log_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    state = normalize_quest_log_state(simulation_state.get("quest_log_state"))
    simulation_state["quest_log_state"] = state
    return state


def append_quest_log_history(
    simulation_state: Dict[str, Any],
    *,
    objective_id: str,
    action: str,
    turn_index: int = 0,
    reason: str = "",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    state = ensure_quest_log_state(simulation_state)
    history = list(state.get("history") or [])
    history.append(
        normalize_quest_log_history_item(
            {
                "objective_id": objective_id,
                "action": action,
                "turn_index": turn_index,
                "reason": reason,
                "metadata": metadata or {},
            }
        )
    )
    state["history"] = history[-MAX_QUEST_LOG_HISTORY:]
    simulation_state["quest_log_state"] = normalize_quest_log_state(state)
    return {"ok": True, "reason": "quest_log_history_recorded"}