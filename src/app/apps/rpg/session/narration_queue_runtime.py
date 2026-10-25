from __future__ import annotations

# RPG session runtime responsibility module.
from app.apps.rpg.session.state_normalization import (
    _copy_dict as _copy_dict,
    _ensure_active_interactions as _ensure_active_interactions,
    _ensure_npc_reaction_runtime_state as _ensure_npc_reaction_runtime_state,
    _ensure_simulation_state as _ensure_simulation_state,
    _normalize_performance_settings as _normalize_performance_settings,
    _safe_bool as _safe_bool,
    _safe_dict as _safe_dict,
    _safe_int as _safe_int,
    _safe_list as _safe_list,
    _safe_str as _safe_str,
)
from app.apps.rpg.session.companion_turn_runtime import (
    _INTERACTION_STALE_GRACE_TICKS as _INTERACTION_STALE_GRACE_TICKS,
    _MAX_ACTIVE_INTERACTIONS as _MAX_ACTIVE_INTERACTIONS,
)
from app.apps.rpg.narration.ai.npc_reaction_layer import (
    apply_npc_reactions as apply_npc_reactions, build_interaction_reaction_context as build_interaction_reaction_context,
    build_npc_reaction_candidates as build_npc_reaction_candidates, select_npc_reactions as select_npc_reactions,
    update_interaction_reaction_state as update_interaction_reaction_state,
)
from app.apps.rpg.narration.ai.conversation_threads import (
    seed_or_update_thread as seed_or_update_thread,
)
import hashlib as hashlib
from typing import (
    Any as Any, Dict as Dict, List as List, Tuple as Tuple,
)


# Backward compatibility wrapper
# ── Fast-turn performance helpers ─────────────────────────────────────────


def _runtime_compact_save_enabled(runtime_state: dict[str, Any]) -> bool:
    return _normalize_performance_settings(runtime_state)["compact_save"]


def _clear_stale_last_player_action(
    runtime_state: dict[str, Any],
    current_tick: int,
    max_age_ticks: int = 2,
) -> dict[str, Any]:
    runtime_state = _copy_dict(runtime_state)
    last_player_action = _safe_dict(runtime_state.get("last_player_action"))
    if not last_player_action:
        return runtime_state
    action_tick = _safe_int(last_player_action.get("tick"), -999999)
    if action_tick < 0:
        runtime_state["last_player_action"] = {}
        return runtime_state
    if _safe_int(current_tick, 0) - action_tick > max_age_ticks:
        runtime_state["last_player_action"] = {}
    return runtime_state


def _expire_stale_active_interactions(
    simulation_state: dict[str, Any],
    current_tick: int,
) -> dict[str, Any]:
    from app.apps.rpg.session.combat_intent import (
        _compact_active_interactions as _compact_active_interactions, _log_interaction_trace as _log_interaction_trace,
    )

    simulation_state = _ensure_active_interactions(simulation_state)
    kept = []
    expired = []
    for raw in _safe_list(simulation_state.get("active_interactions")):
        item = _safe_dict(raw)
        expires_tick = _safe_int(item.get("expires_tick"), -999999)
        if expires_tick >= _safe_int(current_tick, 0) - _INTERACTION_STALE_GRACE_TICKS:
            kept.append(item)
        else:
            expired.append(
                {
                    "id": _safe_str(item.get("id")),
                    "expires_tick": expires_tick,
                    "current_tick": _safe_int(current_tick, 0),
                    "reason": "stale",
                }
            )
    simulation_state["active_interactions"] = kept[:_MAX_ACTIVE_INTERACTIONS]
    if expired:
        _log_interaction_trace(
            "expire_active_interactions",
            {
                "tick": _safe_int(current_tick, 0),
                "expired": expired,
                "remaining_count": len(_safe_list(simulation_state.get("active_interactions"))),
                "remaining": _compact_active_interactions(_safe_list(simulation_state.get("active_interactions"))),
            },
        )
    return simulation_state


