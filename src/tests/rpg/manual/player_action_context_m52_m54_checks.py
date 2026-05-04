from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.player_action_context.runtime import build_player_action_context, build_suggested_actions


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


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
        if (
            isinstance(candidate.get("story_arc_milestone_state"), dict)
            or isinstance(candidate.get("quest_log_state"), dict)
            or isinstance(candidate.get("combat_state"), dict)
            or isinstance(candidate.get("scene"), dict)
        ):
            return candidate
    return first_non_empty


def run_player_action_context_m52_m54_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _extract_simulation_state(result=result, session=session)
    check_type = str(check.get("type") or "")

    if check_type == "player_action_context_payload":
        payload = build_player_action_context(
            simulation_state,
            turn_index=int(check.get("turn_index") or 1),
            limit=int(check.get("limit") or 12),
        )
        expected_mode = check.get("expected_mode")
        expected_objective_id = check.get("expected_objective_id")
        expected_action_category = check.get("expected_action_category")
        must_not_contain = str(check.get("must_not_contain") or "")
        ok = payload.get("ok") is True
        if expected_mode:
            ok = ok and payload.get("mode") == expected_mode
        if expected_objective_id:
            ok = ok and expected_objective_id in [
                row.get("objective_id") for row in payload.get("active_objectives") or []
            ]
        if expected_action_category:
            ok = ok and expected_action_category in [
                row.get("category") for row in payload.get("suggested_actions") or []
            ]
        if must_not_contain:
            ok = ok and must_not_contain not in str(payload)
        return {
            "check_type": check_type,
            "ok": ok,
            "payload": payload,
            "expected_mode": expected_mode,
            "expected_objective_id": expected_objective_id,
            "expected_action_category": expected_action_category,
            "must_not_contain": must_not_contain,
        }

    if check_type == "suggested_actions":
        actions = build_suggested_actions(
            simulation_state,
            turn_index=int(check.get("turn_index") or 1),
            limit=int(check.get("limit") or 12),
        )
        expected_category = check.get("expected_category")
        expected_objective_id = check.get("expected_objective_id")
        expected_first_objective_id = check.get("expected_first_objective_id")
        ok = True
        if expected_category:
            ok = ok and expected_category in [row.get("category") for row in actions]
        if expected_objective_id:
            ok = ok and expected_objective_id in [row.get("objective_id") for row in actions]
        if expected_first_objective_id:
            ok = ok and bool(actions) and actions[0].get("objective_id") == expected_first_objective_id
        return {
            "check_type": check_type,
            "ok": ok,
            "actions": actions,
            "expected_category": expected_category,
            "expected_objective_id": expected_objective_id,
            "expected_first_objective_id": expected_first_objective_id,
        }

    if check_type == "player_action_context_bounded":
        payload = build_player_action_context(
            simulation_state,
            turn_index=int(check.get("turn_index") or 1),
            limit=int(check.get("limit") or 12),
        )
        limit = int(check.get("limit") or 12)
        return {
            "check_type": check_type,
            "ok": len(payload.get("suggested_actions") or []) <= limit,
            "payload": payload,
            "limit": limit,
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_player_action_context_m52_m54_check_type:{check_type}",
    }


def run_player_action_context_m52_m54_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for check in checks:
        check_type = str(_safe_dict(check).get("type") or "")
        try:
            check_result = run_player_action_context_m52_m54_check(
                check=_safe_dict(check),
                result=result,
                session=session,
            )
        except Exception as exc:
            check_result = {
                "check_type": check_type,
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        results.append(check_result)
    return results