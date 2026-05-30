from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _s(value: Any) -> str:
    return "" if value is None else str(value)


def _i(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except Exception:
            return default
    return default


def combat_lifecycle_from_matrix_turn(turn: Mapping[str, Any]) -> Dict[str, Any]:
    """Extract PR.1 combat lifecycle metadata from a matrix-shaped turn."""

    turn = _d(turn)
    raw = _d(turn.get("raw_result") or turn.get("result"))
    nested = _d(raw.get("result"))
    resolved = _d(raw.get("resolved_result") or nested.get("resolved_result"))
    for candidate in (
        _d(raw.get("combat_lifecycle")),
        _d(nested.get("combat_lifecycle")),
        _d(resolved.get("combat_lifecycle")),
        _d(_d(raw.get("narration_payload")).get("combat_lifecycle")),
        _d(_d(raw.get("structured_narration")).get("combat_lifecycle")),
        _d(_d(raw.get("combat_narration_payload")).get("combat_lifecycle")),
    ):
        if candidate.get("schema") == "combat_lifecycle_v1":
            return candidate
    return {}


def combat_log_from_matrix_turn(turn: Mapping[str, Any]) -> List[Dict[str, Any]]:
    lifecycle = combat_lifecycle_from_matrix_turn(turn)
    if lifecycle:
        return [_d(row) for row in _l(lifecycle.get("combat_log"))]
    turn = _d(turn)
    raw = _d(turn.get("raw_result") or turn.get("result"))
    nested = _d(raw.get("result"))
    rows = _l(raw.get("combat_log")) or _l(nested.get("combat_log"))
    return [_d(row) for row in rows]


def _combat_result_from_matrix_turn(turn: Mapping[str, Any]) -> Dict[str, Any]:
    turn = _d(turn)
    raw = _d(turn.get("raw_result") or turn.get("result"))
    nested = _d(raw.get("result"))
    resolved = _d(raw.get("resolved_result") or nested.get("resolved_result"))
    return _d(raw.get("combat_result") or nested.get("combat_result") or resolved.get("combat_result"))


def _is_combat_start_only_turn(turn: Mapping[str, Any]) -> bool:
    combat = _combat_result_from_matrix_turn(turn)
    reason = _s(combat.get("reason"))
    if reason != "combat_started":
        return False
    return _i(combat.get("damage_applied"), 0) <= 0 and not bool(combat.get("defeated") or combat.get("combat_ended"))


def validate_combat_lifecycle_matrix_turns(turns: Sequence[Mapping[str, Any]]) -> List[str]:
    """Validate PR.1 lifecycle metadata on combat matrix attack/damage turns.

    The initial combat-start turn may not have a combat delta yet. PR.1 lifecycle
    metadata is required once an attack/damage/defeat turn has a backed combat
    delta.
    """

    failures: List[str] = []
    combat_turns = [_d(turn) for turn in turns]
    lifecycle_turns: List[Dict[str, Any]] = []

    for turn in combat_turns:
        turn_number = turn.get("turn_index") or turn.get("turn")
        lifecycle = combat_lifecycle_from_matrix_turn(turn)
        if not lifecycle:
            if _is_combat_start_only_turn(turn):
                continue
            failures.append(f"combat lifecycle turn {turn_number}: missing combat_lifecycle_v1")
            continue
        lifecycle_turns.append(lifecycle)
        initiative = _d(lifecycle.get("initiative"))
        enemy_turn = _d(lifecycle.get("enemy_turn"))
        progression = _d(lifecycle.get("progression_hooks"))
        log = [_d(row) for row in _l(lifecycle.get("combat_log"))]

        if initiative.get("schema") != "combat_initiative_v1":
            failures.append(f"combat lifecycle turn {turn_number}: missing combat_initiative_v1")
        if enemy_turn.get("schema") != "enemy_turn_skeleton_v1":
            failures.append(f"combat lifecycle turn {turn_number}: missing enemy_turn_skeleton_v1")
        if progression.get("schema") != "combat_progression_hooks_v1":
            failures.append(f"combat lifecycle turn {turn_number}: missing combat_progression_hooks_v1")
        if not log:
            failures.append(f"combat lifecycle turn {turn_number}: missing combat log row")
            continue

        row = log[0]
        damage = _i(row.get("damage_applied"), 0)
        before = row.get("target_hp_before")
        after = row.get("target_hp_after")
        if damage > 0 and before is not None and after is not None:
            expected_after = _i(before) - damage
            if _i(after) != expected_after:
                failures.append(
                    f"combat lifecycle turn {turn_number}: combat log HP delta mismatch before={before!r} damage={damage!r} after={after!r}"
                )
        if row.get("schema") != "combat_log_entry_v1":
            failures.append(f"combat lifecycle turn {turn_number}: combat log row missing schema")

        ended = bool(row.get("combat_ended") or row.get("defeated"))
        if ended:
            if enemy_turn.get("pending") is not False:
                failures.append(f"combat lifecycle turn {turn_number}: final enemy_turn.pending should be false")
            if initiative.get("turn_phase") != "combat_complete":
                failures.append(f"combat lifecycle turn {turn_number}: final turn_phase should be combat_complete")
            if progression.get("xp_pending") is not True:
                failures.append(f"combat lifecycle turn {turn_number}: defeat should mark xp_pending true")
            if progression.get("loot_pending") is not True:
                failures.append(f"combat lifecycle turn {turn_number}: defeat should mark loot_pending true")
        else:
            if enemy_turn.get("pending") is not True:
                failures.append(f"combat lifecycle turn {turn_number}: non-final enemy_turn.pending should be true")
            if not _s(initiative.get("next_actor_id")):
                failures.append(f"combat lifecycle turn {turn_number}: non-final next_actor_id should be populated")
            if progression.get("xp_pending") is True or progression.get("loot_pending") is True:
                failures.append(f"combat lifecycle turn {turn_number}: non-final progression should not be pending")

    if lifecycle_turns and not any(_d(_l(lifecycle.get("combat_log"))[0] if _l(lifecycle.get("combat_log")) else {}).get("defeated") for lifecycle in lifecycle_turns):
        failures.append("combat lifecycle: expected at least one defeated/completed final row")
    return failures