def _refresh_active_interactions_for_tick(
    simulation_state: dict[str, Any],
    current_tick: int,
) -> dict[str, Any]:
    """Keep unresolved interactions visually current across idle ticks.

    This does not change lifecycle semantics. It only updates the interaction's
    display freshness so world-events sorting does not bury an ongoing player
    interaction under ambient activity rows.
    """
    simulation_state = _ensure_active_interactions(simulation_state)
    refreshed: list[dict[str, Any]] = []

    for raw in _safe_list(simulation_state.get("active_interactions")):
        item = _safe_dict(raw)
        if not _safe_bool(item.get("resolved"), False):
            item["updated_tick"] = _safe_int(current_tick, 0)
        refreshed.append(item)

    simulation_state["active_interactions"] = refreshed[:_MAX_ACTIVE_INTERACTIONS]
    return simulation_state


def _seed_conversation_thread_from_active_interaction(
    simulation_state: dict[str, Any],
    runtime_state: dict[str, Any],
    interaction: dict[str, Any],
    current_tick: int,
) -> dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    interaction = _safe_dict(interaction)
    participants = [
        _safe_str(p).strip()
        for p in _safe_list(interaction.get("participants"))
        if _safe_str(p).strip()
    ]
    npc_participants = [p for p in participants if p != "player"]
    if not npc_participants:
        return runtime_state
    state = _safe_dict(interaction.get("state"))
    activity_label = _safe_str(
        state.get("activity_label")
        or interaction.get("subtype")
        or interaction.get("action_type")
        or "interaction"
    )
    topic_summary = _safe_str(state.get("summary")).strip()
    if not topic_summary:
        display_name = _safe_str(interaction.get("display_name")).strip()
        topic_summary = f"Player interaction with {display_name or npc_participants[0]} about {activity_label}."
    runtime_state = seed_or_update_thread(
        runtime_state,
        kind="player_interaction",
        participants=participants,
        topic={
            "key": f"interaction:{_safe_str(interaction.get('id'))}",
            "type": "player_interaction",
            "summary": topic_summary,
            "activity_label": activity_label,
            "allowed_world_signal_types": ["rumor", "tension", "quest_lead", "relationship_shift"],
        },
        current_tick=current_tick,
        location_id=_safe_str(interaction.get("location_id")),
        scene_id=_safe_str(interaction.get("scene_id")),
    )
    return runtime_state


def _run_npc_reaction_pass(
    simulation_state: dict[str, Any],
    runtime_state: dict[str, Any],
    current_tick: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    simulation_state = _ensure_simulation_state(_safe_dict(simulation_state))
    runtime_state = _ensure_npc_reaction_runtime_state(_safe_dict(runtime_state))

    interactions = _safe_list(simulation_state.get("active_interactions"))
    for raw in interactions:
        interaction = _safe_dict(raw)
        if _safe_bool(interaction.get("resolved"), False):
            continue
        runtime_state = _seed_conversation_thread_from_active_interaction(
            simulation_state,
            runtime_state,
            interaction,
            current_tick,
        )
        context = build_interaction_reaction_context(simulation_state, runtime_state, interaction)
        context["tick"] = _safe_int(current_tick, 0)
        runtime_state = update_interaction_reaction_state(simulation_state, runtime_state, context)
        candidates = build_npc_reaction_candidates(simulation_state, runtime_state, context)
        reactions = select_npc_reactions(simulation_state, runtime_state, candidates)
        simulation_state, runtime_state = apply_npc_reactions(simulation_state, runtime_state, reactions)

    return simulation_state, runtime_state


__all__ = [
    "_INTERACTION_STALE_GRACE_TICKS",
    "_MAX_ACTIVE_INTERACTIONS",
    "_clear_stale_last_player_action",
    "_expire_stale_active_interactions",
    "_refresh_active_interactions_for_tick",
    "_run_npc_reaction_pass",
    "_runtime_compact_save_enabled",
    "_seed_conversation_thread_from_active_interaction",
]
