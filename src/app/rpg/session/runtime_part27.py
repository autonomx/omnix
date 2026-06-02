from __future__ import annotations

from typing import Any, Dict

# Generated split module for app.rpg.session.runtime.
# Phase 4.13: route session travel commands through guarded Phase 4 runtime helpers.
from .runtime_part26 import *
from .runtime_part26 import _apply_turn_authoritative as _base_apply_turn_authoritative

_PHASE4_SESSION_TRAVEL_SOURCE = "deterministic_phase4_session_travel_command_integration"


def _phase4_session_travel_turn_index(runtime_state: Dict[str, Any], simulation_state: Dict[str, Any]) -> int:
    return _safe_int(
        runtime_state.get("tick")
        or simulation_state.get("tick")
        or simulation_state.get("current_tick"),
        0,
    )


def _phase4_session_travel_current_location(simulation_state: Dict[str, Any]) -> str:
    travel_state = _safe_dict(simulation_state.get("travel_state"))
    location_state = _safe_dict(simulation_state.get("location_state"))
    return _safe_str(
        travel_state.get("current_location_id")
        or location_state.get("current_location_id")
        or simulation_state.get("current_location_id")
        or simulation_state.get("location_id")
    )


def _phase4_session_travel_summary(command_result: Dict[str, Any]) -> str:
    command_result = _safe_dict(command_result)
    travel_result = _safe_dict(command_result.get("travel_result"))
    command = _safe_dict(command_result.get("command_result"))
    start = _safe_str(command.get("start_location_id"))
    end = _safe_str(command.get("end_location_id"))
    reason = _safe_str(command_result.get("reason") or travel_result.get("reason"))
    if command_result.get("ok") is True and end:
        return f"Travel resolved deterministically: {start} -> {end}."
    if reason == "insufficient_travel_resources":
        return "Travel denied: required travel resources are missing."
    if reason == "route_blocked":
        return "Travel denied: that route is currently blocked."
    if reason == "destination_undiscovered":
        return "Travel denied: that destination is not yet discovered."
    if reason == "route_undiscovered":
        return "Travel denied: that route is not yet discovered."
    if reason == "unknown_travel_destination":
        return "Travel denied: no canonical destination matches that command."
    return f"Travel command result: {reason or 'not_applied'}."


