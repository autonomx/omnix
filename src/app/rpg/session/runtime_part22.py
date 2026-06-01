from __future__ import annotations

# Generated split module for app.rpg.session.runtime.
# PR.1.13: final-turn bridge for combat XP reward surfaces.
from .runtime_part21 import *
from .runtime_part16 import _apply_turn_authoritative as _base_apply_turn_authoritative


def _first_non_empty_xp_result(*values: Any) -> Dict[str, Any]:
    for value in values:
        xp_result = _safe_dict(value)
        if not xp_result:
            continue
        if (
            _safe_int(xp_result.get("xp_gained"), 0) > 0
            or _safe_int(xp_result.get("xp_awarded"), 0) > 0
            or bool(xp_result.get("awarded"))
            or bool(xp_result.get("level_ups"))
        ):
            return xp_result
    return {}


def _surface_combat_xp_result_in_turn_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    result = _safe_dict(payload.get("result"))
    resolved_result = _safe_dict(payload.get("resolved_result")) or result
    narration_context = _safe_dict(payload.get("narration_context"))
    runtime_state = _safe_dict(payload.get("runtime_state"))
    session = _safe_dict(payload.get("session"))
    session_runtime_state = _safe_dict(session.get("runtime_state"))

    combat_result = (
        _safe_dict(payload.get("combat_result"))
        or _safe_dict(result.get("combat_result"))
        or _safe_dict(resolved_result.get("combat_result"))
        or _safe_dict(narration_context.get("combat_result"))
    )
    combat_xp_result = _first_non_empty_xp_result(
        combat_result.get("xp_result"),
        _safe_dict(combat_result.get("loot_result")).get("xp_result"),
        resolved_result.get("xp_result"),
        result.get("xp_result"),
    )
    if not combat_xp_result:
        return payload

    existing_xp_result = _first_non_empty_xp_result(
        payload.get("xp_result"),
        result.get("xp_result"),
        resolved_result.get("xp_result"),
        narration_context.get("xp_result"),
        _safe_dict(runtime_state.get("last_turn_result")).get("xp_result"),
        _safe_dict(session_runtime_state.get("last_turn_result")).get("xp_result"),
    )
    turn_xp_result = existing_xp_result or combat_xp_result

    payload["xp_result"] = turn_xp_result
    result["xp_result"] = turn_xp_result
    resolved_result["xp_result"] = turn_xp_result
    narration_context["xp_result"] = turn_xp_result

    if runtime_state:
        last_turn_result = _safe_dict(runtime_state.get("last_turn_result"))
        if last_turn_result:
            last_turn_result["xp_result"] = turn_xp_result
            runtime_state["last_turn_result"] = last_turn_result
        payload["runtime_state"] = runtime_state

    if session_runtime_state:
        session_last_turn_result = _safe_dict(session_runtime_state.get("last_turn_result"))
        if session_last_turn_result:
            session_last_turn_result["xp_result"] = turn_xp_result
            session_runtime_state["last_turn_result"] = session_last_turn_result
        session["runtime_state"] = session_runtime_state
        payload["session"] = session

    payload["result"] = result
    payload["resolved_result"] = resolved_result
    payload["narration_context"] = narration_context
    return payload


def _apply_turn_authoritative(
    session_id: str,
    player_input: str,
    action: Dict[str, Any] | None = None,
    *,
    performance_override: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = _base_apply_turn_authoritative(
        session_id,
        player_input,
        action,
        performance_override=performance_override,
    )
    return _surface_combat_xp_result_in_turn_payload(payload)


__all__ = [name for name in globals() if not name.startswith("__")]
