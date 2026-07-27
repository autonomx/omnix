from .runtime_part19 import *  # noqa: F401,F403
from .runtime_part19 import apply_turn as _PHASE8_PART40_BASE_APPLY_TURN
from .runtime_part39 import (
    _latest_authoritative_turn_contract,
    _response_with_canonical_contract,
    _restore_response_narration,
)
from .causal_turn_runtime import advance_causal_runtime_for_turn


def _soft_truth_line(text: Any) -> str:
    return " ".join(str(text or "").split()).strip()


def _soft_truth_state(session: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(session.get("simulation_state"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    current_scene = _safe_dict(runtime_state.get("current_scene"))
    player_state = _safe_dict(simulation_state.get("player_state"))
    quest_state = _safe_dict(simulation_state.get("quest_state"))
    combat_state = _safe_dict(simulation_state.get("combat_state"))
    environment = _safe_dict(simulation_state.get("environment"))
    return {
        "location_id": _safe_str(
            current_scene.get("location_id")
            or player_state.get("location_id")
            or simulation_state.get("current_location_id")
        ),
        "current_scene": {
            "location_id": _safe_str(current_scene.get("location_id")),
            "npc_ids": list(_safe_list(current_scene.get("npc_ids"))),
            "summary": _soft_truth_line(current_scene.get("summary")),
        },
        "player_state": {
            "location_id": _safe_str(player_state.get("location_id")),
            "level": int(player_state.get("level", 1) or 1),
            "xp": int(player_state.get("xp", 0) or 0),
            "nearby_npc_ids": list(_safe_list(player_state.get("nearby_npc_ids"))),
        },
        "active_quest_ids": [
            _safe_str(row.get("quest_id") or row.get("id"))
            for row in _safe_list(quest_state.get("quests"))
            if isinstance(row, dict)
            and _safe_str(row.get("status")).strip().casefold()
            in {"active", "in_progress", "available", "accepted"}
        ],
        "active_combat_id": _safe_str(
            combat_state.get("combat_id")
            if _safe_str(combat_state.get("status")).strip().casefold()
            in {"active", "ongoing", "in_progress"}
            else ""
        ),
        "environment": {
            "absolute_minutes": int(environment.get("absolute_minutes", 0) or 0),
            "time_of_day": _safe_str(environment.get("time_of_day")),
            "weather": _soft_truth_line(environment.get("weather")),
        },
        "runtime_tick": int(runtime_state.get("tick", 0) or 0),
        "source": "post_commit_authoritative_soft_truth_v1",
    }


def _response_with_soft_truth(payload: Dict[str, Any], truth: Dict[str, Any]) -> Dict[str, Any]:
    result = deepcopy(_safe_dict(payload))
    result["soft_truth_state"] = deepcopy(truth)
    result_sub = _safe_dict(result.get("result"))
    if result_sub:
        result_sub["soft_truth_state"] = deepcopy(truth)
        result["result"] = result_sub
    authoritative = _safe_dict(result.get("authoritative"))
    if authoritative:
        authoritative["soft_truth_state"] = deepcopy(truth)
        result["authoritative"] = authoritative
    metadata = _safe_dict(result.get("metadata"))
    metadata["soft_truth_source"] = truth.get("source")
    result["metadata"] = metadata
    return result


def _persist_soft_truth(payload: Dict[str, Any], session_id: str) -> Dict[str, Any]:
    try:
        session = load_runtime_session(session_id)
    except Exception:
        session = None
    if not session:
        return payload
    truth = _soft_truth_state(session)
    runtime_state = _safe_dict(session.get("runtime_state"))
    runtime_state["soft_truth_state"] = deepcopy(truth)
    session["runtime_state"] = runtime_state
    try:
        save_runtime_session(session)
    except Exception:
        return _response_with_soft_truth(payload, truth)
    return _response_with_soft_truth(payload, truth)


def _advance_causal_turn(payload: Dict[str, Any], session_id: str) -> Dict[str, Any]:
    try:
        return advance_causal_runtime_for_turn(
            session_id,
            payload,
            loader=load_runtime_session,
            saver=save_runtime_session,
        )
    except Exception as exc:
        # The gameplay turn remains authoritative. Causal failures are surfaced for
        # diagnostics and never overwrite the committed turn or narration.
        result = deepcopy(_safe_dict(payload))
        result["causal_world_runtime"] = {
            "applied": False,
            "reason": "causal_runtime_error",
            "error": f"{type(exc).__name__}: {exc}",
        }
        return result


def apply_turn(
    session_id: str,
    command: Dict[str, Any],
    *,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Finalize one authoritative turn, then advance causal world state exactly once."""

    resolved = _PHASE8_PART40_BASE_APPLY_TURN(session_id, command, context=context)
    canonical = _response_with_canonical_contract(resolved, session_id)
    contract = _latest_authoritative_turn_contract(canonical, session_id)
    canonical = _restore_response_narration(
        canonical,
        resolved,
        contract=contract,
    )
    canonical = _persist_soft_truth(canonical, session_id)
    return _advance_causal_turn(canonical, session_id)
