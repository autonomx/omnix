from __future__ import annotations

from typing import Any, Dict


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def normalize_puzzle(value: Dict[str, Any], *, puzzle_id: str = "") -> Dict[str, Any]:
    value = _safe_dict(value)
    normalized_id = _safe_str(value.get("puzzle_id")) or puzzle_id
    status = _safe_str(value.get("status")) or "inactive"
    if status not in {"inactive", "active", "solved", "failed"}:
        status = "inactive"
    return {
        "puzzle_id": normalized_id,
        "title": _safe_str(value.get("title")) or normalized_id,
        "status": status,
        "state": _safe_str(value.get("state")) or "initial",
        "flags": dict(_safe_dict(value.get("flags"))),
        "attempts": _safe_int(value.get("attempts"), 0),
        "solved_turn": _safe_int_or_none(value.get("solved_turn")),
        "metadata": dict(_safe_dict(value.get("metadata"))),
    }


def normalize_puzzle_state(value: Dict[str, Any] | None) -> Dict[str, Any]:
    value = _safe_dict(value)
    puzzles = {}
    for puzzle_id, puzzle in _safe_dict(value.get("puzzles")).items():
        puzzle_id = str(puzzle_id or "")
        if not puzzle_id:
            continue
        puzzles[puzzle_id] = normalize_puzzle(puzzle, puzzle_id=puzzle_id)
    return {
        "version": 1,
        "puzzles": puzzles,
    }


def ensure_puzzle_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    puzzle_state = normalize_puzzle_state(simulation_state.get("puzzle_state"))
    simulation_state["puzzle_state"] = puzzle_state
    return puzzle_state


def get_puzzle(
    simulation_state: Dict[str, Any],
    puzzle_id: str,
    *,
    create: bool = False,
    title: str = "",
) -> Dict[str, Any] | None:
    puzzle_state = ensure_puzzle_state(simulation_state)
    puzzles = puzzle_state.setdefault("puzzles", {})
    if puzzle_id not in puzzles and create:
        puzzles[puzzle_id] = normalize_puzzle(
            {
                "puzzle_id": puzzle_id,
                "title": title or puzzle_id,
                "status": "inactive",
                "state": "initial",
            },
            puzzle_id=puzzle_id,
        )
    return puzzles.get(puzzle_id)


def start_puzzle(
    simulation_state: Dict[str, Any],
    puzzle_id: str,
    *,
    title: str = "",
    state: str = "initial",
) -> Dict[str, Any]:
    puzzle = get_puzzle(simulation_state, puzzle_id, create=True, title=title)
    assert puzzle is not None
    puzzle["status"] = "active"
    puzzle["state"] = state
    return {
        "ok": True,
        "kind": "puzzle_start",
        "puzzle_id": puzzle_id,
        "state": puzzle["state"],
        "status": puzzle["status"],
        "puzzle": puzzle,
    }


def set_puzzle_state(
    simulation_state: Dict[str, Any],
    puzzle_id: str,
    state: str,
    *,
    status: str | None = None,
    turn_index: int = 0,
) -> Dict[str, Any]:
    puzzle = get_puzzle(simulation_state, puzzle_id, create=True)
    assert puzzle is not None
    puzzle["state"] = state
    if status:
        puzzle["status"] = status
    if status == "solved" and puzzle.get("solved_turn") is None:
        puzzle["solved_turn"] = int(turn_index or 0)
    return {
        "ok": True,
        "kind": "puzzle_state",
        "puzzle_id": puzzle_id,
        "state": puzzle["state"],
        "status": puzzle["status"],
        "puzzle": puzzle,
    }


def set_puzzle_flag(
    simulation_state: Dict[str, Any],
    puzzle_id: str,
    flag: str,
    value: Any,
) -> Dict[str, Any]:
    puzzle = get_puzzle(simulation_state, puzzle_id, create=True)
    assert puzzle is not None
    puzzle.setdefault("flags", {})[flag] = value
    return {
        "ok": True,
        "kind": "puzzle_flag",
        "puzzle_id": puzzle_id,
        "flag": flag,
        "value": value,
        "puzzle": puzzle,
    }