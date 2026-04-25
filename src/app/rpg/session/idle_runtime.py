from __future__ import annotations

from typing import Any, Callable, Dict

from app.rpg.creator.defaults import apply_adventure_defaults
from app.rpg.creator.world_simulation import step_simulation_state
from app.rpg.session.ambient_builder import _MAX_RESUME_CATCHUP_TICKS
from app.rpg.session.state_normalization import (
    _copy_dict,
    _ensure_simulation_state,
    _safe_dict,
    _safe_list,
    _safe_str,
)


def compute_idle_tick_count(
    session: Dict[str, Any],
    *,
    elapsed_seconds: int = 0,
    reason: str = "heartbeat",
) -> int:
    session = _safe_dict(session)
    runtime = _safe_dict(session.get("runtime_state"))
    sim = _safe_dict(session.get("simulation_state"))

    encounter_active = bool(sim.get("encounter_active") or sim.get("active_encounter"))
    quiet_ticks = int(runtime.get("post_player_quiet_ticks", 0) or 0)

    if reason == "resume_catchup":
        raw = max(0, elapsed_seconds // 5)
        return min(raw, _MAX_RESUME_CATCHUP_TICKS)

    if reason == "heartbeat":
        if encounter_active:
            return 0
        if quiet_ticks > 0:
            return 0
        return 1

    return 1



def advance_simulation_for_idle(session: Dict[str, Any], *, reason: str = "heartbeat") -> Dict[str, Any]:
    setup = apply_adventure_defaults(_copy_dict(session.get("setup_payload")))
    simulation_state = _ensure_simulation_state(_safe_dict(session.get("simulation_state")))

    metadata = _safe_dict(setup.get("metadata"))
    metadata["simulation_state"] = simulation_state
    setup["metadata"] = metadata

    step_result = step_simulation_state(setup)
    after_state = _ensure_simulation_state(_safe_dict(step_result.get("after_state")))
    next_setup = _safe_dict(step_result.get("next_setup")) or setup
    after_state["active_interactions"] = _safe_list(simulation_state.get("active_interactions"))

    return {
        "ok": True,
        "before_state": _safe_dict(step_result.get("before_state")),
        "after_state": after_state,
        "next_setup": next_setup,
        "step_result": step_result,
        "reason": reason,
    }



def build_idle_player_context(
    after_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    *,
    filter_salient_player_events: Callable[[list[Any]], list[Any]],
) -> Dict[str, Any]:
    player_state = _safe_dict(after_state.get("player_state"))
    current_scene = _safe_dict(runtime_state.get("current_scene"))
    idle_streak = int(runtime_state.get("idle_streak", 0) or 0)
    return {
        "player_location": _safe_str(
            player_state.get("location_id") or current_scene.get("location_id")
        ),
        "nearby_npc_ids": _safe_list(player_state.get("nearby_npc_ids")),
        "scene_id": _safe_str(current_scene.get("scene_id")),
        "world_summary": _safe_str(current_scene.get("summary") or current_scene.get("scene")),
        "player_idle": idle_streak > 0,
        "active_conflict": _safe_str(
            _safe_dict(after_state.get("active_conflict")).get("conflict_id")
            if isinstance(after_state.get("active_conflict"), dict)
            else ""
        ),
        "recent_incidents": _safe_list(after_state.get("incidents"))[-4:],
        "salient_events": filter_salient_player_events(_safe_list(after_state.get("events"))),
    }
