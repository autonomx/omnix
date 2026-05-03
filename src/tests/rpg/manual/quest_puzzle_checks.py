from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.puzzles.conditions import evaluate_puzzle_condition
from app.rpg.puzzles.state import get_puzzle
from app.rpg.quests.conditions import evaluate_quest_condition
from app.rpg.quests.state import get_quest


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_simulation_state(
    *,
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    result = _safe_dict(result)
    nested = _safe_dict(result.get("result"))
    session_dict = _safe_dict(session)
    session_setup_payload = _safe_dict(session_dict.get("setup_payload"))
    session_metadata = _safe_dict(session_setup_payload.get("metadata"))

    candidates = [
        session_dict.get("simulation_state"),
        session_metadata.get("simulation_state"),
        _safe_dict(result.get("session")).get("simulation_state"),
        _safe_dict(nested.get("session")).get("simulation_state"),
        result.get("simulation_state"),
        nested.get("simulation_state"),
    ]

    first_non_empty: Dict[str, Any] = {}
    for candidate in candidates:
        candidate = _safe_dict(candidate)
        if candidate and not first_non_empty:
            first_non_empty = candidate
        if isinstance(candidate.get("quest_state"), dict) or isinstance(candidate.get("puzzle_state"), dict):
            return candidate
    return first_non_empty


def run_quest_puzzle_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "quest_stage":
        quest_id = str(check.get("quest_id") or "")
        expected_stage = str(check.get("expected_stage") or "")
        expected_status = check.get("expected_status")
        quest = get_quest(simulation_state, quest_id)
        actual_stage = str((quest or {}).get("stage") or "")
        actual_status = str((quest or {}).get("status") or "")
        ok = actual_stage == expected_stage
        if expected_status is not None:
            ok = ok and actual_status == str(expected_status)
        return {
            "check_type": check_type,
            "ok": ok,
            "quest_id": quest_id,
            "expected_stage": expected_stage,
            "actual_stage": actual_stage,
            "expected_status": expected_status,
            "actual_status": actual_status,
        }

    if check_type == "quest_objective":
        quest_id = str(check.get("quest_id") or "")
        objective_id = str(check.get("objective_id") or "")
        expected_status = str(check.get("expected_status") or "")
        quest = get_quest(simulation_state, quest_id)
        objective = _safe_dict(_safe_dict((quest or {}).get("objectives")).get(objective_id))
        actual_status = str(objective.get("status") or "")
        return {
            "check_type": check_type,
            "ok": actual_status == expected_status,
            "quest_id": quest_id,
            "objective_id": objective_id,
            "expected_status": expected_status,
            "actual_status": actual_status,
        }

    if check_type == "quest_condition":
        condition = _safe_dict(check.get("condition"))
        expected_ok = bool(check.get("expected_ok"))
        condition_result = evaluate_quest_condition(simulation_state, condition)
        return {
            "check_type": check_type,
            "ok": bool(condition_result.get("ok")) is expected_ok,
            "expected_ok": expected_ok,
            "actual_ok": bool(condition_result.get("ok")),
            "condition_result": condition_result,
        }

    if check_type == "quest_reward_payload":
        quest_id = str(check.get("quest_id") or "")
        quest = get_quest(simulation_state, quest_id)
        rewards = list(_safe_dict(quest).get("rewards") or [])
        expected_count = check.get("expected_count")
        expected_auto_granted = check.get("expected_auto_granted")
        ok = True
        if expected_count is not None:
            ok = ok and len(rewards) == int(expected_count)
        if expected_auto_granted is not None:
            ok = ok and all(row.get("auto_granted") is bool(expected_auto_granted) for row in rewards)
        return {
            "check_type": check_type,
            "ok": ok,
            "quest_id": quest_id,
            "expected_count": expected_count,
            "actual_count": len(rewards),
            "expected_auto_granted": expected_auto_granted,
            "rewards": rewards,
        }

    if check_type == "puzzle_state":
        puzzle_id = str(check.get("puzzle_id") or "")
        expected_state = str(check.get("expected_state") or "")
        expected_status = check.get("expected_status")
        puzzle = get_puzzle(simulation_state, puzzle_id)
        actual_state = str((puzzle or {}).get("state") or "")
        actual_status = str((puzzle or {}).get("status") or "")
        ok = actual_state == expected_state
        if expected_status is not None:
            ok = ok and actual_status == str(expected_status)
        return {
            "check_type": check_type,
            "ok": ok,
            "puzzle_id": puzzle_id,
            "expected_state": expected_state,
            "actual_state": actual_state,
            "expected_status": expected_status,
            "actual_status": actual_status,
        }

    if check_type == "puzzle_flag":
        puzzle_id = str(check.get("puzzle_id") or "")
        flag = str(check.get("flag") or "")
        expected = check.get("expected")
        puzzle = get_puzzle(simulation_state, puzzle_id)
        actual = _safe_dict((puzzle or {}).get("flags")).get(flag)
        return {
            "check_type": check_type,
            "ok": actual == expected,
            "puzzle_id": puzzle_id,
            "flag": flag,
            "expected": expected,
            "actual": actual,
        }

    if check_type == "puzzle_condition":
        condition = _safe_dict(check.get("condition"))
        expected_ok = bool(check.get("expected_ok"))
        condition_result = evaluate_puzzle_condition(simulation_state, condition)
        return {
            "check_type": check_type,
            "ok": bool(condition_result.get("ok")) is expected_ok,
            "expected_ok": expected_ok,
            "actual_ok": bool(condition_result.get("ok")),
            "condition_result": condition_result,
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_quest_puzzle_check_type:{check_type}",
    }


def run_quest_puzzle_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_quest_puzzle_check(check=check, result=result, session=session)
        for check in checks
    ]