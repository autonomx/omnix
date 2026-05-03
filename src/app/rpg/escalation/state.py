from __future__ import annotations

from typing import Any, Dict, List


MAX_ESCALATION_RULE_APPLICATIONS = 500


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


def _safe_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def normalize_escalation_application(value: Dict[str, Any], *, rule_id: str = "") -> Dict[str, Any]:
    value = _safe_dict(value)
    normalized_rule_id = _safe_str(value.get("rule_id")) or rule_id
    return {
        "rule_id": normalized_rule_id,
        "arc_id": _safe_str(value.get("arc_id")),
        "application_count": max(0, _safe_int(value.get("application_count"), 0)),
        "last_applied_turn": _safe_int_or_none(value.get("last_applied_turn")),
        "applied_event_ids": [
            str(item)
            for item in _safe_list(value.get("applied_event_ids"))
            if str(item)
        ][-50:],
    }


def normalize_escalation_state(value: Dict[str, Any] | None) -> Dict[str, Any]:
    value = _safe_dict(value)
    applications: Dict[str, Dict[str, Any]] = {}
    for rule_id, row in _safe_dict(value.get("rule_applications")).items():
        rule_id = str(rule_id or "")
        if not rule_id:
            continue
        applications[rule_id] = normalize_escalation_application(row, rule_id=rule_id)
    ordered_ids = sorted(
        applications,
        key=lambda rid: (
            int(applications[rid].get("last_applied_turn") or 0),
            rid,
        ),
    )[-MAX_ESCALATION_RULE_APPLICATIONS:]
    return {
        "version": 1,
        "rule_applications": {
            rule_id: applications[rule_id]
            for rule_id in ordered_ids
        },
        "max_rule_applications": MAX_ESCALATION_RULE_APPLICATIONS,
    }


def ensure_escalation_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    state = normalize_escalation_state(simulation_state.get("escalation_state"))
    simulation_state["escalation_state"] = state
    return state


def get_escalation_rule_application(
    simulation_state: Dict[str, Any],
    rule_id: str,
) -> Dict[str, Any] | None:
    state = ensure_escalation_state(simulation_state)
    return state.get("rule_applications", {}).get(rule_id)


def mark_escalation_rule_applied(
    simulation_state: Dict[str, Any],
    *,
    rule_id: str,
    arc_id: str,
    event_id: str,
    turn_index: int = 0,
) -> Dict[str, Any]:
    state = ensure_escalation_state(simulation_state)
    applications = state.setdefault("rule_applications", {})
    current = normalize_escalation_application(
        applications.get(rule_id) or {"rule_id": rule_id, "arc_id": arc_id},
        rule_id=rule_id,
    )
    current["arc_id"] = arc_id
    current["application_count"] = int(current.get("application_count") or 0) + 1
    current["last_applied_turn"] = int(turn_index or 0)
    event_ids = list(current.get("applied_event_ids") or [])
    if event_id and event_id not in event_ids:
        event_ids.append(event_id)
    current["applied_event_ids"] = event_ids[-50:]
    applications[rule_id] = current
    simulation_state["escalation_state"] = normalize_escalation_state(state)
    return {
        "ok": True,
        "reason": "rule_application_marked",
        "rule_id": rule_id,
        "arc_id": arc_id,
        "event_id": event_id,
        "application": simulation_state["escalation_state"]["rule_applications"][rule_id],
    }