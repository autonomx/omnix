from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

# Generated split module for app.rpg.session.runtime.
# Phase 4.13: route session travel commands through guarded Phase 4 runtime helpers.
from .runtime_part26 import *
from .runtime_part26 import _apply_turn_authoritative as _base_apply_turn_authoritative

_PHASE4_SESSION_TRAVEL_SOURCE = "deterministic_phase4_session_travel_command_integration"
_PHASE4_FRONTEND_MAP_LOCATION_SOURCE = "deterministic_phase4_frontend_map_location_ui_panel"
_PHASE8_PLAYER_HUD_SOURCE = "deterministic_phase8_player_visible_state_objective_hud_gate"


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


def _phase4_frontend_map_location_panel_payload(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Build the player-visible map/location UI payload without mutating state."""
    from app.rpg.locations import build_map_location_panel_payload

    panel_payload = build_map_location_panel_payload(deepcopy(_safe_dict(simulation_state)))
    panel_payload["frontend_source"] = _PHASE4_FRONTEND_MAP_LOCATION_SOURCE
    return panel_payload


def _phase8_inventory_summary(player_state: Dict[str, Any]) -> Dict[str, Any]:
    inventory = _safe_dict(player_state.get("inventory_state") or player_state.get("inventory"))
    items = []
    for raw in _safe_list(inventory.get("items") or player_state.get("items")):
        item = _safe_dict(raw)
        item_id = _safe_str(item.get("item_id") or item.get("id") or item.get("name"))
        if item_id:
            items.append(
                {
                    "item_id": item_id,
                    "name": _safe_str(item.get("name") or item_id),
                    "qty": _safe_int(item.get("qty") or item.get("quantity"), 1),
                    "source": _PHASE8_PLAYER_HUD_SOURCE,
                }
            )
    currency = _safe_dict(inventory.get("currency") or player_state.get("currency"))
    return {
        "items": items[:8],
        "item_count": len(items),
        "currency": {
            "gold": _safe_int(currency.get("gold"), 0),
            "silver": _safe_int(currency.get("silver"), 0),
            "copper": _safe_int(currency.get("copper"), 0),
            "source": _PHASE8_PLAYER_HUD_SOURCE,
        },
        "source": _PHASE8_PLAYER_HUD_SOURCE,
    }


def _phase8_active_objective_summary(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    journal = _safe_dict(simulation_state.get("journal_state") or simulation_state.get("journal"))
    quest_state = _safe_dict(simulation_state.get("quest_state") or simulation_state.get("quests"))
    candidates: List[Dict[str, Any]] = []
    for raw in _safe_list(journal.get("objectives") or quest_state.get("objectives")):
        objective = _safe_dict(raw)
        status = _safe_str(objective.get("status") or objective.get("state") or "active")
        if status in {"active", "in_progress", "available"}:
            candidates.append(objective)
    for raw in _safe_list(quest_state.get("active_quests") or quest_state.get("quests")):
        quest = _safe_dict(raw)
        status = _safe_str(quest.get("status") or quest.get("state") or "active")
        if status in {"active", "in_progress", "available"}:
            candidates.append(quest)
    selected = candidates[0] if candidates else {}
    title = _safe_str(
        selected.get("title")
        or selected.get("objective")
        or selected.get("summary")
        or selected.get("description")
        or journal.get("active_objective")
        or quest_state.get("active_objective")
    )
    return {
        "title": title or "No active objective recorded",
        "quest_id": _safe_str(selected.get("quest_id") or selected.get("id")),
        "status": _safe_str(selected.get("status") or selected.get("state") or ("active" if title else "none")),
        "source": _PHASE8_PLAYER_HUD_SOURCE,
    }


def _phase8_party_summary(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    party_state = _safe_dict(simulation_state.get("party_state") or simulation_state.get("party"))
    members = []
    for raw in _safe_list(party_state.get("members") or party_state.get("companions")):
        member = _safe_dict(raw)
        member_id = _safe_str(member.get("npc_id") or member.get("id") or member.get("name"))
        if member_id:
            members.append(
                {
                    "id": member_id,
                    "name": _safe_str(member.get("name") or member_id),
                    "role": _safe_str(member.get("role") or "companion"),
                    "source": _PHASE8_PLAYER_HUD_SOURCE,
                }
            )
    return {"members": members[:6], "member_count": len(members), "source": _PHASE8_PLAYER_HUD_SOURCE}


def _phase8_major_warnings(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    player_state = _safe_dict(simulation_state.get("player_state"))
    survival = _safe_dict(player_state.get("survival_state") or simulation_state.get("survival_state"))
    hunger = _safe_int(survival.get("hunger"), 0)
    thirst = _safe_int(survival.get("thirst"), 0)
    if hunger >= 80:
        warnings.append({"kind": "high_hunger", "label": "Hunger is high", "severity": "warning", "source": _PHASE8_PLAYER_HUD_SOURCE})
    if thirst >= 80:
        warnings.append({"kind": "high_thirst", "label": "Thirst is high", "severity": "warning", "source": _PHASE8_PLAYER_HUD_SOURCE})
    last_turn = _safe_dict(runtime_state.get("last_turn_result"))
    if last_turn and last_turn.get("ok") is False:
        warnings.append(
            {
                "kind": "last_action_failed",
                "label": _safe_str(last_turn.get("reason") or "Last action failed"),
                "severity": "info",
                "source": _PHASE8_PLAYER_HUD_SOURCE,
            }
        )
    return warnings


def _phase8_player_visible_hud_payload(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a read-only player HUD payload from deterministic runtime state."""

    simulation_copy = deepcopy(_safe_dict(simulation_state))
    runtime_copy = deepcopy(_safe_dict(runtime_state))
    player_state = _safe_dict(simulation_copy.get("player_state"))
    map_panel = _phase4_frontend_map_location_panel_payload(simulation_copy)
    time_state = _safe_dict(map_panel.get("time_state") or simulation_copy.get("time_state"))
    weather_state = _safe_dict(map_panel.get("weather_state") or simulation_copy.get("weather_state"))
    return {
        "source": _PHASE8_PLAYER_HUD_SOURCE,
        "frontend_source": _PHASE8_PLAYER_HUD_SOURCE,
        "current_location": _safe_dict(map_panel.get("current_location")),
        "current_location_id": _safe_str(map_panel.get("current_location_id")),
        "active_objective": _phase8_active_objective_summary(simulation_copy),
        "player_resources": _phase8_inventory_summary(player_state),
        "party_summary": _phase8_party_summary(simulation_copy),
        "major_warnings": _phase8_major_warnings(simulation_copy, runtime_copy),
        "time_state": {
            "day_count": _safe_int(time_state.get("day_count"), 1),
            "clock_time": _safe_str(time_state.get("clock_time")),
            "time_of_day_label": _safe_str(time_state.get("time_of_day_label")),
            "season": _safe_str(time_state.get("season") or weather_state.get("season")),
            "weather_label": _safe_str(time_state.get("weather_label") or weather_state.get("weather_label") or weather_state.get("label")),
            "source": _PHASE8_PLAYER_HUD_SOURCE,
        },
        "map_location_panel": map_panel,
        "non_mutating": True,
    }


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
    map_location_panel = _phase4_frontend_map_location_panel_payload(simulation_state)
    player_hud = _phase8_player_visible_hud_payload(simulation_state, runtime_state)

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
        "map_location_panel": map_location_panel,
        "player_hud": player_hud,
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
        "map_location_panel": map_location_panel,
        "player_hud": player_hud,
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
        "map_location_panel": map_location_panel,
        "player_hud": player_hud,
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
    base_payload = _base_apply_turn_authoritative(session_id, player_input, action, performance_override=performance_override)
    if isinstance(base_payload, dict):
        base_payload.setdefault("player_hud", _phase8_player_visible_hud_payload(simulation_state, runtime_state))
    return base_payload


__all__ = [name for name in globals() if not name.startswith("__")]
