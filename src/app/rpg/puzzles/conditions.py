from __future__ import annotations

from typing import Any, Dict

from app.rpg.puzzles.state import get_puzzle


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def evaluate_puzzle_condition(
    simulation_state: Dict[str, Any],
    condition: Dict[str, Any],
) -> Dict[str, Any]:
    condition = _safe_dict(condition)
    condition_type = str(condition.get("type") or "")

    if condition_type == "always":
        return {"ok": True, "type": condition_type, "reason": "always"}

    if condition_type == "puzzle_state":
        puzzle_id = str(condition.get("puzzle_id") or "")
        expected_state = str(condition.get("state") or "")
        puzzle = get_puzzle(simulation_state, puzzle_id)
        actual_state = str((puzzle or {}).get("state") or "")
        return {
            "ok": actual_state == expected_state,
            "type": condition_type,
            "puzzle_id": puzzle_id,
            "state": expected_state,
            "actual_state": actual_state,
            "reason": "state_matches" if actual_state == expected_state else "state_mismatch",
        }

    if condition_type == "puzzle_flag":
        puzzle_id = str(condition.get("puzzle_id") or "")
        flag = str(condition.get("flag") or "")
        expected = condition.get("expected", True)
        puzzle = get_puzzle(simulation_state, puzzle_id)
        actual = _safe_dict((puzzle or {}).get("flags")).get(flag)
        return {
            "ok": actual == expected,
            "type": condition_type,
            "puzzle_id": puzzle_id,
            "flag": flag,
            "expected": expected,
            "actual": actual,
            "reason": "flag_matches" if actual == expected else "flag_mismatch",
        }

    return {
        "ok": False,
        "type": condition_type,
        "reason": f"unknown_condition_type:{condition_type}",
    }


def evaluate_all_puzzle_conditions(
    simulation_state: Dict[str, Any],
    conditions: list[Dict[str, Any]],
) -> Dict[str, Any]:
    results = [
        evaluate_puzzle_condition(simulation_state, condition)
        for condition in conditions
    ]
    ok = all(row.get("ok") for row in results)
    return {
        "ok": ok,
        "results": results,
        "failed": [row for row in results if not row.get("ok")],
    }