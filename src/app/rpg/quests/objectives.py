from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.quests.state import get_quest

SOURCE = "deterministic_quest_objective_lifecycle"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def objective_from_template(template: Dict[str, Any]) -> Dict[str, Any]:
    template = _safe_dict(template)
    objective_id = _safe_str(template.get("objective_id"))
    required = max(1, _safe_int(template.get("required"), 1))
    return {
        "objective_id": objective_id,
        "description": _safe_str(template.get("description")) or objective_id,
        "status": "open",
        "completed_turn": None,
        "failed_turn": None,
        "failure_reason": "",
        "progress": 0,
        "required": required,
        "event_ids": [],
        "metadata": {
            "type": _safe_str(template.get("type")) or "generic",
            "target_ids": [_safe_str(row) for row in _safe_list(template.get("target_ids")) if _safe_str(row)],
            "required": required,
            **dict(_safe_dict(template.get("metadata"))),
        },
        "source": SOURCE,
    }


def create_objective(
    simulation_state: Dict[str, Any],
    *,
    quest_id: str,
    objective_template: Dict[str, Any],
) -> Dict[str, Any]:
    quest = get_quest(simulation_state, quest_id, create=False)
    objective = objective_from_template(objective_template)
    objective_id = _safe_str(objective.get("objective_id"))
    if not quest:
        return _reject("quest_missing", quest_id=quest_id, objective_id=objective_id)
    if not objective_id:
        return _reject("objective_id_missing", quest_id=quest_id, objective_id=objective_id)

    objectives = quest.setdefault("objectives", {})
    if objective_id in objectives:
        return _state_result("objective_already_exists", quest_id, objective_id, quest, objectives[objective_id])
    objectives[objective_id] = objective
    return _state_result("objective_created", quest_id, objective_id, quest, objective)


def update_objective_progress(
    simulation_state: Dict[str, Any],
    *,
    quest_id: str,
    objective_id: str,
    event_id: str,
    amount: int = 1,
    turn_index: int = 0,
) -> Dict[str, Any]:
    quest, objective, missing = _get_objective(simulation_state, quest_id, objective_id)
    if missing:
        return missing
    if objective.get("status") in {"failed", "completed"}:
        return _state_result(f"objective_already_{objective['status']}", quest_id, objective_id, quest, objective)

    normalized_event_id = _safe_str(event_id)
    if not normalized_event_id:
        return _reject("event_id_missing", quest_id=quest_id, objective_id=objective_id)
    event_ids = [_safe_str(row) for row in _safe_list(objective.get("event_ids")) if _safe_str(row)]
    if normalized_event_id in event_ids:
        return _state_result("duplicate_event_ignored", quest_id, objective_id, quest, objective)

    required = _set_required(objective)
    event_ids.append(normalized_event_id)
    objective["event_ids"] = event_ids
    objective["progress"] = min(required, _safe_int(objective.get("progress"), 0) + max(0, _safe_int(amount, 1)))

    reason = "objective_progress_updated"
    if objective["progress"] >= required:
        _complete_objective_record(objective, turn_index=turn_index)
        _derive_quest_state(quest, turn_index=turn_index)
        reason = "objective_completed"
    return _state_result(reason, quest_id, objective_id, quest, objective)


def complete_objective_lifecycle(
    simulation_state: Dict[str, Any],
    *,
    quest_id: str,
    objective_id: str,
    turn_index: int = 0,
) -> Dict[str, Any]:
    quest, objective, missing = _get_objective(simulation_state, quest_id, objective_id)
    if missing:
        return missing
    if objective.get("status") in {"failed", "completed"}:
        return _state_result(f"objective_already_{objective['status']}", quest_id, objective_id, quest, objective)

    required = _set_required(objective)
    objective["progress"] = required
    _complete_objective_record(objective, turn_index=turn_index)
    _derive_quest_state(quest, turn_index=turn_index)
    return _state_result("objective_completed", quest_id, objective_id, quest, objective)


def fail_objective(
    simulation_state: Dict[str, Any],
    *,
    quest_id: str,
    objective_id: str,
    reason: str,
    turn_index: int = 0,
) -> Dict[str, Any]:
    quest, objective, missing = _get_objective(simulation_state, quest_id, objective_id)
    if missing:
        return missing
    if objective.get("status") in {"failed", "completed"}:
        return _state_result(f"objective_already_{objective['status']}", quest_id, objective_id, quest, objective)

    failure_reason = _safe_str(reason) or "objective_failed"
    objective.update({"status": "failed", "failed_turn": int(turn_index or 0), "failure_reason": failure_reason, "source": SOURCE})
    quest["status"] = "failed"
    quest["stage"] = "failed"
    quest.setdefault("metadata", {})["failure_reason"] = failure_reason
    return _state_result("objective_failed", quest_id, objective_id, quest, objective)


def derive_quest_lifecycle(simulation_state: Dict[str, Any], *, quest_id: str, turn_index: int = 0) -> Dict[str, Any]:
    quest = get_quest(simulation_state, quest_id, create=False)
    if not quest:
        return _reject("quest_missing", quest_id=quest_id, objective_id="")
    return {"ok": True, "reason": _derive_quest_state(quest, turn_index=turn_index), "quest_id": quest_id, "quest": deepcopy(quest), "source": SOURCE}


def _get_objective(
    simulation_state: Dict[str, Any], quest_id: str, objective_id: str
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any] | None]:
    quest = get_quest(simulation_state, quest_id, create=False)
    if not quest:
        return {}, {}, _reject("quest_missing", quest_id=quest_id, objective_id=objective_id)
    objective = _safe_dict(quest.setdefault("objectives", {}).get(objective_id))
    if not objective:
        return quest, {}, _reject("objective_missing", quest_id=quest_id, objective_id=objective_id)
    return quest, objective, None


def _set_required(objective: Dict[str, Any]) -> int:
    metadata = _safe_dict(objective.get("metadata"))
    required = max(1, _safe_int(objective.get("required") or metadata.get("required"), 1))
    objective["required"] = required
    objective.setdefault("metadata", {})["required"] = required
    return required


def _complete_objective_record(objective: Dict[str, Any], *, turn_index: int) -> None:
    objective["status"] = "completed"
    objective["completed_turn"] = int(turn_index or 0)
    objective["source"] = SOURCE


def _derive_quest_state(quest: Dict[str, Any], *, turn_index: int) -> str:
    objectives = [_safe_dict(row) for row in _safe_dict(quest.get("objectives")).values()]
    if objectives and all(row.get("status") == "completed" for row in objectives):
        quest["status"] = "completed"
        quest["stage"] = "completed"
        if quest.get("completed_turn") is None:
            quest["completed_turn"] = int(turn_index or 0)
        return "quest_completed"
    if any(row.get("status") == "failed" for row in objectives):
        quest["status"] = "failed"
        quest["stage"] = "failed"
        return "quest_failed"
    return "quest_still_active"


def _state_result(reason: str, quest_id: str, objective_id: str, quest: Dict[str, Any], objective: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": True,
        "reason": reason,
        "quest_id": quest_id,
        "objective_id": objective_id,
        "objective": deepcopy(objective),
        "quest": deepcopy(quest),
        "source": SOURCE,
    }


def _reject(reason: str, *, quest_id: str, objective_id: str) -> Dict[str, Any]:
    return {"ok": False, "reason": reason, "quest_id": quest_id, "objective_id": objective_id, "source": SOURCE}
