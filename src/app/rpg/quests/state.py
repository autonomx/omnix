from __future__ import annotations

from typing import Any, Dict, List


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


def _safe_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def normalize_objective(value: Dict[str, Any], *, objective_id: str = "") -> Dict[str, Any]:
    value = _safe_dict(value)
    normalized_id = _safe_str(value.get("objective_id")) or objective_id
    status = _safe_str(value.get("status")) or "open"
    if status not in {"open", "completed", "failed"}:
        status = "open"
    return {
        "objective_id": normalized_id,
        "description": _safe_str(value.get("description")) or normalized_id,
        "status": status,
        "completed_turn": _safe_int_or_none(value.get("completed_turn")),
        "metadata": dict(_safe_dict(value.get("metadata"))),
    }


def normalize_quest(value: Dict[str, Any], *, quest_id: str = "") -> Dict[str, Any]:
    value = _safe_dict(value)
    normalized_id = _safe_str(value.get("quest_id")) or quest_id
    status = _safe_str(value.get("status")) or "inactive"
    if status not in {"inactive", "active", "completed", "failed"}:
        status = "inactive"

    objectives = {}
    for objective_id, objective in _safe_dict(value.get("objectives")).items():
        objective_id = str(objective_id or "")
        if not objective_id:
            continue
        objectives[objective_id] = normalize_objective(
            objective,
            objective_id=objective_id,
        )

    return {
        "quest_id": normalized_id,
        "title": _safe_str(value.get("title")) or normalized_id,
        "status": status,
        "stage": _safe_str(value.get("stage")) or status,
        "objectives": objectives,
        "flags": dict(_safe_dict(value.get("flags"))),
        "rewards": [
            dict(row)
            for row in _safe_list(value.get("rewards"))
            if isinstance(row, dict)
        ],
        "reward_claimed": _safe_bool(value.get("reward_claimed"), False),
        "started_turn": _safe_int_or_none(value.get("started_turn")),
        "completed_turn": _safe_int_or_none(value.get("completed_turn")),
        "metadata": dict(_safe_dict(value.get("metadata"))),
    }


def normalize_quest_state(value: Dict[str, Any] | None) -> Dict[str, Any]:
    value = _safe_dict(value)
    quests = {}
    for quest_id, quest in _safe_dict(value.get("quests")).items():
        quest_id = str(quest_id or "")
        if not quest_id:
            continue
        quests[quest_id] = normalize_quest(quest, quest_id=quest_id)
    return {
        "version": 1,
        "quests": quests,
    }


def ensure_quest_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    quest_state = normalize_quest_state(simulation_state.get("quest_state"))
    simulation_state["quest_state"] = quest_state
    return quest_state


def get_quest(
    simulation_state: Dict[str, Any],
    quest_id: str,
    *,
    create: bool = False,
    title: str = "",
) -> Dict[str, Any] | None:
    quest_state = ensure_quest_state(simulation_state)
    quests = quest_state.setdefault("quests", {})
    if quest_id not in quests and create:
        quests[quest_id] = normalize_quest(
            {
                "quest_id": quest_id,
                "title": title or quest_id,
                "status": "inactive",
                "stage": "inactive",
            },
            quest_id=quest_id,
        )
    return quests.get(quest_id)


def start_quest(
    simulation_state: Dict[str, Any],
    quest_id: str,
    *,
    title: str = "",
    stage: str = "started",
    objectives: Dict[str, Dict[str, Any]] | None = None,
    turn_index: int = 0,
) -> Dict[str, Any]:
    quest = get_quest(simulation_state, quest_id, create=True, title=title)
    assert quest is not None
    quest["status"] = "active"
    quest["stage"] = stage
    if quest.get("started_turn") is None:
        quest["started_turn"] = int(turn_index or 0)
    for objective_id, objective in (objectives or {}).items():
        quest.setdefault("objectives", {})[objective_id] = normalize_objective(
            dict(objective or {}, objective_id=objective_id),
            objective_id=objective_id,
        )
    return {
        "ok": True,
        "kind": "quest_start",
        "quest_id": quest_id,
        "stage": quest["stage"],
        "status": quest["status"],
        "quest": quest,
    }


def set_quest_stage(
    simulation_state: Dict[str, Any],
    quest_id: str,
    stage: str,
    *,
    status: str | None = None,
    turn_index: int = 0,
) -> Dict[str, Any]:
    quest = get_quest(simulation_state, quest_id, create=True)
    assert quest is not None
    quest["stage"] = stage
    if status:
        quest["status"] = status
    if status == "completed" and quest.get("completed_turn") is None:
        quest["completed_turn"] = int(turn_index or 0)
    return {
        "ok": True,
        "kind": "quest_stage",
        "quest_id": quest_id,
        "stage": quest["stage"],
        "status": quest["status"],
        "quest": quest,
    }


def complete_objective(
    simulation_state: Dict[str, Any],
    quest_id: str,
    objective_id: str,
    *,
    turn_index: int = 0,
) -> Dict[str, Any]:
    quest = get_quest(simulation_state, quest_id, create=False)
    if not quest:
        return {
            "ok": False,
            "reason": "quest_missing",
            "quest_id": quest_id,
            "objective_id": objective_id,
        }
    objective = quest.setdefault("objectives", {}).get(objective_id)
    if not objective:
        return {
            "ok": False,
            "reason": "objective_missing",
            "quest_id": quest_id,
            "objective_id": objective_id,
        }
    if objective.get("status") == "completed":
        return {
            "ok": True,
            "reason": "already_completed",
            "quest_id": quest_id,
            "objective_id": objective_id,
            "objective": objective,
        }
    objective["status"] = "completed"
    objective["completed_turn"] = int(turn_index or 0)
    return {
        "ok": True,
        "reason": "completed",
        "quest_id": quest_id,
        "objective_id": objective_id,
        "objective": objective,
    }