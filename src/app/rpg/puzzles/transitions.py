from __future__ import annotations

from typing import Any, Dict

from app.rpg.puzzles.conditions import evaluate_all_puzzle_conditions
from app.rpg.puzzles.state import (
    get_puzzle,
    set_puzzle_flag,
    set_puzzle_state,
    start_puzzle,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _input_matches(expected: Any, actual: Any) -> bool:
    if expected is None:
        return True
    return str(expected).strip().lower() == str(actual).strip().lower()


def apply_puzzle_transition(
    simulation_state: Dict[str, Any],
    transition: Dict[str, Any],
    *,
    turn_index: int = 0,
) -> Dict[str, Any]:
    transition = _safe_dict(transition)
    action = str(transition.get("action") or "")
    puzzle_id = str(transition.get("puzzle_id") or "")

    conditions = transition.get("conditions") or []
    condition_result = evaluate_all_puzzle_conditions(simulation_state, conditions)
    if not condition_result.get("ok"):
        return {
            "ok": False,
            "kind": "puzzle_transition",
            "action": action,
            "puzzle_id": puzzle_id,
            "reason": "conditions_failed",
            "conditions": condition_result,
        }

    if action == "start":
        return dict(
            start_puzzle(
                simulation_state,
                puzzle_id,
                title=str(transition.get("title") or puzzle_id),
                state=str(transition.get("state") or "initial"),
            ),
            conditions=condition_result,
        )

    if action == "input":
        puzzle = get_puzzle(simulation_state, puzzle_id, create=True)
        assert puzzle is not None
        puzzle["attempts"] = int(puzzle.get("attempts") or 0) + 1
        expected_input = transition.get("expected_input")
        actual_input = transition.get("input")
        if not _input_matches(expected_input, actual_input):
            return {
                "ok": False,
                "kind": "puzzle_input",
                "action": action,
                "puzzle_id": puzzle_id,
                "reason": "wrong_input",
                "expected_input": expected_input,
                "input": actual_input,
                "puzzle": puzzle,
                "conditions": condition_result,
            }
        result = set_puzzle_state(
            simulation_state,
            puzzle_id,
            str(transition.get("next_state") or puzzle.get("state") or "initial"),
            status=transition.get("status"),
            turn_index=turn_index,
        )
        for flag, value in _safe_dict(transition.get("set_flags")).items():
            set_puzzle_flag(simulation_state, puzzle_id, str(flag), value)
        return dict(
            result,
            kind="puzzle_input",
            reason="correct_input",
            input=actual_input,
            conditions=condition_result,
        )

    if action == "set_flag":
        return dict(
            set_puzzle_flag(
                simulation_state,
                puzzle_id,
                str(transition.get("flag") or ""),
                transition.get("value", True),
            ),
            conditions=condition_result,
        )

    if action == "solve":
        result = set_puzzle_state(
            simulation_state,
            puzzle_id,
            str(transition.get("state") or "solved"),
            status="solved",
            turn_index=turn_index,
        )
        for flag, value in _safe_dict(transition.get("set_flags")).items():
            set_puzzle_flag(simulation_state, puzzle_id, str(flag), value)
        return dict(
            result,
            kind="puzzle_solve",
            reason="solved",
            conditions=condition_result,
        )

    return {
        "ok": False,
        "kind": "puzzle_transition",
        "action": action,
        "puzzle_id": puzzle_id,
        "reason": f"unknown_action:{action}",
        "conditions": condition_result,
    }