def _phase4_session_travel_payload(
    *,
    session_id: str,
    player_input: str,
    session: Dict[str, Any],
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    command_result: Dict[str, Any],
) -> Dict[str, Any]:
    from app.rpg.locations import build_runtime_travel_command_narration_contract

    command_result = _safe_dict(command_result)
    turn_index = _phase4_session_travel_turn_index(runtime_state, simulation_state)
    turn_id = _build_turn_id(runtime_state)
    summary = _phase4_session_travel_summary(command_result)
    contract = build_runtime_travel_command_narration_contract(command_result)
    travel_result = _safe_dict(command_result.get("travel_result"))
    encounter_result = _safe_dict(command_result.get("encounter_result"))
    encounter_runtime_result = _safe_dict(command_result.get("encounter_runtime_result"))

    resolved_result: Dict[str, Any] = {
        "ok": command_result.get("ok") is True,
        "action_type": "travel",
        "semantic_action_type": "travel",
        "summary": summary,
        "outcome": "success" if command_result.get("ok") is True else "failure",
        "travel_command_result": command_result,
        "travel_result": travel_result,
        "encounter_result": encounter_result,
        "encounter_runtime_result": encounter_runtime_result,
        "runtime_travel_command_narration_contract": contract,
        "meaningful_progress": command_result.get("ok") is True,
        "progress_category": "location_progression" if command_result.get("ok") is True else "blocked_travel",
        "source": _PHASE4_SESSION_TRAVEL_SOURCE,
    }
    if travel_result:
        resolved_result["travel_resource_result"] = _safe_dict(travel_result.get("resource_result"))
    if encounter_runtime_result.get("combat_candidate"):
        resolved_result["combat_candidate"] = encounter_runtime_result.get("combat_candidate")

    runtime_state["last_turn_result"] = {
        "action_type": "travel",
        "reason": _safe_str(command_result.get("reason")),
        "ok": command_result.get("ok") is True,
        "source": _PHASE4_SESSION_TRAVEL_SOURCE,
    }
    runtime_state["last_player_action"] = {
        "action_id": f"player_action:{turn_index + 1}",
        "action_type": "travel",
        "target_id": _safe_str(_safe_dict(command_result.get("command_result")).get("end_location_id")),
        "source": _PHASE4_SESSION_TRAVEL_SOURCE,
    }
    runtime_state["tick"] = turn_index + 1

    session = _safe_dict(session)
    session["simulation_state"] = simulation_state
    session["runtime_state"] = runtime_state
    manifest = _safe_dict(session.get("manifest"))
    manifest.setdefault("session_id", session_id)
    manifest.setdefault("id", session_id)
    session["manifest"] = manifest
    save_runtime_session(session)

    narration_context = {
        "player_input": player_input,
        "action_type": "travel",
        "resolved_result": resolved_result,
        "simulation_state": simulation_state,
        "runtime_state": runtime_state,
        "travel_command_result": command_result,
        "travel_result": travel_result,
        "encounter_result": encounter_result,
        "encounter_runtime_result": encounter_runtime_result,
        "runtime_travel_command_narration_contract": contract,
        "forbidden_narration": list(_safe_list(contract.get("forbidden_runtime_travel_command_claims"))),
        "settings": runtime_state.get("runtime_settings", {}),
        "conversation_threads": [],
    }

    return {
        "ok": True,
        "simulation_state": simulation_state,
        "runtime_state": runtime_state,
        "session": session,
        "result": resolved_result,
        "resolved_result": resolved_result,
        "travel_command_result": command_result,
        "travel_result": travel_result,
        "encounter_result": encounter_result,
        "encounter_runtime_result": encounter_runtime_result,
        "runtime_travel_command_narration_contract": contract,
        "narration_context": narration_context,
        "narration": summary,
        "final_narration": summary,
        "summary": summary,
        "turn_id": turn_id,
        "tick": turn_index,
        "source": _PHASE4_SESSION_TRAVEL_SOURCE,
    }


def _apply_phase4_session_travel_command(
    session_id: str,
    player_input: str,
    *,
    session: Dict[str, Any],
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> Dict[str, Any]:
    from app.rpg.locations import apply_runtime_travel_command, resolve_travel_command

    turn_index = _phase4_session_travel_turn_index(runtime_state, simulation_state)
    current_location_id = _phase4_session_travel_current_location(simulation_state)
    command_probe = resolve_travel_command(player_input, current_location_id=current_location_id or "location:rusty_flagon")
    if command_probe.get("reason") == "not_travel_command":
        return {}

    command_result = apply_runtime_travel_command(
        simulation_state,
        player_input,
        turn_index=turn_index,
        encounter_seed=f"phase4.13:{session_id}",
        current_location_id=current_location_id or None,
    )
    return _phase4_session_travel_payload(
        session_id=session_id,
        player_input=player_input,
        session=session,
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        command_result=command_result,
    )


def _apply_turn_authoritative(
    session_id: str,
    player_input: str,
    action: Dict[str, Any] | None = None,
    *,
    performance_override: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    session = load_runtime_session(session_id)
    if session is None:
        return _base_apply_turn_authoritative(session_id, player_input, action, performance_override=performance_override)
    session = _copy_dict(session)
    simulation_state = _ensure_simulation_state(_safe_dict(session.get("simulation_state")))
    runtime_state = _copy_dict(session.get("runtime_state"))
    travel_payload = _apply_phase4_session_travel_command(
        session_id,
        _safe_str(player_input).strip(),
        session=session,
        simulation_state=simulation_state,
        runtime_state=runtime_state,
    )
    if travel_payload:
        return travel_payload
    return _base_apply_turn_authoritative(session_id, player_input, action, performance_override=performance_override)


__all__ = [name for name in globals() if not name.startswith("__")]
