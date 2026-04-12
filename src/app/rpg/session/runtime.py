"""Canonical RPG session runtime.

Single source of truth for:
- building a persisted session from adventure-builder startup
- loading/saving canonical sessions
- executing player turns against canonical session state
- shaping turn/bootstrap payloads for the frontend

This replaces the legacy in-memory GameSession / pipeline.py / routes.py flow.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

from app.rpg.action_resolver import resolve_player_action
from app.rpg.ai.action_intelligence import get_action_advisory, merge_action_advisory
from app.rpg.ai.ambient_dialogue import (
    apply_dialogue_cooldowns,
    build_ambient_dialogue_candidates,
    build_ambient_dialogue_request,
    select_ambient_dialogue_candidate,
)
from app.rpg.ai.npc_initiative import (
    apply_initiative_cooldowns,
    apply_world_behavior_bias,
    build_npc_initiative_candidates,
    compute_opening_relevance,
    select_npc_initiative_candidate,
)
from app.rpg.ai.npc_reaction_layer import (
    apply_npc_reactions,
    build_interaction_reaction_context,
    build_npc_reaction_candidates,
    select_npc_reactions,
    update_interaction_reaction_state,
)
from app.rpg.ai.scene_continuity import (
    advance_scene,
    build_continuation_beats,
    compact_finished_scenes,
    get_active_scene_candidates,
    maybe_build_scene_consequence,
    select_continuing_scene,
    start_persistent_scene,
)
from app.rpg.ai.scene_continuity import (
    ensure_scene_runtime_state as ensure_persistent_scene_runtime_state,
)
from app.rpg.ai.scene_weaver import (
    apply_scene_cooldowns,
    build_scene_beats,
    build_scene_candidates,
    select_scene_candidate,
)
from app.rpg.ai.semantic_action_intelligence import get_semantic_action_advisory
from app.rpg.ai.world_scene_narrator import narrate_ambient_update, narrate_scene
from app.rpg.creator.defaults import apply_adventure_defaults
from app.rpg.creator.schema import normalize_world_behavior_config
from app.rpg.creator.world_player_actions import (
    ESCALATE_CONFLICT,
    INTERVENE_THREAD,
    SUPPORT_FACTION,
    apply_player_action,
)
from app.rpg.creator.world_scene_generator import generate_scenes_from_simulation
from app.rpg.creator.world_simulation import (
    build_initial_simulation_state,
    step_simulation_state,
    summarize_simulation_step,
)
from app.rpg.items.inventory_state import (
    add_inventory_items,
    equip_inventory_item,
    get_inventory_item_for_drop,
    remove_inventory_item,
    unequip_inventory_slot,
)
from app.rpg.items.item_effects import apply_item_use
from app.rpg.items.world_items import (
    drop_world_item,
    ensure_world_item_state,
    list_scene_items,
    pickup_world_item,
)
from app.rpg.llm_app_gateway import build_app_llm_gateway
from app.rpg.memory.actor_memory_state import ensure_actor_memory_state
from app.rpg.memory.dialogue_context import (
    build_dialogue_memory_context,
    build_llm_memory_prompt_block,
)
from app.rpg.memory.memory_state import ensure_memory_state
from app.rpg.memory.world_memory_state import ensure_world_memory_state
from app.rpg.player import ensure_player_party, ensure_player_state
from app.rpg.player.player_progression_state import (
    award_player_xp,
    award_skill_xp,
    ensure_player_progression_state,
    resolve_level_ups,
    resolve_skill_level_ups,
)
from app.rpg.player.player_xp_rules import (
    compute_action_player_xp,
    compute_action_skill_xp,
    compute_stat_influence_bonus,
)
from app.rpg.presentation import (
    build_runtime_presentation_payload,
    build_scene_presentation_payload,
)
from app.rpg.presentation.memory_inspector import build_memory_ui_summary
from app.rpg.presentation.personality_state import ensure_personality_state
from app.rpg.presentation.speaker_cards import build_nearby_npc_cards
from app.rpg.presentation.visual_state import ensure_visual_state
from app.rpg.session.ambient_builder import (
    _MAX_IDLE_TICKS_PER_REQUEST,
    _MAX_RESUME_CATCHUP_TICKS,
    build_ambient_updates,
    coalesce_ambient_updates,
    enqueue_ambient_updates,
    get_pending_ambient_updates,
    is_player_visible_update,
    normalize_ambient_state,
    score_ambient_salience,
)
from app.rpg.session.ambient_policy import (
    classify_ambient_delivery,
    record_interrupt,
)
from app.rpg.session.service import load_session as load_canonical_session
from app.rpg.session.service import save_session as save_canonical_session
from app.rpg.world.world_event_director import (
    apply_world_behavior_to_events,
    build_world_event_candidates,
    convert_events_to_ambient_updates,
    filter_world_events,
)

_SCHEMA_VERSION = 4
_MAX_HISTORY = 64

# Phase F — quiet-window ticks after player action
_DEFAULT_POST_PLAYER_QUIET_TICKS = 1

_ALLOWED_IDLE_SECONDS = (15, 30, 60, 300, 600)
_ALLOWED_REACTION_STYLES = ("minimal", "normal", "lively")
_MAX_RECENT_WORLD_EVENT_ROWS = 64
_MAX_WORLD_RUMORS = 64
_MAX_WORLD_PRESSURE = 64
_MAX_LOCATION_CONDITIONS = 64
_MAX_WORLD_CONSEQUENCES = 128
_WORLD_RUMOR_DECAY_TICKS = 6
_WORLD_PRESSURE_DECAY_TICKS = 4
_LOCATION_CONDITION_DECAY_TICKS = 8
_WORLD_CONSEQUENCE_DECAY_TICKS = 6
_MAX_AMBIENT_UPDATES = 64
_MAX_RECENT_EVENTS = 24
_MAX_RECENT_CHANGES = 24
_MAX_DIRECTOR_LOG = 24
_MAX_RECENT_SCENE_BEATS = 32
_MAX_SEMANTIC_PROPOSALS = 32
_MAX_ACCEPTED_STATE_CHANGE_EVENTS = 64
_MAX_APPLIED_PROPOSAL_IDS = 128
_MAX_LLM_PROPOSAL_CANDIDATES = 8
_MAX_PROMPT_SCENE_BEATS = 4
_SEMANTIC_LLM_PROPOSAL_COOLDOWN_TICKS = 1
_MAX_RECORDED_SEMANTIC_LLM_PROPOSALS = 8
_MAX_SEMANTIC_ACTION_RECORDS = 64
_MAX_RUNTIME_LLM_RECORDS = 256
_MAX_ACTIVE_INTERACTIONS = 8
_DEFAULT_INTERACTION_DURATION_TICKS = 3
_INTERACTION_STALE_GRACE_TICKS = 1
_MAX_NPC_REACTION_RECORDS = 64
_MAX_INTERACTION_REACTION_STATE = 16


def _normalize_runtime_settings(value: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize runtime settings to allowed values only."""
    if not isinstance(value, dict):
        value = {}
    result: Dict[str, Any] = {}
    # mode
    result["mode"] = _safe_str(value.get("mode") or "live").strip().lower() or "live"
    interaction_duration_mode = _safe_str(
        value.get("interaction_duration_mode") or "until_next_command"
    ).strip().lower()
    if interaction_duration_mode not in {"ticks", "until_next_command"}:
        interaction_duration_mode = "ticks"

    interaction_duration_ticks = _safe_int(value.get("interaction_duration_ticks"), 5)
    if interaction_duration_ticks < 1:
        interaction_duration_ticks = 1
    if interaction_duration_ticks > 20:
        interaction_duration_ticks = 20

    result["interaction_duration_mode"] = interaction_duration_mode
    result["interaction_duration_ticks"] = interaction_duration_ticks
    result["interaction_trace"] = _safe_bool(value.get("interaction_trace"), True)
    # response_length: keep existing semantics
    rl = value.get("response_length")
    if isinstance(rl, str):
        rl_value = rl.strip().lower()
        result["response_length"] = rl_value if rl_value in ("short", "medium", "long") else "short"
    elif isinstance(rl, dict):
        # Backward compatibility for older/broken frontend payloads that posted:
        # {"response_length": {"narrator_length": "...", "character_length": "..."}}
        fallback = str(rl.get("narrator_length") or rl.get("character_length") or "").strip().lower()
        result["response_length"] = fallback if fallback in ("short", "medium", "long") else "short"
    else:
        result["response_length"] = "short"
    # idle_conversation_seconds: only allowed values
    ics = value.get("idle_conversation_seconds")
    try:
        ics = int(ics)
    except (TypeError, ValueError):
        ics = 15
    result["idle_conversation_seconds"] = ics if ics in _ALLOWED_IDLE_SECONDS else 15
    # booleans
    for bkey in (
        "idle_conversations_enabled",
        "idle_npc_to_player_enabled",
        "idle_npc_to_npc_enabled",
        "follow_reactions_enabled",
        "console_debug_enabled",
        "world_events_panel_enabled",
    ):
        result[bkey] = bool(value.get(bkey, True))
    # reaction_style: only allowed enum
    rs = value.get("reaction_style")
    result["reaction_style"] = rs if isinstance(rs, str) and rs.strip().lower() in _ALLOWED_REACTION_STYLES else "normal"
    result["verbose_semantic_trace"] = _safe_bool(value.get("verbose_semantic_trace"), False)
    return result


def _ensure_semantic_action_runtime_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _copy_dict(runtime_state)
    runtime_state.setdefault("semantic_action_records", [])
    runtime_state.setdefault("semantic_action_index", {})
    return runtime_state


def _ensure_npc_reaction_runtime_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _copy_dict(runtime_state)
    runtime_state.setdefault("npc_reaction_records", [])
    runtime_state.setdefault("interaction_reaction_state", [])
    records = _safe_list(runtime_state.get("npc_reaction_records"))
    runtime_state["npc_reaction_records"] = records[-_MAX_NPC_REACTION_RECORDS:]
    state_rows = _safe_list(runtime_state.get("interaction_reaction_state"))
    runtime_state["interaction_reaction_state"] = state_rows[-_MAX_INTERACTION_REACTION_STATE:]
    return runtime_state


def _build_last_player_action_record(
    *,
    tick: int,
    player_input: str,
    action: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
) -> Dict[str, Any]:
    action = _safe_dict(action)
    semantic_action_record = _safe_dict(semantic_action_record)
    return {
        "action_id": f"player_action:{int(tick or 0)}",
        "tick": int(tick or 0),
        "text": _safe_str(player_input).strip()[:200],
        "action_type": _safe_str(
            semantic_action_record.get("action_type")
            or action.get("action_type")
        ).strip(),
        "target_id": _safe_str(
            semantic_action_record.get("target_id")
            or action.get("target_id")
            or action.get("npc_id")
        ).strip(),
        "semantic_action_id": _safe_str(
            semantic_action_record.get("semantic_action_id")
        ).strip(),
    }


def _clear_stale_last_player_action(
    runtime_state: Dict[str, Any],
    current_tick: int,
    max_age_ticks: int = 2,
) -> Dict[str, Any]:
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


def _ensure_active_interactions(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    interactions = _safe_list(simulation_state.get("active_interactions"))
    simulation_state["active_interactions"] = interactions
    return simulation_state


def _semantic_action_starts_persistent_interaction(record: Dict[str, Any]) -> bool:
    record = _safe_dict(record)
    action_type = _safe_str(record.get("action_type")).strip().lower()
    interaction_mode = _safe_str(record.get("interaction_mode")).strip().lower()
    visibility = _safe_str(record.get("visibility")).strip().lower()
    if action_type in {"social_competition", "social_affection", "social_performance", "threat"}:
        return True
    if interaction_mode in {"direct", "group", "public"} and visibility in {"local", "public"}:
        return True
    return False


def _interaction_duration_for_record(record: Dict[str, Any]) -> int:
    record = _safe_dict(record)
    action_type = _safe_str(record.get("action_type")).strip().lower()
    intensity = max(0, min(3, _safe_int(record.get("intensity"), 1)))
    if action_type == "social_competition":
        return _DEFAULT_INTERACTION_DURATION_TICKS + max(1, intensity)
    if action_type in {"social_performance", "threat"}:
        return _DEFAULT_INTERACTION_DURATION_TICKS + intensity
    return _DEFAULT_INTERACTION_DURATION_TICKS


def _get_interaction_duration_mode(runtime_state: Dict[str, Any]) -> str:
    runtime_state = _safe_dict(runtime_state)
    settings = _normalize_runtime_settings(_safe_dict(runtime_state.get("runtime_settings")))
    return _safe_str(settings.get("interaction_duration_mode") or "until_next_command").strip().lower() or "until_next_command"


def _get_interaction_duration_ticks(runtime_state: Dict[str, Any], record: Dict[str, Any]) -> int:
    runtime_state = _safe_dict(runtime_state)
    settings = _normalize_runtime_settings(_safe_dict(runtime_state.get("runtime_settings")))
    configured = _safe_int(settings.get("interaction_duration_ticks"), 5)
    if configured < 1:
        configured = 1
    if configured > 20:
        configured = 20
    return configured


def _compute_interaction_expires_tick(
    runtime_state: Dict[str, Any],
    record: Dict[str, Any],
    updated_tick: int,
) -> int:
    mode = _get_interaction_duration_mode(runtime_state)
    if mode == "until_next_command":
        # Large sentinel; explicit command transition / resolution will end it.
        return 10**9
    return _safe_int(updated_tick, 0) + _get_interaction_duration_ticks(runtime_state, record)


def _build_active_interaction_from_semantic_action(
    runtime_state: Dict[str, Any],
    record: Dict[str, Any],
) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    record = _safe_dict(record)
    tick = _safe_int(record.get("tick"), 0)
    target_id = _safe_str(record.get("target_id")).strip()
    location_id = _safe_str(record.get("location_id")).strip()
    action_type = _safe_str(record.get("action_type")).strip().lower()
    activity_label = _safe_str(record.get("activity_label")).strip().lower() or action_type or "interaction"
    scene_id = _safe_str(_safe_dict(runtime_state.get("current_scene")).get("scene_id"))
    interaction_id = f"semantic_interaction:{_safe_str(record.get('semantic_action_id'))}"
    return {
        "id": interaction_id,
        "type": "player_semantic_interaction",
        "subtype": activity_label,
        "semantic_action_id": _safe_str(record.get("semantic_action_id")),
        "action_type": action_type,
        "display_name": _safe_str(record.get("target_name") or activity_label.replace("_", " ")),
        "participants": ["player"] + ([target_id] if target_id else []),
        "location_id": location_id,
        "scene_id": scene_id,
        "phase": "active",
        "resolved": False,
        "started_tick": tick,
        "updated_tick": tick,
        "expires_tick": _compute_interaction_expires_tick(runtime_state, record, tick),
        "state": {
            "activity_label": activity_label,
            "visibility": _safe_str(record.get("visibility")),
            "intensity": _safe_int(record.get("intensity"), 1),
            "stakes": _safe_int(record.get("stakes"), 1),
            "summary": _safe_str(record.get("summary")),
            "duration_mode": _get_interaction_duration_mode(runtime_state),
            "duration_ticks": _get_interaction_duration_ticks(runtime_state, record),
        },
    }


def _upsert_active_interaction_from_semantic_action(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    record: Dict[str, Any],
) -> Dict[str, Any]:
    simulation_state = _ensure_active_interactions(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    record = _safe_dict(record)
    if not _semantic_action_starts_persistent_interaction(record):
        return simulation_state

    new_interaction = _build_active_interaction_from_semantic_action(runtime_state, record)
    semantic_action_id = _safe_str(record.get("semantic_action_id")).strip()
    target_id = _safe_str(record.get("target_id")).strip()
    action_type = _safe_str(record.get("action_type")).strip().lower()
    location_id = _safe_str(record.get("location_id")).strip()
    updated_tick = _safe_int(record.get("tick"), 0)

    next_items = []
    matched = False
    for raw in _safe_list(simulation_state.get("active_interactions")):
        item = _safe_dict(raw)
        same_semantic = _safe_str(item.get("semantic_action_id")).strip() == semantic_action_id and semantic_action_id
        same_shape = (
            _safe_str(item.get("action_type")).strip().lower() == action_type
            and _safe_str(item.get("location_id")).strip() == location_id
            and target_id in _safe_list(item.get("participants"))
        )
        if same_semantic or same_shape:
            item["updated_tick"] = updated_tick
            item["expires_tick"] = _compute_interaction_expires_tick(runtime_state, record, updated_tick)
            item["resolved"] = False
            item["phase"] = "active"
            state = _safe_dict(item.get("state"))
            state["summary"] = _safe_str(record.get("summary")) or _safe_str(state.get("summary"))
            state["activity_label"] = _safe_str(record.get("activity_label")) or _safe_str(state.get("activity_label"))
            state["duration_mode"] = _get_interaction_duration_mode(runtime_state)
            state["duration_ticks"] = _get_interaction_duration_ticks(runtime_state, record)
            item["state"] = state
            if semantic_action_id:
                item["semantic_action_id"] = semantic_action_id
            next_items.append(item)
            matched = True
        else:
            next_items.append(item)

    if not matched:
        next_items.append(new_interaction)

    next_items.sort(
        key=lambda x: (
            -_safe_int(_safe_dict(x).get("updated_tick"), 0),
            _safe_str(_safe_dict(x).get("id")),
        )
    )
    simulation_state["active_interactions"] = next_items[:_MAX_ACTIVE_INTERACTIONS]
    _log_interaction_trace(
        "upsert_active_interaction",
        {
            "tick": updated_tick,
            "semantic_action_id": semantic_action_id,
            "action_type": action_type,
            "target_id": target_id,
            "count": len(_safe_list(simulation_state.get("active_interactions"))),
            "items": _compact_active_interactions(_safe_list(simulation_state.get("active_interactions"))),
        },
        runtime_state,
    )
    return simulation_state


def _persist_player_interaction_state_after_turn(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    player_input: str,
    semantic_action_record: Dict[str, Any],
    current_tick: int,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    simulation_state = _ensure_simulation_state(_safe_dict(simulation_state))
    runtime_state = _copy_dict(runtime_state)
    semantic_action_record = _safe_dict(semantic_action_record)

    runtime_state["last_player_action"] = _build_last_player_action_record(
        tick=current_tick,
        player_input=player_input,
        action={"action_type": _safe_str(semantic_action_record.get("action_type")), "target_id": _safe_str(semantic_action_record.get("target_id"))},
        semantic_action_record=semantic_action_record,
    )

    simulation_state = _upsert_active_interaction_from_semantic_action(
        simulation_state,
        runtime_state,
        semantic_action_record,
    )

    return simulation_state, runtime_state


def _expire_stale_active_interactions(
    simulation_state: Dict[str, Any],
    current_tick: int,
) -> Dict[str, Any]:
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
    simulation_state: Dict[str, Any],
    current_tick: int,
) -> Dict[str, Any]:
    """Keep unresolved interactions visually current across idle ticks.

    This does not change lifecycle semantics. It only updates the interaction's
    display freshness so world-events sorting does not bury an ongoing player
    interaction under ambient activity rows.
    """
    simulation_state = _ensure_active_interactions(simulation_state)
    refreshed: list[Dict[str, Any]] = []

    for raw in _safe_list(simulation_state.get("active_interactions")):
        item = _safe_dict(raw)
        if not _safe_bool(item.get("resolved"), False):
            item["updated_tick"] = _safe_int(current_tick, 0)
        refreshed.append(item)

    simulation_state["active_interactions"] = refreshed[:_MAX_ACTIVE_INTERACTIONS]
    return simulation_state


def _build_active_interaction_prompt_context(
    simulation_state: Dict[str, Any],
    current_tick: int,
) -> List[Dict[str, Any]]:
    simulation_state = _safe_dict(simulation_state)
    rows = []
    for raw in _safe_list(simulation_state.get("active_interactions")):
        item = _safe_dict(raw)
        if _safe_bool(item.get("resolved"), False):
            continue
        expires_tick = _safe_int(item.get("expires_tick"), -999999)
        if expires_tick < _safe_int(current_tick, 0) - _INTERACTION_STALE_GRACE_TICKS:
            continue
        rows.append(
            {
                "id": _safe_str(item.get("id")),
                "type": _safe_str(item.get("type")),
                "subtype": _safe_str(item.get("subtype")),
                "action_type": _safe_str(item.get("action_type")),
                "participants": _safe_list(item.get("participants"))[:4],
                "location_id": _safe_str(item.get("location_id")),
                "phase": _safe_str(item.get("phase")),
                "summary": _safe_str(_safe_dict(item.get("state")).get("summary"))[:200],
                "expires_tick": expires_tick,
                "duration_mode": _safe_str(_safe_dict(item.get("state")).get("duration_mode")),
                "duration_ticks": _safe_int(_safe_dict(item.get("state")).get("duration_ticks"), 0),
            }
        )
    rows.sort(key=lambda x: (-_safe_int(x.get("expires_tick"), 0), _safe_str(x.get("id"))))
    return rows[:4]


def _run_npc_reaction_pass(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    current_tick: int,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    simulation_state = _ensure_simulation_state(_safe_dict(simulation_state))
    runtime_state = _ensure_npc_reaction_runtime_state(_safe_dict(runtime_state))

    interactions = _safe_list(simulation_state.get("active_interactions"))
    for raw in interactions:
        interaction = _safe_dict(raw)
        if _safe_bool(interaction.get("resolved"), False):
            continue
        context = build_interaction_reaction_context(simulation_state, runtime_state, interaction)
        context["tick"] = _safe_int(current_tick, 0)
        runtime_state = update_interaction_reaction_state(simulation_state, runtime_state, context)
        candidates = build_npc_reaction_candidates(simulation_state, runtime_state, context)
        reactions = select_npc_reactions(simulation_state, runtime_state, candidates)
        simulation_state, runtime_state = apply_npc_reactions(simulation_state, runtime_state, reactions)

    return simulation_state, runtime_state


def _semantic_action_matches_active_interaction(
    interaction: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
) -> bool:
    interaction = _safe_dict(interaction)
    semantic_action_record = _safe_dict(semantic_action_record)
    interaction_action_type = _safe_str(interaction.get("action_type")).strip().lower()
    interaction_subtype = _safe_str(interaction.get("subtype")).strip().lower()
    interaction_participants = set(str(x).strip() for x in _safe_list(interaction.get("participants")) if str(x).strip())

    record_action_type = _safe_str(semantic_action_record.get("action_type")).strip().lower()
    record_activity_label = _safe_str(semantic_action_record.get("activity_label")).strip().lower()
    record_target_id = _safe_str(semantic_action_record.get("target_id")).strip()

    if interaction_action_type and interaction_action_type == record_action_type:
        if interaction_subtype and record_activity_label and interaction_subtype == record_activity_label:
            if not record_target_id or record_target_id in interaction_participants:
                return True

    if record_target_id and record_target_id in interaction_participants and record_action_type == interaction_action_type:
        return True

    return False


def _resolve_until_next_command_interactions(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
    current_tick: int,
) -> Dict[str, Any]:
    simulation_state = _ensure_active_interactions(simulation_state)
    mode = _get_interaction_duration_mode(runtime_state)
    if mode != "until_next_command":
        return simulation_state

    semantic_action_record = _safe_dict(semantic_action_record)
    next_items = []
    resolved_ids = []
    for raw in _safe_list(simulation_state.get("active_interactions")):
        item = _safe_dict(raw)
        if _safe_bool(item.get("resolved"), False):
            next_items.append(item)
            continue
        if _semantic_action_matches_active_interaction(item, semantic_action_record):
            next_items.append(item)
            continue
        item["resolved"] = True
        item["phase"] = "resolved"
        item["updated_tick"] = _safe_int(current_tick, 0)
        item["expires_tick"] = _safe_int(current_tick, 0)
        resolved_ids.append(_safe_str(item.get("id")))
        next_items.append(item)
    simulation_state["active_interactions"] = next_items[:_MAX_ACTIVE_INTERACTIONS]
    if resolved_ids:
        _log_interaction_trace(
            "resolve_until_next_command",
            {
                "tick": _safe_int(current_tick, 0),
                "new_action_type": _safe_str(semantic_action_record.get("action_type")),
                "new_activity_label": _safe_str(semantic_action_record.get("activity_label")),
                "resolved_ids": resolved_ids,
                "remaining": _compact_active_interactions(_safe_list(simulation_state.get("active_interactions"))),
            },
            runtime_state,
        )
    return simulation_state


def _clean_resolved_interaction_world_event_rows(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Remove recent_world_event_rows that reference resolved interactions."""
    resolved_labels: set[str] = set()
    resolved_ids: set[str] = set()
    for raw in _safe_list(simulation_state.get("active_interactions")):
        item = _safe_dict(raw)
        if not _safe_bool(item.get("resolved"), False):
            continue
        state = _safe_dict(item.get("state"))
        label = _safe_str(state.get("activity_label") or item.get("subtype") or "").strip().lower()
        if label:
            resolved_labels.add(label)
        iid = _safe_str(item.get("id")).strip()
        if iid:
            resolved_ids.add(iid)
        sid = _safe_str(item.get("semantic_action_id")).strip()
        if sid:
            resolved_ids.add(sid)

    if not resolved_labels and not resolved_ids:
        return runtime_state

    def _row_references_resolved(row: Dict[str, Any]) -> bool:
        row = _safe_dict(row)
        eid = _safe_str(row.get("event_id")).strip().lower()
        row_id = _safe_str(row.get("reaction_id") or row.get("id")).strip().lower()
        summary_lower = _safe_str(row.get("summary")).strip().lower()
        # Normalize separators for matching
        summary_normalized = summary_lower.replace("-", " ").replace("_", " ")
        for label in resolved_labels:
            label_normalized = label.replace("_", " ").replace("-", " ")
            if label_normalized and (label_normalized in summary_lower or label_normalized in summary_normalized):
                return True
        for resolved_id in resolved_ids:
            resolved_lower = resolved_id.lower()
            if resolved_lower and (resolved_lower in eid or resolved_lower in row_id):
                return True
        return False

    # Clean recent_world_event_rows
    rows = _safe_list(runtime_state.get("recent_world_event_rows"))
    kept: list[Dict[str, Any]] = []
    for row in rows:
        row = _safe_dict(row)
        kind = _safe_str(row.get("kind")).strip().lower()
        # Skip non-interaction row kinds — always keep simulation/global rows
        if kind in ("world_event", "director_pressure"):
            kept.append(row)
            continue
        if _row_references_resolved(row):
            continue
        kept.append(row)
    runtime_state["recent_world_event_rows"] = kept[-_MAX_RECENT_WORLD_EVENT_ROWS:]

    # Clean recent_scene_beats
    beats = _safe_list(runtime_state.get("recent_scene_beats"))
    kept_beats: list[Dict[str, Any]] = []
    for beat in beats:
        beat = _safe_dict(beat)
        if _row_references_resolved(beat):
            continue
        kept_beats.append(beat)
    runtime_state["recent_scene_beats"] = kept_beats[-_MAX_RECENT_SCENE_BEATS:]

    # Clean world_consequences
    consequences = _safe_list(runtime_state.get("world_consequences"))
    kept_consequences: list[Dict[str, Any]] = []
    for c in consequences:
        if not _row_references_resolved(_safe_dict(c)):
            kept_consequences.append(c)
    runtime_state["world_consequences"] = kept_consequences[-_MAX_WORLD_CONSEQUENCES:]

    # Clean world_rumors
    rumors = _safe_list(runtime_state.get("world_rumors"))
    kept_rumors: list[Dict[str, Any]] = []
    for r in rumors:
        if not _row_references_resolved(_safe_dict(r)):
            kept_rumors.append(r)
    runtime_state["world_rumors"] = kept_rumors[-_MAX_WORLD_RUMORS:]

    # Clean world_pressure
    pressure = _safe_list(runtime_state.get("world_pressure"))
    kept_pressure: list[Dict[str, Any]] = []
    for p in pressure:
        if not _row_references_resolved(_safe_dict(p)):
            kept_pressure.append(p)
    runtime_state["world_pressure"] = kept_pressure[-_MAX_WORLD_PRESSURE:]

    # Clean npc_reaction_records tied to resolved interactions
    reaction_records = _safe_list(runtime_state.get("npc_reaction_records"))
    kept_reaction_records: list[Dict[str, Any]] = []
    for record in reaction_records:
        record = _safe_dict(record)
        interaction_id = _safe_str(record.get("interaction_id")).strip()
        if interaction_id and interaction_id in resolved_ids:
            continue
        kept_reaction_records.append(record)
    runtime_state["npc_reaction_records"] = kept_reaction_records[-_MAX_NPC_REACTION_RECORDS:]

    # Clean escalation state tied to resolved interactions
    reaction_state_rows = _safe_list(runtime_state.get("interaction_reaction_state"))
    kept_reaction_state_rows: list[Dict[str, Any]] = []
    for row in reaction_state_rows:
        row = _safe_dict(row)
        interaction_id = _safe_str(row.get("interaction_id")).strip()
        if interaction_id and interaction_id in resolved_ids:
            continue
        kept_reaction_state_rows.append(row)
    runtime_state["interaction_reaction_state"] = kept_reaction_state_rows[-_MAX_INTERACTION_REACTION_STATE:]

    return runtime_state


def _prune_llm_records_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _copy_dict(runtime_state)
    records = _safe_list(runtime_state.get("llm_records"))[-_MAX_RUNTIME_LLM_RECORDS:]
    new_index: Dict[str, Any] = {}
    for item in records:
        item = _safe_dict(item)
        record_type = _safe_str(item.get("type")).strip()
        tick = _safe_int(item.get("tick"), -1)
        if tick < 0 or not record_type:
            continue
        new_index[f"{record_type}:{tick}"] = item
    runtime_state["llm_records"] = records
    runtime_state["llm_records_index"] = new_index
    return runtime_state


def _stable_semantic_action_id(tick: int, player_input: str, action_type: str, target_id: str, activity_label: str) -> str:
    material = json.dumps(
        {
            "tick": int(tick or 0),
            "player_input": _safe_str(player_input).strip(),
            "action_type": _safe_str(action_type).strip(),
            "target_id": _safe_str(target_id).strip(),
            "activity_label": _safe_str(activity_label).strip(),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return "semantic_action_" + hashlib.sha1(material.encode("utf-8")).hexdigest()[:16]


def _find_npc_target_by_name(simulation_state: Dict[str, Any], text: str) -> str:
    simulation_state = _safe_dict(simulation_state)
    npc_index = _safe_dict(simulation_state.get("npc_index"))
    text_lc = _safe_str(text).strip().lower()
    if not text_lc:
        return ""

    candidates: List[tuple[str, str]] = []
    for npc_id, raw in sorted(npc_index.items()):
        npc = _safe_dict(raw)
        name = _safe_str(npc.get("name")).strip().lower()
        role = _safe_str(npc.get("role")).strip().lower()
        title = _safe_str(npc.get("title")).strip().lower()
        stable_id = _safe_str(npc.get("id") or npc_id)
        if stable_id and name:
            candidates.append((stable_id, name))
        if stable_id and role:
            candidates.append((stable_id, role))
        if stable_id and title:
            candidates.append((stable_id, title))

    candidates.sort(key=lambda item: (-len(item[1]), item[1], item[0]))
    for npc_id, npc_name in candidates:
        if npc_name in text_lc:
            return npc_id
    return ""


def _coerce_action_target(simulation_state: Dict[str, Any], action: Dict[str, Any], player_input: str) -> Dict[str, Any]:
    action = _safe_dict(action)
    target_id = _safe_str(action.get("target_id") or action.get("npc_id")).strip()
    if not target_id:
        target_id = _find_npc_target_by_name(simulation_state, player_input)
    if target_id and not _safe_str(action.get("target_id")).strip():
        action["target_id"] = target_id
    return action


def _normalize_social_axes(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for item in _safe_list(items)[:4]:
        item = _safe_dict(item)
        axis = _safe_str(item.get("axis")).strip().lower()
        delta = _safe_int(item.get("delta"), 0)
        if not axis or delta == 0:
            continue
        if delta > 2:
            delta = 2
        if delta < -2:
            delta = -2
        key = (axis, delta)
        if key in seen:
            continue
        seen.add(key)
        out.append({"axis": axis, "delta": delta})
    return out


def _compile_semantic_action_record(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    player_input: str,
    action: Dict[str, Any],
    semantic_advisory: Dict[str, Any],
) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    action = _safe_dict(action)
    semantic_advisory = _safe_dict(semantic_advisory)

    tick = int(simulation_state.get("tick", runtime_state.get("tick", 0)) or 0) + 1
    player_state = _safe_dict(simulation_state.get("player_state"))
    current_scene = _safe_dict(runtime_state.get("current_scene"))

    target_id = _safe_str(semantic_advisory.get("target_id")).strip()
    if not target_id:
        target_id = _safe_str(action.get("target_id")).strip()
    if not target_id:
        target_id = _find_npc_target_by_name(simulation_state, player_input)

    npc_index = _safe_dict(simulation_state.get("npc_index"))
    target_npc = _safe_dict(npc_index.get(target_id))
    target_name = _safe_str(
        semantic_advisory.get("target_name")
        or target_npc.get("name")
        or action.get("target_name")
        or target_id
    ).strip()

    action_type = _safe_str(semantic_advisory.get("action_type") or action.get("action_type")).strip().lower() or "observe"
    semantic_family = _safe_str(semantic_advisory.get("semantic_family")).strip().lower() or "observation"
    interaction_mode = _safe_str(semantic_advisory.get("interaction_mode")).strip().lower() or ("direct" if target_id else "solo")
    activity_label = _safe_str(semantic_advisory.get("activity_label")).strip().lower().replace(" ", "_") or action_type
    visibility = _safe_str(semantic_advisory.get("visibility")).strip().lower() or "local"
    intensity = max(0, min(3, _safe_int(semantic_advisory.get("intensity"), 1)))
    stakes = max(0, min(3, _safe_int(semantic_advisory.get("stakes"), 1)))
    social_axes = _normalize_social_axes(_safe_list(semantic_advisory.get("social_axes")))
    observer_hooks = [str(x).strip().lower() for x in _safe_list(semantic_advisory.get("observer_hooks")) if str(x).strip()][:4]
    scene_impact = _safe_str(semantic_advisory.get("scene_impact")).strip().lower() or "none"

    location_id = _safe_str(
        current_scene.get("location_id")
        or player_state.get("location_id")
        or _safe_dict(target_npc).get("location_id")
    )

    semantic_action_id = _stable_semantic_action_id(
        tick=tick,
        player_input=player_input,
        action_type=action_type,
        target_id=target_id,
        activity_label=activity_label,
    )

    summary_parts = []
    if target_name:
        summary_parts.append(target_name)
    if activity_label:
        summary_parts.append(activity_label.replace("_", " "))
    summary = " / ".join(summary_parts).strip() or _safe_str(player_input).strip()[:120]

    return {
        "semantic_action_id": semantic_action_id,
        "tick": tick,
        "player_input": _safe_str(player_input).strip(),
        "action_type": action_type,
        "semantic_family": semantic_family,
        "interaction_mode": interaction_mode,
        "activity_label": activity_label,
        "target_id": target_id,
        "target_name": target_name,
        "secondary_actor_ids": [str(x).strip() for x in _safe_list(semantic_advisory.get("secondary_actor_ids")) if str(x).strip()][:4],
        "location_id": location_id,
        "visibility": visibility,
        "intensity": intensity,
        "stakes": stakes,
        "social_axes": social_axes,
        "observer_hooks": observer_hooks,
        "scene_impact": scene_impact,
        "reason": _safe_str(semantic_advisory.get("reason")).strip()[:200],
        "summary": summary[:160],
        "tags": sorted(list({
            "player_action",
            semantic_family or "semantic",
            action_type or "action",
            activity_label or "activity",
        })),
    }


def _append_simulation_semantic_event(simulation_state: Dict[str, Any], record: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    record = _safe_dict(record)
    if not record:
        return simulation_state

    event_history = _safe_list(simulation_state.get("event_history"))
    tick = _safe_int(record.get("tick"), 0)
    event_id = f"semantic_event:{_safe_str(record.get('semantic_action_id'))}"
    for existing in event_history:
        existing = _safe_dict(existing)
        if _safe_str(existing.get("id")) == event_id:
            return simulation_state
    event = {
        "id": event_id,
        "tick": tick,
        "type": "player_semantic_action",
        "category": "player_action",
        "source": "semantic_action_bridge",
        "location_id": _safe_str(record.get("location_id")),
        "actor_ids": ["player"] + ([_safe_str(record.get("target_id"))] if _safe_str(record.get("target_id")) else []),
        "payload": {
            "semantic_action_id": _safe_str(record.get("semantic_action_id")),
            "action_type": _safe_str(record.get("action_type")),
            "semantic_family": _safe_str(record.get("semantic_family")),
            "interaction_mode": _safe_str(record.get("interaction_mode")),
            "activity_label": _safe_str(record.get("activity_label")),
            "target_id": _safe_str(record.get("target_id")),
            "target_name": _safe_str(record.get("target_name")),
            "visibility": _safe_str(record.get("visibility")),
            "intensity": _safe_int(record.get("intensity"), 1),
            "stakes": _safe_int(record.get("stakes"), 1),
            "social_axes": _safe_list(record.get("social_axes")),
            "observer_hooks": _safe_list(record.get("observer_hooks")),
            "scene_impact": _safe_str(record.get("scene_impact")),
            "summary": _safe_str(record.get("summary")),
            "tags": _safe_list(record.get("tags")),
        },
    }
    event_history.append(event)
    simulation_state["event_history"] = event_history[-256:]
    return simulation_state


def _append_semantic_action_record(runtime_state: Dict[str, Any], record: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _ensure_semantic_action_runtime_state(runtime_state)
    record = _safe_dict(record)
    items = _safe_list(runtime_state.get("semantic_action_records"))
    index = _safe_dict(runtime_state.get("semantic_action_index"))
    record_id = _safe_str(record.get("semantic_action_id")).strip()
    if not record_id:
        return runtime_state
    if record_id in index:
        return runtime_state
    items.append(record)
    index[record_id] = record
    runtime_state["semantic_action_records"] = items[-_MAX_SEMANTIC_ACTION_RECORDS:]
    runtime_state["semantic_action_index"] = index
    return runtime_state


def _semantic_activity_kind(record: Dict[str, Any]) -> str:
    record = _safe_dict(record)
    action_type = _safe_str(record.get("action_type"))
    semantic_family = _safe_str(record.get("semantic_family"))
    if action_type == "social_competition":
        return "player_social_competition"
    if action_type == "social_affection":
        return "player_social_affection"
    if action_type == "social_performance":
        return "player_social_performance"
    if action_type == "trade":
        return "player_trade"
    if action_type == "ritual":
        return "player_ritual"
    if semantic_family == "social":
        return "player_social_activity"
    return "player_engaged"


def _semantic_consequence_summary(record: Dict[str, Any]) -> str:
    record = _safe_dict(record)
    target_name = _safe_str(record.get("target_name"))
    activity_label = _safe_str(record.get("activity_label")).replace("_", " ")
    action_type = _safe_str(record.get("action_type"))
    visibility = _safe_str(record.get("visibility"))

    if action_type == "social_competition":
        return f"A {activity_label or 'contest'} between the player and {target_name or 'someone'} draws a crowd."
    if action_type == "social_affection":
        return f"{target_name or 'Someone'} reacts warmly to the player."
    if action_type == "social_performance":
        return f"The player's {activity_label or 'performance'} shifts the local mood."
    if action_type == "trade":
        return f"The player's {activity_label or 'exchange'} changes the local social flow."
    if action_type == "ritual":
        return f"The player's {activity_label or 'ritual'} leaves a noticeable impression."
    if visibility == "public":
        return f"The player's {activity_label or 'action'} becomes the center of attention."
    return f"The player's {activity_label or 'action'} affects the immediate scene."


def _safe_relationship_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    relationships = _safe_dict(simulation_state.get("relationship_state"))
    simulation_state["relationship_state"] = relationships
    return relationships


def _relationship_bucket_key(a: str, b: str) -> str:
    left = _safe_str(a).strip()
    right = _safe_str(b).strip()
    ordered = sorted([left, right])
    return f"{ordered[0]}::{ordered[1]}"


def _apply_semantic_social_axes_to_relationships(
    simulation_state: Dict[str, Any],
    record: Dict[str, Any],
) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    record = _safe_dict(record)
    target_id = _safe_str(record.get("target_id")).strip()
    if not target_id:
        return simulation_state

    relationships = _safe_relationship_state(simulation_state)
    rel_key = _relationship_bucket_key("player", target_id)
    rel = _safe_dict(relationships.get(rel_key))
    axes = _safe_dict(rel.get("axes"))

    for item in _safe_list(record.get("social_axes")):
        item = _safe_dict(item)
        axis = _safe_str(item.get("axis")).strip().lower()
        delta = _safe_int(item.get("delta"), 0)
        if not axis or delta == 0:
            continue
        current = _safe_int(axes.get(axis), 0)
        next_value = current + delta
        if next_value > 10:
            next_value = 10
        if next_value < -10:
            next_value = -10
        axes[axis] = next_value

    rel["pair"] = ["player", target_id]
    rel["axes"] = axes
    rel["updated_tick"] = _safe_int(record.get("tick"), 0)
    relationships[rel_key] = rel
    simulation_state["relationship_state"] = relationships
    return simulation_state


def _derive_semantic_observer_ids(
    simulation_state: Dict[str, Any],
    record: Dict[str, Any],
) -> List[str]:
    simulation_state = _safe_dict(simulation_state)
    record = _safe_dict(record)
    target_id = _safe_str(record.get("target_id")).strip()
    location_id = _safe_str(record.get("location_id")).strip()
    npc_index = _safe_dict(simulation_state.get("npc_index"))

    observer_ids: List[str] = []
    for npc_id, raw in sorted(npc_index.items()):
        npc = _safe_dict(raw)
        stable_id = _safe_str(npc.get("id") or npc_id).strip()
        if not stable_id or stable_id == target_id:
            continue
        npc_location = _safe_str(npc.get("location_id")).strip()
        if location_id and npc_location and npc_location != location_id:
            continue
        observer_ids.append(stable_id)
    return observer_ids[:4]


def _build_observer_activity_summary(
    observer_name: str,
    record: Dict[str, Any],
) -> str:
    record = _safe_dict(record)
    action_type = _safe_str(record.get("action_type"))
    activity_label = _safe_str(record.get("activity_label")).replace("_", " ")
    target_name = _safe_str(record.get("target_name")) or "someone"

    if action_type == "social_competition":
        return f"{observer_name} watches the {activity_label or 'contest'} with {target_name} closely."
    if action_type == "social_performance":
        return f"{observer_name} pays attention to the player's {activity_label or 'performance'}."
    if action_type == "social_affection":
        return f"{observer_name} notices the warm exchange between the player and {target_name}."
    return f"{observer_name} reacts to the player's action nearby."


def _apply_semantic_observer_reactions(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    record: Dict[str, Any],
) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = ensure_actor_activity_state(runtime_state)
    record = _safe_dict(record)

    hooks = [str(x).strip().lower() for x in _safe_list(record.get("observer_hooks")) if str(x).strip()]
    if not any(h in {"spectacle", "crowd_attention", "authority_notice", "conversation_seed", "relationship_shift", "rumor_seed"} for h in hooks):
        return runtime_state

    tick = _safe_int(record.get("tick"), 0)
    location_id = _safe_str(record.get("location_id"))
    npc_index = _safe_dict(simulation_state.get("npc_index"))

    for observer_id in _derive_semantic_observer_ids(simulation_state, record):
        npc = _safe_dict(npc_index.get(observer_id))
        observer_name = _safe_str(npc.get("name") or observer_id)
        activity_kind = "observer_reaction"
        if "authority_notice" in hooks and ("guard" in observer_name.lower() or "captain" in observer_name.lower() or "watch" in observer_name.lower()):
            activity_kind = "authority_observation"

        runtime_state = set_actor_activity(
            runtime_state,
            observer_id,
            _normalize_activity_record(
                {
                    "activity_id": _stable_activity_id(observer_id, tick, activity_kind, location_id),
                    "kind": activity_kind,
                    "subtype": _safe_str(record.get("activity_label")),
                    "summary": _build_observer_activity_summary(observer_name, record),
                    "location_id": location_id,
                    "target_id": _safe_str(record.get("target_id")),
                    "target_label": _safe_str(record.get("target_name")),
                    "started_tick": tick,
                    "updated_tick": tick,
                    "expected_duration": 2,
                    "status": "active",
                    "intent": "React to a notable player-driven local event.",
                    "world_tags": _safe_list(record.get("tags")) + ["observer_reaction"],
                    "priority": 4,
                }
            ),
        )

    return runtime_state


def _append_semantic_world_pressure(runtime_state: Dict[str, Any], pressure: Dict[str, Any]) -> Dict[str, Any]:
    items = _safe_list(runtime_state.get("world_pressure"))
    pressure = _safe_dict(pressure)
    pressure_id = _safe_str(pressure.get("pressure_id")).strip()
    if pressure_id and any(_safe_str(_safe_dict(existing).get("pressure_id")) == pressure_id for existing in items):
        return runtime_state
    items.append(pressure)
    runtime_state["world_pressure"] = items[-64:]
    return runtime_state


def _append_semantic_world_rumor(runtime_state: Dict[str, Any], rumor: Dict[str, Any]) -> Dict[str, Any]:
    items = _safe_list(runtime_state.get("world_rumors"))
    rumor = _safe_dict(rumor)
    rumor_id = _safe_str(rumor.get("rumor_id")).strip()
    if rumor_id and any(_safe_str(_safe_dict(existing).get("rumor_id")) == rumor_id for existing in items):
        return runtime_state
    items.append(rumor)
    runtime_state["world_rumors"] = items[-64:]
    return runtime_state


def _apply_semantic_world_propagation(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    record: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = ensure_world_consequence_state(runtime_state)
    record = _safe_dict(record)
    hooks = [str(x).strip().lower() for x in _safe_list(record.get("observer_hooks")) if str(x).strip()]
    tick = _safe_int(record.get("tick"), 0)
    location_id = _safe_str(record.get("location_id"))
    action_type = _safe_str(record.get("action_type"))
    activity_label = _safe_str(record.get("activity_label")).replace("_", " ")
    target_name = _safe_str(record.get("target_name"))
    intensity = max(0, min(3, _safe_int(record.get("intensity"), 1)))
    visibility = _safe_str(record.get("visibility"))

    simulation_state = _apply_semantic_social_axes_to_relationships(simulation_state, record)
    runtime_state = _apply_semantic_observer_reactions(simulation_state, runtime_state, record)

    if visibility == "public" or "crowd_attention" in hooks or "spectacle" in hooks:
        runtime_state = _append_world_pressure(
            runtime_state,
            {
                "pressure_id": f"semantic_pressure:{_safe_str(record.get('semantic_action_id'))}",
                "tick": tick,
                "kind": "local_attention",
                "location_id": location_id,
                "summary": f"Attention builds around the player's {activity_label or 'action'}.",
                "intensity": intensity,
                "tags": _safe_list(record.get("tags")) + ["crowd_attention"],
            },
        )

    if "rumor_seed" in hooks or (visibility == "public" and action_type in {"social_competition", "social_performance", "threat"}):
        runtime_state = _append_world_rumor(
            runtime_state,
            {
                "rumor_id": f"semantic_rumor:{_safe_str(record.get('semantic_action_id'))}",
                "tick": tick,
                "location_id": location_id,
                "summary": (
                    f"People start talking about the player's {activity_label or 'action'}"
                    + (f" with {target_name}" if target_name else "")
                    + "."
                ),
                "intensity": intensity,
                "tags": _safe_list(record.get("tags")) + ["rumor_seed"],
            },
        )

    if _safe_str(record.get("scene_impact")) in {"gathers_attention", "changes_mood", "disrupts_flow"}:
        consequence_summary = {
            "gathers_attention": f"The scene grows more focused on the player's {activity_label or 'action'}.",
            "changes_mood": f"The mood shifts after the player's {activity_label or 'action'}.",
            "disrupts_flow": f"The usual rhythm of the area is disrupted by the player's {activity_label or 'action'}.",
        }.get(_safe_str(record.get("scene_impact")), "")
        if consequence_summary:
            runtime_state = _append_semantic_world_consequence(
                runtime_state,
                {
                    "consequence_id": _stable_consequence_id(
                        "consequence",
                        tick,
                        "local" if location_id else "global",
                        location_id or "player",
                        consequence_summary,
                    ),
                    "kind": "semantic_scene_impact",
                    "scope": "local" if location_id else "global",
                    "location_id": location_id,
                    "summary": consequence_summary,
                    "source_actor_id": _safe_str(record.get("target_id")),
                    "tick": tick,
                    "priority": 0.7,
                    "tags": _safe_list(record.get("tags")) + ["scene_impact"],
                },
            )

    return simulation_state, runtime_state


def _append_world_event_row(runtime_state: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
    rows = _safe_list(runtime_state.get("recent_world_event_rows"))
    row = _safe_dict(row)
    row_id = _safe_str(row.get("event_id")).strip()
    if row_id and any(_safe_str(_safe_dict(existing).get("event_id")) == row_id for existing in rows):
        return runtime_state
    rows.append(row)
    runtime_state["recent_world_event_rows"] = rows[-_MAX_RECENT_WORLD_EVENT_ROWS:]
    return runtime_state


def _append_semantic_world_consequence(runtime_state: Dict[str, Any], consequence: Dict[str, Any]) -> Dict[str, Any]:
    items = _safe_list(runtime_state.get("world_consequences"))
    consequence = _safe_dict(consequence)
    consequence_id = _safe_str(consequence.get("consequence_id")).strip()
    if consequence_id and any(_safe_str(_safe_dict(existing).get("consequence_id")) == consequence_id for existing in items):
        return runtime_state
    items.append(consequence)
    runtime_state["world_consequences"] = items[-_MAX_WORLD_CONSEQUENCES:]
    return runtime_state


def _emit_scene_beat_from_semantic_action(runtime_state: Dict[str, Any], record: Dict[str, Any]) -> Dict[str, Any]:
    beats = _safe_list(runtime_state.get("recent_scene_beats"))
    record = _safe_dict(record)
    tick = _safe_int(record.get("tick"), 0)
    beat_id = f"semantic_beat:{_safe_str(record.get('semantic_action_id'))}"
    if any(_safe_str(_safe_dict(existing).get("beat_id")) == beat_id for existing in beats):
        return runtime_state
    beat = {
        "beat_id": beat_id,
        "tick": tick,
        "kind": "interaction_beat",
        "summary": _safe_str(record.get("summary")) or _safe_str(record.get("player_input")),
        "priority": 0.8 if _safe_str(record.get("action_type")) == "social_competition" else 0.68,
        "scene_id": _safe_str(_safe_dict(runtime_state.get("current_scene")).get("scene_id")),
        "interaction_id": f"semantic_interaction:{_safe_str(record.get('semantic_action_id'))}",
        "actors": ["player"] + ([_safe_str(record.get("target_id"))] if _safe_str(record.get("target_id")) else []),
        "location_id": _safe_str(record.get("location_id")),
        "recap_level": "major" if _safe_str(record.get("action_type")) in ("social_competition", "social_performance") else "notable",
        "tags": _safe_list(record.get("tags")),
    }
    beats.append(beat)
    runtime_state["recent_scene_beats"] = beats[-_MAX_RECENT_SCENE_BEATS:]
    return runtime_state


def _apply_semantic_action_to_runtime(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    record: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = ensure_world_consequence_state(runtime_state)
    runtime_state = ensure_actor_activity_state(runtime_state)
    runtime_state = _ensure_semantic_action_runtime_state(runtime_state)
    record = _safe_dict(record)
    if not record:
        return simulation_state, runtime_state

    target_id = _safe_str(record.get("target_id"))
    target_name = _safe_str(record.get("target_name") or target_id)
    tick = _safe_int(record.get("tick"), 0)
    location_id = _safe_str(record.get("location_id"))
    activity_kind = _semantic_activity_kind(record)

    if target_id:
        runtime_state = set_actor_activity(
            runtime_state,
            target_id,
            _normalize_activity_record(
                {
                    "activity_id": _stable_activity_id(target_id, tick, activity_kind, location_id),
                    "kind": activity_kind,
                    "subtype": _safe_str(record.get("activity_label")),
                    "summary": (
                        f"{target_name} is engaged in { _safe_str(record.get('activity_label')).replace('_', ' ') } with the player."
                        if _safe_str(record.get("activity_label"))
                        else f"{target_name} is focused on the player."
                    ),
                    "location_id": location_id,
                    "target_id": "player",
                    "target_label": "Player",
                    "started_tick": tick,
                    "updated_tick": tick,
                    "expected_duration": 2 if _safe_str(record.get("action_type")) != "social_competition" else 3,
                    "status": "active",
                    "intent": "Respond directly to the player's immediate action.",
                    "world_tags": _safe_list(record.get("tags")) + ["player_engaged"],
                    "priority": 5 if _safe_str(record.get("action_type")) == "social_competition" else 4,
                }
            ),
        )

    simulation_state = _upsert_active_interaction_from_semantic_action(
        simulation_state,
        runtime_state,
        record,
    )

    consequence_summary = _semantic_consequence_summary(record)
    consequence = {
        "consequence_id": _stable_consequence_id(
            "consequence",
            tick,
            "local" if location_id else "global",
            location_id or target_id or "player",
            consequence_summary,
        ),
        "kind": "player_action_consequence",
        "scope": "local" if location_id else "global",
        "location_id": location_id,
        "summary": consequence_summary,
        "source_actor_id": target_id,
        "tick": tick,
        "priority": 0.8 if _safe_str(record.get("action_type")) in ("social_competition", "social_performance") else 0.65,
        "tags": _safe_list(record.get("tags")),
    }
    runtime_state = _append_world_consequence(runtime_state, consequence)
    runtime_state = _append_world_event_row(
        runtime_state,
        {
            "event_id": f"semantic_action_row:{_safe_str(record.get('semantic_action_id'))}",
            "scope": "local" if location_id else "global",
            "kind": "player_action_consequence",
            "title": "World Consequence",
            "summary": consequence_summary,
            "tick": tick,
            "actors": [target_id] if target_id else [],
            "actor_id": target_id,
            "location_id": location_id,
            "priority": consequence.get("priority"),
            "status": "active",
            "source": "semantic_player_runtime",
            "tags": _safe_list(record.get("tags")),
        },
     )
    simulation_state, runtime_state = _apply_semantic_world_propagation(
        simulation_state,
        runtime_state,
        record,
    )
    simulation_state = _append_simulation_semantic_event(simulation_state, record)
    runtime_state = _emit_scene_beat_from_semantic_action(runtime_state, record)
    runtime_state = _append_semantic_action_record(runtime_state, record)
    return simulation_state, runtime_state


def _record_real_player_activity(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    """Record real player activity timestamp and reset idle streak."""
    runtime_state["last_real_player_activity_at"] = _utc_now_iso()
    runtime_state["idle_streak"] = 0
    return runtime_state


_CRITICAL_REACTION_KINDS = frozenset({"follow_reaction", "caution_reaction", "assist_reaction", "warning"})
_MOVEMENT_RUSH_KEYWORDS = frozenset({"run", "sprint", "rush", "charge", "hurry", "dash", "race"})
_MOVEMENT_ADVANCE_KEYWORDS = frozenset({"walk", "move", "go", "continue", "advance", "proceed", "head", "enter", "step"})
_MOVEMENT_RETREAT_KEYWORDS = frozenset({"retreat", "flee", "escape", "back", "withdraw", "fall back", "run away"})
_MOVEMENT_INSPECT_KEYWORDS = frozenset({"look", "inspect", "examine", "investigate", "search", "study", "check", "peer"})
_MOVEMENT_WAIT_KEYWORDS = frozenset({"wait", "pause", "hold", "stay", "rest", "stop"})
_MOVEMENT_TALK_KEYWORDS = frozenset({"talk", "speak", "ask", "tell", "say", "greet", "address", "chat"})
_MOVEMENT_ATTACK_KEYWORDS = frozenset({"attack", "strike", "fight", "hit", "slash", "stab", "shoot", "cast"})
_MOVEMENT_APPROACH_KEYWORDS = frozenset({"approach", "near", "toward", "towards", "close"})

_HIGH_RISK_KEYWORDS = frozenset({"attack", "fight", "charge", "rush", "strike", "slash", "stab", "shoot", "cast", "confront"})
_MEDIUM_RISK_KEYWORDS = frozenset({"investigate", "enter", "approach", "sneak", "climb", "jump", "cross"})


def _classify_player_action_context(
    player_input: str,
    resolved_result: Dict[str, Any],
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Classify player action into a bounded deterministic context dict.

    Uses simple keyword-based classification. No LLM call.
    """
    player_input = _safe_str(player_input).strip()
    resolved_result = _safe_dict(resolved_result)
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)

    words = set(player_input.lower().split())
    text_lower = player_input.lower()

    # Determine movement intent
    movement_intent = "unknown"
    if words & _MOVEMENT_RUSH_KEYWORDS or any(k in text_lower for k in ("run toward", "sprint to", "rush to")):
        movement_intent = "rush"
    elif words & _MOVEMENT_RETREAT_KEYWORDS or "fall back" in text_lower or "run away" in text_lower:
        movement_intent = "retreat"
    elif words & _MOVEMENT_APPROACH_KEYWORDS or "toward" in text_lower:
        movement_intent = "approach"
    elif words & _MOVEMENT_ATTACK_KEYWORDS:
        movement_intent = "attack"
    elif words & _MOVEMENT_TALK_KEYWORDS:
        movement_intent = "talk"
    elif words & _MOVEMENT_INSPECT_KEYWORDS:
        movement_intent = "inspect"
    elif words & _MOVEMENT_WAIT_KEYWORDS:
        movement_intent = "wait"
    elif words & _MOVEMENT_ADVANCE_KEYWORDS:
        movement_intent = "advance"

    # Determine risk level
    risk_level = "low"
    if words & _HIGH_RISK_KEYWORDS:
        risk_level = "high"
    elif words & _MEDIUM_RISK_KEYWORDS:
        risk_level = "medium"

    # Determine urgency
    urgency = "low"
    if movement_intent in ("rush", "attack"):
        urgency = "high"
    elif movement_intent in ("approach", "retreat"):
        urgency = "medium"

    action_type = _safe_str(resolved_result.get("action_type"))
    target_id = _safe_str(resolved_result.get("target_id"))
    target_name = _safe_str(resolved_result.get("target_name"))
    player_state = _safe_dict(simulation_state.get("player_state"))
    location_id = _safe_str(player_state.get("location_id"))
    tick = int(simulation_state.get("tick", runtime_state.get("tick", 0)) or 0)

    return {
        "tick": tick,
        "player_input": player_input[:200],
        "action_type": action_type,
        "movement_intent": movement_intent,
        "risk_level": risk_level,
        "urgency": urgency,
        "target_id": target_id,
        "target_name": target_name,
        "location_id": location_id,
    }


def _seconds_since_iso(iso_str: str) -> int:
    """Return seconds elapsed since an ISO timestamp. Returns 9999 if invalid."""
    iso_str = _safe_str(iso_str).strip()
    if not iso_str:
        return 9999
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return max(0, int(delta.total_seconds()))
    except Exception:
        return 9999


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _stable_scene_beat_id(beat: Dict[str, Any]) -> str:
    payload = {
        "tick": int(_safe_dict(beat).get("tick", 0) or 0),
        "kind": _safe_str(_safe_dict(beat).get("kind")),
        "summary": _safe_str(_safe_dict(beat).get("summary")),
        "scene_id": _safe_str(_safe_dict(beat).get("scene_id")),
        "interaction_id": _safe_str(_safe_dict(beat).get("interaction_id")),
        "actors": sorted([_safe_str(x) for x in _safe_list(_safe_dict(beat).get("actors")) if _safe_str(x)]),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return "scene_beat_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _normalize_scene_beat(beat: Dict[str, Any]) -> Dict[str, Any]:
    beat = _safe_dict(beat)
    out = {
        "id": _safe_str(beat.get("id")),
        "tick": int(beat.get("tick", 0) or 0),
        "kind": _safe_str(beat.get("kind")) or "scene_beat",
        "summary": _safe_str(beat.get("summary")),
        "priority": int(beat.get("priority", 50) or 50),
        "scene_id": _safe_str(beat.get("scene_id")),
        "interaction_id": _safe_str(beat.get("interaction_id")),
        "actors": [_safe_str(x) for x in _safe_list(beat.get("actors")) if _safe_str(x)],
        "location_id": _safe_str(beat.get("location_id")),
        "recap_level": _safe_str(beat.get("recap_level")) or "notable",
        "tags": [_safe_str(x) for x in _safe_list(beat.get("tags")) if _safe_str(x)],
    }
    if not out["id"]:
        out["id"] = _stable_scene_beat_id(out)
    return out


def _ensure_recent_scene_beats(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    beats = []
    seen = set()
    for beat in _safe_list(runtime_state.get("recent_scene_beats")):
        norm = _normalize_scene_beat(beat)
        if not norm["summary"]:
            continue
        if norm["id"] in seen:
            continue
        seen.add(norm["id"])
        beats.append(norm)
    beats.sort(key=lambda item: (int(item.get("tick", 0)), int(item.get("priority", 0)), _safe_str(item.get("id"))))
    runtime_state["recent_scene_beats"] = beats[-_MAX_RECENT_SCENE_BEATS:]
    return runtime_state


# ── World consequence state ──────────────────────────────────────────────────

def _stable_consequence_id(prefix: str, tick: int, scope: str, key: str, summary: str) -> str:
    # For mergeable consequences, use content-based ID, not tick-based
    if prefix in ("rumor", "pressure", "condition", "consequence"):
        raw = f"{prefix}|{scope}|{key}|{summary}"
    else:
        raw = f"{prefix}|{tick}|{scope}|{key}|{summary}"
    return prefix + "_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _normalize_world_rumor(record: Dict[str, Any]) -> Dict[str, Any]:
    record = _safe_dict(record)
    return {
        "rumor_id": _safe_str(record.get("rumor_id")),
        "summary": _safe_str(record.get("summary")),
        "scope": _safe_str(record.get("scope")) or "local",
        "location_id": _safe_str(record.get("location_id")),
        "source_actor_id": _safe_str(record.get("source_actor_id")),
        "source_kind": _safe_str(record.get("source_kind")),
        "started_tick": _safe_int(record.get("started_tick"), 0),
        "updated_tick": _safe_int(record.get("updated_tick"), 0),
        "strength": max(1, _safe_int(record.get("strength"), 1)),
        "tags": [str(x).strip() for x in _safe_list(record.get("tags")) if str(x).strip()],
    }


def _normalize_pressure_record(record: Dict[str, Any]) -> Dict[str, Any]:
    record = _safe_dict(record)
    return {
        "pressure_id": _safe_str(record.get("pressure_id")),
        "kind": _safe_str(record.get("kind")),
        "scope": _safe_str(record.get("scope")) or "local",
        "location_id": _safe_str(record.get("location_id")),
        "value": max(0, _safe_int(record.get("value"), 0)),
        "started_tick": _safe_int(record.get("started_tick"), 0),
        "updated_tick": _safe_int(record.get("updated_tick"), 0),
        "summary": _safe_str(record.get("summary")),
        "tags": [str(x).strip() for x in _safe_list(record.get("tags")) if str(x).strip()],
    }


def _normalize_location_condition(record: Dict[str, Any]) -> Dict[str, Any]:
    record = _safe_dict(record)
    return {
        "condition_id": _safe_str(record.get("condition_id")),
        "location_id": _safe_str(record.get("location_id")),
        "kind": _safe_str(record.get("kind")),
        "summary": _safe_str(record.get("summary")),
        "severity": max(1, _safe_int(record.get("severity"), 1)),
        "started_tick": _safe_int(record.get("started_tick"), 0),
        "updated_tick": _safe_int(record.get("updated_tick"), 0),
        "status": _safe_str(record.get("status")) or "active",
        "tags": [str(x).strip() for x in _safe_list(record.get("tags")) if str(x).strip()],
    }


def _normalize_world_consequence(record: Dict[str, Any]) -> Dict[str, Any]:
    record = _safe_dict(record)
    return {
        "consequence_id": _safe_str(record.get("consequence_id")),
        "kind": _safe_str(record.get("kind")),
        "scope": _safe_str(record.get("scope")) or "local",
        "location_id": _safe_str(record.get("location_id")),
        "summary": _safe_str(record.get("summary")),
        "source_actor_id": _safe_str(record.get("source_actor_id")),
        "source_activity_id": _safe_str(record.get("source_activity_id")),
        "tick": _safe_int(record.get("tick"), 0),
        "priority": max(1, _safe_int(record.get("priority"), 1)),
        "tags": [str(x).strip() for x in _safe_list(record.get("tags")) if str(x).strip()],
    }


def _normalize_consequence_text(text: str) -> str:
    text = _safe_str(text).lower()
    text = " ".join(text.split())
    text = text.rstrip(".,!?;:")
    return text


def _world_rumor_key(record: Dict[str, Any]) -> str:
    record = _normalize_world_rumor(record)
    return "|".join([
        _safe_str(record.get("scope")),
        _safe_str(record.get("location_id")),
        _normalize_consequence_text(_safe_str(record.get("summary"))),
        _safe_str(record.get("source_kind")),
    ])


def _world_pressure_key(record: Dict[str, Any]) -> str:
    record = _normalize_pressure_record(record)
    return "|".join([
        _safe_str(record.get("scope")),
        _safe_str(record.get("location_id")),
        _safe_str(record.get("kind")),
    ])


def _location_condition_key(record: Dict[str, Any]) -> str:
    record = _normalize_location_condition(record)
    return "|".join([
        _safe_str(record.get("location_id")),
        _safe_str(record.get("kind")),
    ])


def _world_consequence_key(record: Dict[str, Any]) -> str:
    record = _normalize_world_consequence(record)
    return "|".join([
        _safe_str(record.get("scope")),
        _safe_str(record.get("location_id")),
        _safe_str(record.get("kind")),
        _normalize_consequence_text(_safe_str(record.get("summary"))),
    ])


def ensure_world_consequence_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)

    rumors = [_normalize_world_rumor(x) for x in _safe_list(runtime_state.get("world_rumors"))]
    pressures = [_normalize_pressure_record(x) for x in _safe_list(runtime_state.get("world_pressure"))]
    conditions = [_normalize_location_condition(x) for x in _safe_list(runtime_state.get("location_conditions"))]
    consequences = [_normalize_world_consequence(x) for x in _safe_list(runtime_state.get("world_consequences"))]

    runtime_state["world_rumors"] = rumors[-_MAX_WORLD_RUMORS:]
    runtime_state["world_pressure"] = pressures[-_MAX_WORLD_PRESSURE:]
    runtime_state["location_conditions"] = conditions[-_MAX_LOCATION_CONDITIONS:]
    runtime_state["world_consequences"] = consequences[-_MAX_WORLD_CONSEQUENCES:]
    return runtime_state


# ── Active NPC activity state ────────────────────────────────────────────────

_MAX_ACTIVE_ACTIVITIES = 64


def _stable_activity_id(actor_id: str, tick: int, kind: str, location_id: str, target_id: str = "") -> str:
    actor_id = _safe_str(actor_id)
    kind = _safe_str(kind)
    location_id = _safe_str(location_id)
    target_id = _safe_str(target_id)
    raw = f"{actor_id}|{tick}|{kind}|{location_id}|{target_id}"
    return "activity_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _normalize_activity_record(record: Dict[str, Any]) -> Dict[str, Any]:
    record = _safe_dict(record)
    return {
        "activity_id": _safe_str(record.get("activity_id")),
        "kind": _safe_str(record.get("kind")),
        "summary": _safe_str(record.get("summary")),
        "location_id": _safe_str(record.get("location_id")),
        "target_id": _safe_str(record.get("target_id")),
        "target_label": _safe_str(record.get("target_label")),
        "started_tick": _safe_int(record.get("started_tick"), 0),
        "updated_tick": _safe_int(record.get("updated_tick"), 0),
        "expected_duration": max(1, _safe_int(record.get("expected_duration"), 1)),
        "status": _safe_str(record.get("status")) or "active",
        "intent": _safe_str(record.get("intent")),
        "world_tags": [str(x).strip() for x in _safe_list(record.get("world_tags")) if str(x).strip()],
    }


def ensure_actor_activity_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    actor_activities = _safe_dict(runtime_state.get("actor_activities"))
    normalized: Dict[str, Any] = {}
    for actor_id, rec in actor_activities.items():
        actor_id = _safe_str(actor_id)
        if not actor_id:
            continue
        normalized[actor_id] = _normalize_activity_record(rec)
    runtime_state["actor_activities"] = normalized
    return runtime_state


def get_actor_activity(runtime_state: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    runtime_state = ensure_actor_activity_state(runtime_state)
    return _safe_dict(_safe_dict(runtime_state.get("actor_activities")).get(_safe_str(actor_id)))


def set_actor_activity(runtime_state: Dict[str, Any], actor_id: str, activity: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = ensure_actor_activity_state(runtime_state)
    actor_id = _safe_str(actor_id)
    if not actor_id:
        return runtime_state
    actor_activities = _safe_dict(runtime_state.get("actor_activities"))
    actor_activities[actor_id] = _normalize_activity_record(activity)
    # bounded by actor count naturally, but normalize anyway
    runtime_state["actor_activities"] = dict(list(actor_activities.items())[-_MAX_ACTIVE_ACTIVITIES:])
    return runtime_state


# ── Living world activity planner ────────────────────────────────────────────

_LOCAL_ACTIVITY_KINDS = (
    "patrol",
    "watch_crowd",
    "trade",
    "gossip",
    "serve",
    "clean",
    "rest",
    "question_patron",
)

_GLOBAL_ACTIVITY_KINDS = (
    "move_goods",
    "spread_rumor",
    "scout_route",
    "increase_patrols",
    "organize_watch",
)

def _sorted_npc_entities(simulation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    simulation_state = _safe_dict(simulation_state)
    out: List[Dict[str, Any]] = []

    npc_index = _safe_dict(simulation_state.get("npc_index"))
    for npc_id, npc in npc_index.items():
        npc = _safe_dict(npc)
        rec = dict(npc)
        if not _safe_str(rec.get("id")):
            rec["id"] = _safe_str(npc_id)
        out.append(rec)

    if not out:
        for npc in _safe_list(simulation_state.get("npcs")):
            npc = _safe_dict(npc)
            if _safe_str(npc.get("id")):
                out.append(npc)

    out.sort(key=lambda x: (_safe_str(x.get("location_id")), _safe_str(x.get("name")), _safe_str(x.get("id"))))
    return out


def _choose_activity_kind_for_actor(actor: Dict[str, Any], tick: int, runtime_state: Dict[str, Any] | None = None) -> str:
    actor = _safe_dict(actor)
    runtime_state = ensure_world_consequence_state(_safe_dict(runtime_state))
    actor_id = _safe_str(actor.get("id"))
    name = _safe_str(actor.get("name"))
    location_id = _safe_str(actor.get("location_id")) or _safe_str(actor.get("current_location_id"))

    # Feedback bias from local conditions / pressure / rumors
    local_pressure = 0
    for p in _safe_list(runtime_state.get("world_pressure")):
        p = _normalize_pressure_record(p)
        if _safe_str(p.get("location_id")) == location_id and _safe_str(p.get("kind")) == "security_presence":
            local_pressure += _safe_int(p.get("value"), 0)

    local_rumors = 0
    for r in _safe_list(runtime_state.get("world_rumors")):
        r = _normalize_world_rumor(r)
        if _safe_str(r.get("location_id")) == location_id:
            local_rumors += _safe_int(r.get("strength"), 0)

    if local_pressure >= 3:
        # High pressure: bias heavily toward security activities
        options = ("patrol", "watch_crowd", "question_patron", "patrol", "watch_crowd", "serve", "clean")
    elif local_pressure >= 2:
        # Medium pressure: bias toward security but allow variety
        options = ("patrol", "watch_crowd", "trade", "serve", "clean", "gossip", "question_patron")
    elif local_rumors >= 3:
        # High rumors: bias toward social activities
        options = ("gossip", "gossip", "trade", "serve", "watch_crowd")
    elif local_rumors >= 2:
        # Medium rumors: bias toward social but allow variety
        options = ("gossip", "trade", "serve", "watch_crowd", "clean", "patrol")
    else:
        options = _LOCAL_ACTIVITY_KINDS

    seed = f"{actor_id}|{name}|{tick}|{location_id}|{local_pressure}|{local_rumors}"
    idx = int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8], 16) % len(options)
    return options[idx]


def _build_activity_summary(actor: Dict[str, Any], kind: str) -> str:
    actor = _safe_dict(actor)
    actor_name = _safe_str(actor.get("name")) or _safe_str(actor.get("id")) or "Someone"
    if kind == "patrol":
        return f"{actor_name} patrols nearby, watching for trouble."
    if kind == "watch_crowd":
        return f"{actor_name} keeps a close eye on the crowd."
    if kind == "trade":
        return f"{actor_name} haggles over goods and prices."
    if kind == "gossip":
        return f"{actor_name} trades rumors with the locals."
    if kind == "serve":
        return f"{actor_name} serves people and keeps things moving."
    if kind == "clean":
        return f"{actor_name} tidies up and keeps the place in order."
    if kind == "rest":
        return f"{actor_name} takes a quiet moment to rest and observe."
    if kind == "question_patron":
        return f"{actor_name} questions someone about suspicious behavior."
    return f"{actor_name} is busy with local matters."


def _build_activity_intent(kind: str) -> str:
    if kind in ("patrol", "watch_crowd", "question_patron"):
        return "Maintain order and watch for trouble."
    if kind == "trade":
        return "Make a profitable exchange."
    if kind == "gossip":
        return "Learn and spread useful rumors."
    if kind == "serve":
        return "Keep customers attended to."
    if kind == "clean":
        return "Keep the area in good condition."
    if kind == "rest":
        return "Recover while staying aware."
    return "Pursue current routine."


def _build_activity_tags(kind: str) -> List[str]:
    if kind in ("patrol", "watch_crowd", "question_patron"):
        return ["security", "local"]
    if kind == "trade":
        return ["commerce", "local"]
    if kind == "gossip":
        return ["rumor", "social", "local"]
    if kind == "serve":
        return ["service", "local"]
    if kind == "clean":
        return ["maintenance", "local"]
    if kind == "rest":
        return ["idle", "local"]
    return ["local"]


def advance_actor_activities_for_tick(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = ensure_actor_activity_state(runtime_state)
    tick = _safe_int(simulation_state.get("tick"), 0)
    npcs = _sorted_npc_entities(simulation_state)
    if not npcs:
        return runtime_state

    # bounded deterministic rotation
    start = tick % len(npcs)
    selected = []
    for offset in range(min(3, len(npcs))):
        selected.append(npcs[(start + offset) % len(npcs)])

    for actor in selected:
        actor_id = _safe_str(actor.get("id"))
        if not actor_id:
            continue
        current = get_actor_activity(runtime_state, actor_id)
        location_id = _safe_str(actor.get("location_id")) or _safe_str(actor.get("current_location_id"))
        if current and _safe_str(current.get("status")) == "active":
            age = tick - _safe_int(current.get("started_tick"), tick)
            duration = _safe_int(current.get("expected_duration"), 1)
            if age < duration:
                current["updated_tick"] = tick
                runtime_state = set_actor_activity(runtime_state, actor_id, current)
                continue

        kind = _choose_activity_kind_for_actor(actor, tick, runtime_state)
        activity = {
            "activity_id": _stable_activity_id(actor_id, tick, kind, location_id),
            "kind": kind,
            "summary": _build_activity_summary(actor, kind),
            "location_id": location_id,
            "target_id": "",
            "target_label": "",
            "started_tick": tick,
            "updated_tick": tick,
            "expected_duration": 2 + (tick % 3),
            "status": "active",
            "intent": _build_activity_intent(kind),
            "world_tags": _build_activity_tags(kind),
        }
        runtime_state = set_actor_activity(runtime_state, actor_id, activity)

    return runtime_state


# ── Activity beats ──────────────────────────────────────────────────────────

_MAX_ACTIVITY_SCENE_BEATS = 64
_MAX_GLOBAL_WORLD_BEATS = 64


def _stable_world_beat_id(prefix: str, actor_id: str, tick: int, summary: str) -> str:
    raw = f"{prefix}|{actor_id}|{tick}|{summary}"
    return prefix + "_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def emit_activity_beats_for_tick(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = ensure_actor_activity_state(runtime_state)
    tick = _safe_int(simulation_state.get("tick"), 0)

    recent_scene_beats = _safe_list(runtime_state.get("recent_scene_beats"))
    recent_world_event_rows = _safe_list(runtime_state.get("recent_world_event_rows"))
    global_world_beats = _safe_list(runtime_state.get("global_world_beats"))

    actor_activities = _safe_dict(runtime_state.get("actor_activities"))
    for actor_id, activity in sorted(actor_activities.items()):
        activity = _normalize_activity_record(activity)
        if _safe_str(activity.get("status")) != "active":
            continue
        if _safe_int(activity.get("updated_tick"), 0) != tick:
            continue

        summary = _safe_str(activity.get("summary"))
        location_id = _safe_str(activity.get("location_id"))
        tags = _safe_list(activity.get("world_tags"))
        beat_id = _stable_world_beat_id("activity_beat", actor_id, tick, summary)

        scene_beat = {
            "beat_id": beat_id,
            "tick": tick,
            "kind": "activity_beat",
            "summary": summary,
            "location_id": location_id,
            "actor_id": actor_id,
            "priority": 40,
            "tags": tags,
        }
        recent_scene_beats.append(scene_beat)

        recent_world_event_rows.append({
            "event_id": beat_id,
            "scope": "local",
            "kind": "activity_beat",
            "title": "Local Activity",
            "summary": summary,
            "tick": tick,
            "actors": [actor_id],
            "actor_id": actor_id,
            "location_id": location_id,
            "priority": 0.7,
            "status": "active",
            "source": "activity_runtime",
        })

        # Some activity kinds also create broader world beats
        kind = _safe_str(activity.get("kind"))
        if kind in ("gossip", "trade", "question_patron", "patrol"):
            global_summary = ""
            if kind == "gossip":
                global_summary = "Rumors circulate more quickly through local taverns."
            elif kind == "trade":
                global_summary = "Trade activity shifts prices and availability in the area."
            elif kind == "question_patron":
                global_summary = "The local watch grows more alert after suspicious behavior."
            elif kind == "patrol":
                global_summary = "Watch presence remains noticeable in nearby streets."

            if global_summary:
                global_id = _stable_world_beat_id("global_beat", actor_id, tick, global_summary)
                global_world_beats.append({
                    "event_id": global_id,
                    "scope": "global",
                    "kind": "world_event",
                    "title": "World Event",
                    "summary": global_summary,
                    "tick": tick,
                    "actors": [actor_id],
                    "actor_id": actor_id,
                    "location_id": "",
                    "priority": 0.6,
                    "status": "active",
                    "source": "activity_runtime",
                })

    runtime_state["recent_scene_beats"] = recent_scene_beats[-_MAX_ACTIVITY_SCENE_BEATS:]
    runtime_state["recent_world_event_rows"] = recent_world_event_rows[-_MAX_RECENT_WORLD_EVENT_ROWS:]
    runtime_state["global_world_beats"] = global_world_beats[-_MAX_GLOBAL_WORLD_BEATS:]
    return runtime_state


# ── Consequence propagation ──────────────────────────────────────────────────

def _append_world_rumor(runtime_state: Dict[str, Any], rumor: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = ensure_world_consequence_state(runtime_state)
    rumor = _normalize_world_rumor(rumor)
    rumor_key = _world_rumor_key(rumor)

    rumors = _safe_list(runtime_state.get("world_rumors"))
    updated = False
    merged: List[Dict[str, Any]] = []

    for existing in rumors:
        existing = _normalize_world_rumor(existing)
        if _world_rumor_key(existing) == rumor_key:
            existing["updated_tick"] = max(_safe_int(existing.get("updated_tick"), 0), _safe_int(rumor.get("updated_tick"), 0))
            existing["strength"] = min(10, _safe_int(existing.get("strength"), 1) + max(1, _safe_int(rumor.get("strength"), 1)))
            existing_tags = set(_safe_list(existing.get("tags")))
            for tag in _safe_list(rumor.get("tags")):
                existing_tags.add(_safe_str(tag))
            existing["tags"] = sorted([t for t in existing_tags if t])
            merged.append(existing)
            updated = True
        else:
            merged.append(existing)

    if not updated:
        merged.append(rumor)

    runtime_state["world_rumors"] = merged[-_MAX_WORLD_RUMORS:]
    return runtime_state


def _append_world_pressure(runtime_state: Dict[str, Any], pressure: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = ensure_world_consequence_state(runtime_state)
    pressure = _normalize_pressure_record(pressure)
    pressure_key = _world_pressure_key(pressure)

    items = _safe_list(runtime_state.get("world_pressure"))
    updated = False
    merged: List[Dict[str, Any]] = []

    for existing in items:
        existing = _normalize_pressure_record(existing)
        if _world_pressure_key(existing) == pressure_key:
            existing["updated_tick"] = max(_safe_int(existing.get("updated_tick"), 0), _safe_int(pressure.get("updated_tick"), 0))
            existing["value"] = min(10, _safe_int(existing.get("value"), 0) + max(1, _safe_int(pressure.get("value"), 0)))
            existing["summary"] = _safe_str(pressure.get("summary")) or _safe_str(existing.get("summary"))
            existing_tags = set(_safe_list(existing.get("tags")))
            for tag in _safe_list(pressure.get("tags")):
                existing_tags.add(_safe_str(tag))
            existing["tags"] = sorted([t for t in existing_tags if t])
            merged.append(existing)
            updated = True
        else:
            merged.append(existing)

    if not updated:
        merged.append(pressure)

    runtime_state["world_pressure"] = merged[-_MAX_WORLD_PRESSURE:]
    return runtime_state


def _append_location_condition(runtime_state: Dict[str, Any], condition: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = ensure_world_consequence_state(runtime_state)
    condition = _normalize_location_condition(condition)
    condition_key = _location_condition_key(condition)

    items = _safe_list(runtime_state.get("location_conditions"))
    updated = False
    merged: List[Dict[str, Any]] = []

    for existing in items:
        existing = _normalize_location_condition(existing)
        if _location_condition_key(existing) == condition_key:
            existing["updated_tick"] = max(_safe_int(existing.get("updated_tick"), 0), _safe_int(condition.get("updated_tick"), 0))
            existing["severity"] = min(10, max(_safe_int(existing.get("severity"), 1), _safe_int(condition.get("severity"), 1)))
            existing["summary"] = _safe_str(condition.get("summary")) or _safe_str(existing.get("summary"))
            existing["status"] = _safe_str(condition.get("status")) or _safe_str(existing.get("status")) or "active"
            existing_tags = set(_safe_list(existing.get("tags")))
            for tag in _safe_list(condition.get("tags")):
                existing_tags.add(_safe_str(tag))
            existing["tags"] = sorted([t for t in existing_tags if t])
            merged.append(existing)
            updated = True
        else:
            merged.append(existing)

    if not updated:
        merged.append(condition)

    runtime_state["location_conditions"] = merged[-_MAX_LOCATION_CONDITIONS:]
    return runtime_state


def _append_world_consequence(runtime_state: Dict[str, Any], consequence: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = ensure_world_consequence_state(runtime_state)
    consequence = _normalize_world_consequence(consequence)
    consequence_key = _world_consequence_key(consequence)

    items = _safe_list(runtime_state.get("world_consequences"))
    updated = False
    merged: List[Dict[str, Any]] = []

    for existing in items:
        existing = _normalize_world_consequence(existing)
        if _world_consequence_key(existing) == consequence_key:
            existing["tick"] = max(_safe_int(existing.get("tick"), 0), _safe_int(consequence.get("tick"), 0))
            existing["priority"] = min(10, max(_safe_int(existing.get("priority"), 1), _safe_int(consequence.get("priority"), 1)))
            existing["summary"] = _safe_str(consequence.get("summary")) or _safe_str(existing.get("summary"))
            existing_tags = set(_safe_list(existing.get("tags")))
            for tag in _safe_list(consequence.get("tags")):
                existing_tags.add(_safe_str(tag))
            existing["tags"] = sorted([t for t in existing_tags if t])
            merged.append(existing)
            updated = True
        else:
            merged.append(existing)

    if not updated:
        merged.append(consequence)

    runtime_state["world_consequences"] = merged[-_MAX_WORLD_CONSEQUENCES:]
    return runtime_state


def _emit_consequence_world_rows(runtime_state: Dict[str, Any], consequence: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    rows = _safe_list(runtime_state.get("recent_world_event_rows"))
    consequence = _normalize_world_consequence(consequence)

    event_id = _safe_str(consequence.get("consequence_id"))
    replaced = False
    merged_rows: List[Dict[str, Any]] = []

    for row in rows:
        row = _safe_dict(row)
        if _safe_str(row.get("event_id")) == event_id:
            merged_rows.append({
                "event_id": event_id,
                "scope": _safe_str(consequence.get("scope")) or "local",
                "kind": _safe_str(consequence.get("kind")) or "world_consequence",
                "title": "World Consequence",
                "summary": _safe_str(consequence.get("summary")),
                "tick": _safe_int(consequence.get("tick"), 0),
                "actors": [_safe_str(consequence.get("source_actor_id"))] if _safe_str(consequence.get("source_actor_id")) else [],
                "actor_id": _safe_str(consequence.get("source_actor_id")),
                "location_id": _safe_str(consequence.get("location_id")),
                "priority": min(1.0, 0.4 + (0.1 * _safe_int(consequence.get("priority"), 1))),
                "status": "active",
                "source": "consequence_runtime",
            })
            replaced = True
        else:
            merged_rows.append(row)

    if not replaced:
        merged_rows.append({
            "event_id": event_id,
            "scope": _safe_str(consequence.get("scope")) or "local",
            "kind": _safe_str(consequence.get("kind")) or "world_consequence",
            "title": "World Consequence",
            "summary": _safe_str(consequence.get("summary")),
            "tick": _safe_int(consequence.get("tick"), 0),
            "actors": [_safe_str(consequence.get("source_actor_id"))] if _safe_str(consequence.get("source_actor_id")) else [],
            "actor_id": _safe_str(consequence.get("source_actor_id")),
            "location_id": _safe_str(consequence.get("location_id")),
            "priority": min(1.0, 0.4 + (0.1 * _safe_int(consequence.get("priority"), 1))),
            "status": "active",
            "source": "consequence_runtime",
        })

    runtime_state["recent_world_event_rows"] = merged_rows[-_MAX_RECENT_WORLD_EVENT_ROWS:]
    return runtime_state


def propagate_activity_consequences_for_tick(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = ensure_world_consequence_state(runtime_state)
    runtime_state = ensure_actor_activity_state(runtime_state)

    tick = _safe_int(simulation_state.get("tick"), 0)
    actor_activities = _safe_dict(runtime_state.get("actor_activities"))

    for actor_id, activity in sorted(actor_activities.items()):
        activity = _normalize_activity_record(activity)
        if _safe_str(activity.get("status")) != "active":
            continue
        if _safe_int(activity.get("updated_tick"), 0) != tick:
            continue

        kind = _safe_str(activity.get("kind"))
        location_id = _safe_str(activity.get("location_id"))
        summary = _safe_str(activity.get("summary"))
        activity_id = _safe_str(activity.get("activity_id"))

        # Gossip creates rumors
        if kind == "gossip":
            rumor_summary = f"Rumors spread that {summary[:1].lower() + summary[1:]}" if summary else "Rumors spread among the locals."
            rumor = {
                "rumor_id": _stable_consequence_id("rumor", tick, "local", location_id, rumor_summary),
                "summary": rumor_summary,
                "scope": "local",
                "location_id": location_id,
                "source_actor_id": actor_id,
                "source_kind": kind,
                "started_tick": tick,
                "updated_tick": tick,
                "strength": 1,
                "tags": ["rumor", "social"],
            }
            consequence = {
                "consequence_id": _stable_consequence_id("consequence", tick, "local", location_id, rumor_summary),
                "kind": "rumor",
                "scope": "local",
                "location_id": location_id,
                "summary": rumor_summary,
                "source_actor_id": actor_id,
                "source_activity_id": activity_id,
                "tick": tick,
                "priority": 2,
                "tags": ["rumor", "social"],
            }
            runtime_state = _append_world_rumor(runtime_state, rumor)
            runtime_state = _append_world_consequence(runtime_state, consequence)
            runtime_state = _emit_consequence_world_rows(runtime_state, consequence)

        # Patrol / questioning increases security pressure
        elif kind in ("patrol", "watch_crowd", "question_patron"):
            pressure_summary = "The local watch grows more visible and alert."
            pressure = {
                "pressure_id": _stable_consequence_id("pressure", tick, "local", location_id, pressure_summary),
                "kind": "security_presence",
                "scope": "local",
                "location_id": location_id,
                "value": 1,
                "started_tick": tick,
                "updated_tick": tick,
                "summary": pressure_summary,
                "tags": ["security", "watch"],
            }
            consequence = {
                "consequence_id": _stable_consequence_id("consequence", tick, "local", location_id, pressure_summary),
                "kind": "security_pressure",
                "scope": "local",
                "location_id": location_id,
                "summary": pressure_summary,
                "source_actor_id": actor_id,
                "source_activity_id": activity_id,
                "tick": tick,
                "priority": 2,
                "tags": ["security", "watch"],
            }
            runtime_state = _append_world_pressure(runtime_state, pressure)
            runtime_state = _append_world_consequence(runtime_state, consequence)
            runtime_state = _emit_consequence_world_rows(runtime_state, consequence)

        # Trade creates a global market consequence
        elif kind == "trade":
            consequence_summary = "Trade shifts local prices and availability."
            consequence = {
                "consequence_id": _stable_consequence_id("consequence", tick, "global", "trade", consequence_summary),
                "kind": "market_shift",
                "scope": "global",
                "location_id": "",
                "summary": consequence_summary,
                "source_actor_id": actor_id,
                "source_activity_id": activity_id,
                "tick": tick,
                "priority": 2,
                "tags": ["commerce", "market"],
            }
            runtime_state = _append_world_consequence(runtime_state, consequence)
            runtime_state = _emit_consequence_world_rows(runtime_state, consequence)

        # Cleaning / service can improve local condition
        elif kind in ("clean", "serve"):
            cond_summary = "The area feels more orderly and well-kept."
            condition = {
                "condition_id": _stable_consequence_id("condition", tick, "local", location_id, cond_summary),
                "location_id": location_id,
                "kind": "orderly",
                "summary": cond_summary,
                "severity": 1,
                "started_tick": tick,
                "updated_tick": tick,
                "status": "active",
                "tags": ["order", "service"],
            }
            consequence = {
                "consequence_id": _stable_consequence_id("consequence", tick, "local", location_id, cond_summary),
                "kind": "location_condition",
                "scope": "local",
                "location_id": location_id,
                "summary": cond_summary,
                "source_actor_id": actor_id,
                "source_activity_id": activity_id,
                "tick": tick,
                "priority": 1,
                "tags": ["order", "service"],
            }
            runtime_state = _append_location_condition(runtime_state, condition)
            runtime_state = _append_world_consequence(runtime_state, consequence)
            runtime_state = _emit_consequence_world_rows(runtime_state, consequence)

    return runtime_state


def decay_world_consequences_for_tick(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = ensure_world_consequence_state(runtime_state)
    tick = _safe_int(simulation_state.get("tick"), 0)

    # Rumors decay by strength, then disappear
    rumors_out: List[Dict[str, Any]] = []
    for rumor in _safe_list(runtime_state.get("world_rumors")):
        rumor = _normalize_world_rumor(rumor)
        age = tick - _safe_int(rumor.get("updated_tick"), 0)
        strength = _safe_int(rumor.get("strength"), 1)
        if age >= _WORLD_RUMOR_DECAY_TICKS:
            strength -= 1
        if strength > 0:
            rumor["strength"] = strength
            rumors_out.append(rumor)
    runtime_state["world_rumors"] = rumors_out[-_MAX_WORLD_RUMORS:]

    # Pressure decays by value, then disappears
    pressure_out: List[Dict[str, Any]] = []
    for pressure in _safe_list(runtime_state.get("world_pressure")):
        pressure = _normalize_pressure_record(pressure)
        age = tick - _safe_int(pressure.get("updated_tick"), 0)
        value = _safe_int(pressure.get("value"), 0)
        if age >= _WORLD_PRESSURE_DECAY_TICKS:
            value -= 1
        if value > 0:
            pressure["value"] = value
            pressure_out.append(pressure)
    runtime_state["world_pressure"] = pressure_out[-_MAX_WORLD_PRESSURE:]

    # Location conditions cool and eventually resolve
    condition_out: List[Dict[str, Any]] = []
    for condition in _safe_list(runtime_state.get("location_conditions")):
        condition = _normalize_location_condition(condition)
        age = tick - _safe_int(condition.get("updated_tick"), 0)
        severity = _safe_int(condition.get("severity"), 1)
        if age >= _LOCATION_CONDITION_DECAY_TICKS:
            severity -= 1
        if severity > 0:
            condition["severity"] = severity
            condition_out.append(condition)
    runtime_state["location_conditions"] = condition_out[-_MAX_LOCATION_CONDITIONS:]

    # Consequences fade out of active memory if stale
    consequence_out: List[Dict[str, Any]] = []
    for consequence in _safe_list(runtime_state.get("world_consequences")):
        consequence = _normalize_world_consequence(consequence)
        age = tick - _safe_int(consequence.get("tick"), 0)
        if age < _WORLD_CONSEQUENCE_DECAY_TICKS:
            consequence_out.append(consequence)
    runtime_state["world_consequences"] = consequence_out[-_MAX_WORLD_CONSEQUENCES:]

    return runtime_state


def emit_scene_beat(
    runtime_state: Dict[str, Any],
    *,
    tick: int,
    summary: str,
    kind: str = "scene_beat",
    priority: int = 50,
    scene_id: str = "",
    interaction_id: str = "",
    actors: List[str] | None = None,
    location_id: str = "",
    recap_level: str = "notable",
    tags: List[str] | None = None,
) -> Dict[str, Any]:
    runtime_state = _ensure_recent_scene_beats(runtime_state)
    beat = _normalize_scene_beat(
        {
            "tick": tick,
            "kind": kind,
            "summary": summary,
            "priority": priority,
            "scene_id": scene_id,
            "interaction_id": interaction_id,
            "actors": actors or [],
            "location_id": location_id,
            "recap_level": recap_level,
            "tags": tags or [],
        }
    )
    if not beat["summary"]:
        return runtime_state
    if beat["recap_level"] not in ("notable", "major"):
        return runtime_state
    beats = _safe_list(runtime_state.get("recent_scene_beats"))
    beats.append(beat)
    runtime_state["recent_scene_beats"] = beats
    return _ensure_recent_scene_beats(runtime_state)


def _stable_state_change_event_id(event: Dict[str, Any]) -> str:
    payload = {
        "tick": int(_safe_dict(event).get("tick", 0) or 0),
        "actor_id": _safe_str(_safe_dict(event).get("actor_id")),
        "semantic_action": _safe_str(_safe_dict(event).get("semantic_action")),
        "summary": _safe_str(_safe_dict(event).get("summary")),
        "location_id": _safe_str(_safe_dict(event).get("location_id")),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return "state_change_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _normalize_semantic_state_change_proposal(proposal: Dict[str, Any]) -> Dict[str, Any]:
    proposal = _safe_dict(proposal)
    delta = _safe_dict(proposal.get("delta"))
    out = {
        "proposal_id": _safe_str(proposal.get("proposal_id") or proposal.get("id")),
        "actor_id": _safe_str(proposal.get("actor_id")),
        "proposal_kind": _safe_str(proposal.get("proposal_kind")) or "state_delta",
        "semantic_action": _safe_str(proposal.get("semantic_action")),
        "target_id": _safe_str(proposal.get("target_id")),
        "target_location_id": _safe_str(proposal.get("target_location_id")),
        "summary": _safe_str(proposal.get("summary")),
        "beat_summary": _safe_str(proposal.get("beat_summary")),
        "priority": int(proposal.get("priority", 50) or 50),
        "delta": {
            "activity": _safe_str(delta.get("activity")),
            "availability": _safe_str(delta.get("availability")),
            "location_id": _safe_str(delta.get("location_id")),
            "mood": _safe_str(delta.get("mood")),
            "intent": _safe_str(delta.get("intent")),
            "engagement": _safe_str(delta.get("engagement")),
        },
        "tags": [_safe_str(x) for x in _safe_list(proposal.get("tags")) if _safe_str(x)],
        "source": _safe_str(proposal.get("source")) or "llm",
    }
    if not out["proposal_id"]:
        raw = json.dumps(
            {
                "actor_id": out["actor_id"],
                "semantic_action": out["semantic_action"],
                "delta": out["delta"],
                "summary": out["summary"],
                "target_location_id": out["target_location_id"],
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        out["proposal_id"] = "proposal_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return out


def _stable_semantic_state_change_proposal_id(
    proposal: Dict[str, Any],
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> str:
    """
    Build a deterministic per-tick proposal identity.

    IMPORTANT:
    - proposal_id must NOT be a constant like "llm_<actor_id>"
    - otherwise applied_proposal_ids suppress all future proposals for that actor
    - identity must vary across ticks / payload changes but remain deterministic
    """
    proposal = _normalize_semantic_state_change_proposal(proposal)
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    tick = int(
        simulation_state.get("current_tick", 0)
        or simulation_state.get("tick", 0)
        or runtime_state.get("tick", 0)
        or 0
    )
    payload = {
        "tick": tick,
        "actor_id": _safe_str(proposal.get("actor_id")),
        "semantic_action": _safe_str(proposal.get("semantic_action")),
        "summary": _safe_str(proposal.get("summary")),
        "beat_summary": _safe_str(proposal.get("beat_summary")),
        "target_id": _safe_str(proposal.get("target_id")),
        "target_location_id": _safe_str(proposal.get("target_location_id")),
        "delta": _safe_dict(proposal.get("delta")),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return "semantic_proposal_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _ensure_semantic_pipeline_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = ensure_ambient_runtime_state(_safe_dict(runtime_state))
    runtime_state = ensure_actor_activity_state(runtime_state)
    runtime_state = ensure_world_consequence_state(runtime_state)
    runtime_state.setdefault("semantic_state_change_proposals", [])
    runtime_state.setdefault("accepted_state_change_events", [])
    runtime_state.setdefault("rejected_state_change_events", [])
    runtime_state.setdefault("applied_semantic_proposal_ids", [])
    runtime_state.setdefault("last_semantic_llm_tick", -999999)
    runtime_state.setdefault("recorded_semantic_llm_proposals", [])
    runtime_state.setdefault("recorded_semantic_llm_prompt", "")
    runtime_state.setdefault("recorded_semantic_llm_raw_output", "")
    runtime_state.setdefault("recorded_semantic_llm_capture_tick", -999999)
    runtime_state["semantic_state_change_proposals"] = _safe_list(
        runtime_state.get("semantic_state_change_proposals")
    )[-_MAX_SEMANTIC_PROPOSALS:]
    runtime_state["accepted_state_change_events"] = _safe_list(
        runtime_state.get("accepted_state_change_events")
    )[-_MAX_ACCEPTED_STATE_CHANGE_EVENTS:]
    runtime_state["rejected_state_change_events"] = _safe_list(
        runtime_state.get("rejected_state_change_events")
    )[-_MAX_ACCEPTED_STATE_CHANGE_EVENTS:]
    runtime_state["applied_semantic_proposal_ids"] = [
        _safe_str(x) for x in _safe_list(runtime_state.get("applied_semantic_proposal_ids")) if _safe_str(x)
    ][-_MAX_APPLIED_PROPOSAL_IDS:]
    runtime_state["recorded_semantic_llm_proposals"] = [
        _normalize_semantic_state_change_proposal(x)
        for x in _safe_list(runtime_state.get("recorded_semantic_llm_proposals"))
        if _safe_dict(x)
    ][-_MAX_RECORDED_SEMANTIC_LLM_PROPOSALS:]
    runtime_state["recorded_semantic_llm_prompt"] = _safe_str(runtime_state.get("recorded_semantic_llm_prompt"))
    runtime_state["recorded_semantic_llm_raw_output"] = _safe_str(runtime_state.get("recorded_semantic_llm_raw_output"))
    runtime_state["recorded_semantic_llm_capture_tick"] = _safe_int(runtime_state.get("recorded_semantic_llm_capture_tick", -999999), -999999)
    runtime_state["last_semantic_llm_tick"] = _safe_int(runtime_state.get("last_semantic_llm_tick", -999999), -999999)
    return runtime_state


def _accepted_state_change_event_ids(runtime_state: Dict[str, Any]) -> set[str]:
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    ids = set()
    for item in _safe_list(runtime_state.get("accepted_state_change_events")):
        event_id = _safe_str(_safe_dict(item).get("event_id"))
        if event_id:
            ids.add(event_id)
    return ids


def _applied_semantic_proposal_ids(runtime_state: Dict[str, Any]) -> set[str]:
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    ids = set()
    for item in _safe_list(runtime_state.get("applied_semantic_proposal_ids")):
        proposal_id = _safe_str(item)
        if proposal_id:
            ids.add(proposal_id)
    return ids


def _safe_actor_states(simulation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    simulation_state = _safe_dict(simulation_state)
    npc_index = _safe_dict(simulation_state.get("npc_index"))
    if npc_index:
        derived: List[Dict[str, Any]] = []
        for npc_id, npc in npc_index.items():
            npc = _safe_dict(npc)
            actor_id = _safe_str(npc_id)
            if not actor_id:
                continue
            derived.append(
                {
                    "id": actor_id,
                    "name": _safe_str(npc.get("name")) or actor_id,
                    "location_id": _safe_str(npc.get("location_id")),
                    "activity": _safe_str(npc.get("activity")),
                    "availability": _safe_str(npc.get("availability")),
                    "mood": _safe_str(npc.get("mood")),
                    "intent": _safe_str(npc.get("intent")),
                    "engagement": _safe_str(npc.get("engagement")),
                }
            )
        return derived
    actor_states = _safe_list(simulation_state.get("actor_states"))
    if actor_states:
        return [_safe_dict(x) for x in actor_states if _safe_dict(x)]
    npc_states = _safe_list(simulation_state.get("npc_states"))
    return [_safe_dict(x) for x in npc_states if _safe_dict(x)]


def _write_actor_states(simulation_state: Dict[str, Any], actor_states: List[Dict[str, Any]]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    actor_states = [ _safe_dict(x) for x in _safe_list(actor_states) ]
    simulation_state["actor_states"] = actor_states

    # Preserve backward compatibility for npc_states only when that projection
    # already exists. Do not blindly force every actor state into npc_states.
    if "npc_states" in simulation_state:
        npc_ids = {
            _safe_str(_safe_dict(x).get("id"))
            for x in _safe_list(simulation_state.get("npc_states"))
            if _safe_str(_safe_dict(x).get("id"))
        }
        simulation_state["npc_states"] = [
            _safe_dict(x) for x in actor_states if _safe_str(_safe_dict(x).get("id")) in npc_ids
        ]
    return simulation_state


def _find_actor_state(actor_states: List[Dict[str, Any]], actor_id: str) -> Dict[str, Any]:
    actor_id = _safe_str(actor_id)
    for actor in _safe_list(actor_states):
        actor = _safe_dict(actor)
        if _safe_str(actor.get("id")) == actor_id:
            return actor
    return {}


def _normalize_actor_state_for_delta(actor: Dict[str, Any]) -> Dict[str, Any]:
    actor = _safe_dict(actor)
    return {
        "id": _safe_str(actor.get("id")),
        "name": _safe_str(actor.get("name")),
        "activity": _safe_str(actor.get("activity")),
        "availability": _safe_str(actor.get("availability")),
        "location_id": _safe_str(actor.get("location_id")),
        "mood": _safe_str(actor.get("mood")),
        "intent": _safe_str(actor.get("intent")),
        "engagement": _safe_str(actor.get("engagement")),
    }


def _allowed_semantic_actions() -> Dict[str, Dict[str, str]]:
    return {
        "take_break": {"activity": "on_break", "availability": "temporarily_unavailable"},
        "wash_up": {"activity": "washing_up", "availability": "occupied"},
        "rest": {"activity": "resting", "availability": "temporarily_unavailable"},
        "investigate": {"activity": "investigating"},
        "argue": {"activity": "arguing", "engagement": "active"},
        "leave_scene": {"activity": "departing", "availability": "unavailable"},
        "return_to_scene": {"activity": "present", "availability": "available"},
    }


def record_semantic_llm_capture(
    runtime_state: Dict[str, Any],
    simulation_state: Dict[str, Any],
    *,
    prompt: str,
    raw_output: Any,
    proposals: List[Dict[str, Any]],
    tick: int,
) -> Dict[str, Any]:
    print("SEMANTIC RECORD prompt_present =", bool(prompt))
    print("SEMANTIC RECORD raw_output_present =", bool(_normalize_llm_text_output(raw_output)))
    print("SEMANTIC RECORD proposal_count =", len(proposals))
    print("SEMANTIC RECORD proposals =", proposals[:3])
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    normalized = [
        _normalize_semantic_state_change_proposal(x)
        for x in _safe_list(proposals)
        if _safe_dict(x)
    ][-_MAX_RECORDED_SEMANTIC_LLM_PROPOSALS:]

    # Hard filter: only allow actors in active interactions if any exist
    interactions = _normalize_active_interactions(simulation_state, runtime_state)
    if interactions:
        allowed_actor_ids = set()
        for i in interactions:
            for p in i.get("participants") or []:
                allowed_actor_ids.add(_safe_str(p))
        if allowed_actor_ids:
            normalized = [p for p in normalized if p.get("actor_id") in allowed_actor_ids]

    # Fallback: if no proposals, keep one actor active to prevent dead world
    if not normalized:
        actor_states = _safe_actor_states(simulation_state)
        if actor_states:
            actor = actor_states[0]
            normalized = [{
                "actor_id": actor.get("id"),
                "proposal_kind": "state_delta",
                "semantic_action": "continue_activity",
                "delta": {
                    "activity": _safe_str(actor.get("activity")) or "active",
                    "engagement": "ongoing"
                },
                "beat_summary": f"{_safe_str(actor.get('name'))} continues their current activity."
            }]

    runtime_state["recorded_semantic_llm_prompt"] = _safe_str(prompt)
    runtime_state["recorded_semantic_llm_raw_output"] = _normalize_llm_text_output(raw_output)
    runtime_state["recorded_semantic_llm_proposals"] = normalized[:_MAX_RECORDED_SEMANTIC_LLM_PROPOSALS]
    runtime_state["recorded_semantic_llm_capture_tick"] = int(tick or 0)
    return runtime_state


def clear_recorded_semantic_llm_capture(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    runtime_state["recorded_semantic_llm_proposals"] = []
    return runtime_state


def _build_location_id_index(simulation_state: Dict[str, Any]) -> set[str]:
    simulation_state = _safe_dict(simulation_state)
    ids = {
        _safe_str(x.get("id"))
        for x in _safe_list(simulation_state.get("locations"))
        if isinstance(x, dict) and _safe_str(x.get("id"))
    }
    scene_location = _safe_str(simulation_state.get("location_id"))
    if scene_location:
        ids.add(scene_location)
    return ids


def _canonical_delta_has_values(delta: Dict[str, Any]) -> bool:
    delta = _safe_dict(delta)
    return any(
        _safe_str(delta.get(key))
        for key in ("activity", "availability", "location_id", "mood", "intent", "engagement")
    )


def enqueue_semantic_state_change_proposal(runtime_state: Dict[str, Any], proposal: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    proposal = _normalize_semantic_state_change_proposal(proposal)
    items = _safe_list(runtime_state.get("semantic_state_change_proposals"))
    # Do not allow empty / constant IDs to poison proposal replay suppression.
    # Proposal IDs should already be stamped upstream with a deterministic
    # per-tick identity, but preserve any explicit ID here.
    proposal_id = _safe_str(proposal.get("proposal_id"))
    if not proposal_id:
        proposal = dict(proposal)
        proposal["proposal_id"] = "semantic_proposal_" + hashlib.sha1(
            json.dumps(proposal, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:12]
    items.append(proposal)
    runtime_state["semantic_state_change_proposals"] = items[-_MAX_SEMANTIC_PROPOSALS:]
    return runtime_state


def validate_semantic_state_change_proposal(
    proposal: Dict[str, Any],
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> Dict[str, Any]:
    proposal = _normalize_semantic_state_change_proposal(proposal)
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)

    errors: List[str] = []
    if proposal["proposal_kind"] != "state_delta":
        errors.append("unsupported_proposal_kind")
    if not proposal["actor_id"]:
        errors.append("missing_actor_id")

    actor_states = _safe_actor_states(simulation_state)
    actor = _find_actor_state(actor_states, proposal["actor_id"])
    if not actor:
        known_ids = [str(_safe_dict(x).get("id") or "").strip() for x in actor_states if _safe_dict(x)]
        print("SEMANTIC VALIDATOR known_actor_ids =", known_ids[:20])
        print("SEMANTIC VALIDATOR incoming_actor_id =", proposal.get("actor_id"))
        print("SEMANTIC VALIDATOR npc_index_keys =", list(_safe_dict(simulation_state.get("npc_index")).keys())[:20])
        errors.append("unknown_actor")

    delta = _safe_dict(proposal.get("delta"))
    semantic_action = _safe_str(proposal.get("semantic_action"))
    known_actions = _allowed_semantic_actions()
    if semantic_action and semantic_action not in known_actions:
        # Open-ended actions are allowed only if they already compile to a canonical bounded delta.
        if not any(_safe_str(delta.get(k)) for k in ("activity", "availability", "location_id", "mood", "intent", "engagement")):
            errors.append("uncompilable_semantic_action")

    if proposal["target_location_id"]:
        valid_location_ids = _build_location_id_index(simulation_state)
        if not valid_location_ids:
            actor_location = _safe_str(actor.get("location_id"))
            if not actor_location:
                errors.append("unvalidated_target_location")
        elif proposal["target_location_id"] not in valid_location_ids:
            errors.append("invalid_target_location")

    if not semantic_action and not _canonical_delta_has_values(delta):
        errors.append("empty_state_delta")

    active_interactions = _normalize_active_interactions(simulation_state, runtime_state)
    for interaction in active_interactions:
        participants = [_safe_str(x) for x in _safe_list(interaction.get("participants")) if _safe_str(x)]
        if proposal["actor_id"] in participants and not bool(interaction.get("resolved")):
            if semantic_action in ("take_break", "wash_up", "leave_scene"):
                errors.append("actor_locked_in_active_interaction")
                break

    return {
        "ok": not errors,
        "errors": errors,
        "proposal": proposal,
        "actor_before": _normalize_actor_state_for_delta(actor),
    }


def compile_semantic_state_change_to_canonical_delta(
    proposal: Dict[str, Any],
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> Dict[str, Any]:
    proposal = _normalize_semantic_state_change_proposal(proposal)
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)

    actor_states = _safe_actor_states(simulation_state)
    actor = _find_actor_state(actor_states, proposal["actor_id"])
    if not actor:
        raise ValueError(f"compile_missing_actor:{_safe_str(proposal.get('actor_id'))}")
    actor_before = _normalize_actor_state_for_delta(actor)
    delta = dict(_safe_dict(proposal.get("delta")))

    semantic_action = _safe_str(proposal.get("semantic_action"))
    implied = dict(_allowed_semantic_actions().get(semantic_action, {}))
    for key, value in implied.items():
        if not _safe_str(delta.get(key)):
            delta[key] = value

    if proposal["target_location_id"] and not _safe_str(delta.get("location_id")):
        delta["location_id"] = proposal["target_location_id"]

    actor_after = dict(actor_before)
    for key in ("activity", "availability", "location_id", "mood", "intent", "engagement"):
        value = _safe_str(delta.get(key))
        if value:
            actor_after[key] = value
    if actor_after == actor_before:
        raise ValueError(f"empty_compiled_delta:{_safe_str(proposal.get('proposal_id'))}")

    beat_summary = _safe_str(proposal.get("beat_summary"))
    if not beat_summary:
        actor_name = _safe_str(actor_after.get("name")) or _safe_str(actor_before.get("name")) or "Someone"
        if semantic_action == "take_break":
            beat_summary = f"{actor_name} steps away for a short break."
        elif semantic_action == "wash_up":
            beat_summary = f"{actor_name} slips away to wash up."
        elif semantic_action == "rest":
            beat_summary = f"{actor_name} settles in to rest."
        elif semantic_action == "investigate":
            beat_summary = f"{actor_name} begins investigating the situation."
        elif semantic_action == "leave_scene":
            beat_summary = f"{actor_name} leaves the area."
        elif semantic_action == "return_to_scene":
            beat_summary = f"{actor_name} returns to the scene."
        elif semantic_action == "argue":
            beat_summary = f"{actor_name} becomes engaged in a heated exchange."
        elif _safe_str(actor_after.get("activity")) and _safe_str(actor_after.get("activity")) != _safe_str(actor_before.get("activity")):
            beat_summary = f"{actor_name} shifts into {_safe_str(actor_after.get('activity')).replace('_', ' ')}."
        else:
            beat_summary = _safe_str(proposal.get("summary"))

    current_tick = _safe_int(
        simulation_state.get("current_tick")
        or simulation_state.get("tick")
        or runtime_state.get("tick"),
        0,
    )

    canonical_event = {
        "event_id": "",
        "tick": current_tick,
        "proposal_id": _safe_str(proposal.get("proposal_id")),
        "actor_id": _safe_str(proposal.get("actor_id")),
        "semantic_action": semantic_action,
        "location_id": _safe_str(actor_after.get("location_id")),
        "summary": _safe_str(proposal.get("summary")) or beat_summary,
        "before": actor_before,
        "after": actor_after,
        "beat": {
            "summary": beat_summary,
            "priority": int(proposal.get("priority", 50) or 50),
            "recap_level": "notable",
            "tags": ["state_change", semantic_action or "semantic_action"],
        },
    }
    canonical_event["event_id"] = _stable_state_change_event_id(canonical_event)
    assert canonical_event["tick"] == _safe_int(simulation_state.get("tick"), 0)

    print(
        "DEBUG SEMANTIC EVENT CREATED =",
        {
            "event_id": canonical_event.get("event_id"),
            "tick": canonical_event.get("tick"),
            "proposal_id": canonical_event.get("proposal_id"),
            "actor_id": canonical_event.get("actor_id"),
            "summary": canonical_event.get("summary"),
            "location_id": canonical_event.get("location_id"),
        },
    )

    return canonical_event


def _apply_canonical_state_change_event(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    event: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    event = _safe_dict(event)

    actor_states = _safe_actor_states(simulation_state)
    actor_id = _safe_str(event.get("actor_id"))
    after = _safe_dict(event.get("after"))

    updated = []
    found = False
    for actor in actor_states:
        actor = _safe_dict(actor)
        if _safe_str(actor.get("id")) == actor_id:
            merged = dict(actor)
            for key in ("activity", "availability", "location_id", "mood", "intent", "engagement"):
                value = _safe_str(after.get(key))
                if value:
                    merged[key] = value
            updated.append(merged)
            found = True
        else:
            updated.append(actor)
    if not found:
        raise ValueError(f"state_change_target_actor_missing:{actor_id}")

    simulation_state = _write_actor_states(simulation_state, updated)
    return simulation_state, runtime_state


def _record_accepted_state_change_event(runtime_state: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    event = _safe_dict(event)
    accepted = _safe_list(runtime_state.get("accepted_state_change_events"))
    accepted.append(event)
    accepted.sort(
        key=lambda x: (
            int(_safe_dict(x).get("tick", 0) or 0),
            _safe_str(_safe_dict(x).get("event_id")),
        )
    )
    runtime_state["accepted_state_change_events"] = accepted[-_MAX_ACCEPTED_STATE_CHANGE_EVENTS:]
    return runtime_state


def _record_applied_semantic_proposal_id(runtime_state: Dict[str, Any], proposal_id: str) -> Dict[str, Any]:
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    proposal_id = _safe_str(proposal_id)
    if not proposal_id:
        return runtime_state
    items = [x for x in _safe_list(runtime_state.get("applied_semantic_proposal_ids")) if _safe_str(x)]
    items.append(proposal_id)
    deduped = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    runtime_state["applied_semantic_proposal_ids"] = deduped[-_MAX_APPLIED_PROPOSAL_IDS:]
    return runtime_state


def _emit_scene_beat_from_accepted_state_change(runtime_state: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    event = _safe_dict(event)
    beat = _safe_dict(event.get("beat"))
    after = _safe_dict(event.get("after"))
    return emit_scene_beat(
        runtime_state,
        tick=int(event.get("tick", 0) or 0),
        summary=_safe_str(beat.get("summary")) or _safe_str(event.get("summary")),
        kind="state_change_beat",
        priority=int(beat.get("priority", 50) or 50),
        scene_id="",
        interaction_id=_safe_str(event.get("proposal_id")),
        actors=[_safe_str(event.get("actor_id"))] if _safe_str(event.get("actor_id")) else [],
        location_id=_safe_str(after.get("location_id")),
        recap_level=_safe_str(beat.get("recap_level")) or "notable",
        tags=[_safe_str(x) for x in _safe_list(beat.get("tags")) if _safe_str(x)],
    )


def process_semantic_state_change_proposals(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    print("SEMANTIC PROCESS queued =", runtime_state.get("semantic_state_change_proposals"))
    if _safe_bool(_safe_dict(runtime_state.get("runtime_settings")).get("verbose_semantic_trace"), False):
        print("SEMANTIC PROCESS accepted =", runtime_state.get("accepted_state_change_events"))
    print("SEMANTIC PROCESS rejected =", runtime_state.get("rejected_state_change_events"))
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)

    raw_proposals = [
        _normalize_semantic_state_change_proposal(x)
        for x in _safe_list(runtime_state.get("semantic_state_change_proposals"))
    ]
    proposals = []
    seen_proposal_ids = set()
    for proposal in raw_proposals:
        proposal_id = _safe_str(proposal.get("proposal_id"))
        if proposal_id and proposal_id in seen_proposal_ids:
            continue
        if proposal_id:
            seen_proposal_ids.add(proposal_id)
        proposals.append(proposal)

    # Current policy: proposals are processed once per tick and never retried.
    # Invalid proposals are recorded in rejected_state_change_events.
    remaining = []
    accepted_ids = _accepted_state_change_event_ids(runtime_state)
    applied_proposal_ids = _applied_semantic_proposal_ids(runtime_state)

    for proposal in proposals:
        proposal_id = _safe_str(proposal.get("proposal_id"))
        if proposal_id and proposal_id in applied_proposal_ids:
            continue

        validation = validate_semantic_state_change_proposal(proposal, simulation_state, runtime_state)
        if not validation.get("ok"):
            rejected = _safe_list(runtime_state.get("rejected_state_change_events"))
            rejected.append(
                {
                    "proposal_id": _safe_str(proposal.get("proposal_id")),
                    "actor_id": _safe_str(proposal.get("actor_id")),
                    "semantic_action": _safe_str(proposal.get("semantic_action")),
                    "errors": _safe_list(validation.get("errors")),
                    "tick": int(runtime_state.get("tick", 0) or 0),
                }
            )
            runtime_state["rejected_state_change_events"] = rejected[-_MAX_ACCEPTED_STATE_CHANGE_EVENTS:]
            continue

        try:
            event = compile_semantic_state_change_to_canonical_delta(
                proposal,
                simulation_state,
                runtime_state,
            )
        except ValueError as exc:
            rejected = _safe_list(runtime_state.get("rejected_state_change_events"))
            rejected.append(
                {
                    "proposal_id": _safe_str(proposal.get("proposal_id")),
                    "actor_id": _safe_str(proposal.get("actor_id")),
                    "semantic_action": _safe_str(proposal.get("semantic_action")),
                    "errors": [str(exc)],
                    "tick": int(runtime_state.get("tick", 0) or 0),
                }
            )
            runtime_state["rejected_state_change_events"] = rejected[-_MAX_ACCEPTED_STATE_CHANGE_EVENTS:]
            continue
        event_id = _safe_str(event.get("event_id"))
        if event_id and event_id in accepted_ids:
            continue

        simulation_state, runtime_state = _apply_canonical_state_change_event(
            simulation_state,
            runtime_state,
            event,
        )

        print(
            "DEBUG SEMANTIC EVENT APPEND accepted_state_change_events =",
            {
                "existing_count": len(_safe_list(runtime_state.get("accepted_state_change_events"))),
                "event_id": event.get("event_id"),
                "tick": event.get("tick"),
            },
        )

        runtime_state = _record_accepted_state_change_event(runtime_state, event)
        _log_interaction_trace(
            "semantic_accept",
            {
                "tick": _safe_int(event.get("tick"), 0),
                "actor_id": _safe_str(event.get("actor_id")),
                "semantic_action": _safe_str(event.get("semantic_action")),
                "summary": _safe_str(event.get("summary"))[:160],
                "interaction_count": len(_safe_list(simulation_state.get("active_interactions"))),
            },
            runtime_state,
        )
        if event_id:
            accepted_ids.add(event_id)
        runtime_state = _record_applied_semantic_proposal_id(runtime_state, proposal_id)
        applied_proposal_ids = _applied_semantic_proposal_ids(runtime_state)
        runtime_state = _emit_scene_beat_from_accepted_state_change(runtime_state, event)

    runtime_state["semantic_state_change_proposals"] = remaining
    return simulation_state, runtime_state


def _build_semantic_state_change_prompt_contract(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> str:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)

    actor_states = _safe_actor_states(simulation_state)
    location_rows = [
        {
            "id": _safe_str(x.get("id")),
            "name": _safe_str(x.get("name")),
        }
        for x in _safe_list(simulation_state.get("locations"))
        if isinstance(x, dict)
    ]
    interaction_rows = [
        {
            "id": _safe_str(x.get("id")),
            "type": _safe_str(x.get("type")),
            "subtype": _safe_str(x.get("subtype")),
            "participants": [_safe_str(p) for p in _safe_list(x.get("participants")) if _safe_str(p)],
            "resolved": bool(x.get("resolved")),
        }
        for x in _normalize_active_interactions(simulation_state, runtime_state)
    ]

    interacting_actor_ids = []
    seen_actor_ids = set()
    for row in interaction_rows:
        for actor_id in row.get("participants") or []:
            actor_id = _safe_str(actor_id)
            if actor_id and actor_id not in seen_actor_ids:
                seen_actor_ids.add(actor_id)
                interacting_actor_ids.append(actor_id)

    interacting_actor_rows = [
        {
            "id": _safe_str(a.get("id")),
            "name": _safe_str(a.get("name")),
            "activity": _safe_str(a.get("activity")),
            "availability": _safe_str(a.get("availability")),
            "location_id": _safe_str(a.get("location_id")),
            "mood": _safe_str(a.get("mood")),
            "intent": _safe_str(a.get("intent")),
            "engagement": _safe_str(a.get("engagement")),
        }
        for a in actor_states
        if _safe_str(a.get("id")) in set(interacting_actor_ids)
    ][: _MAX_LLM_PROPOSAL_CANDIDATES]

    # ── Recent player action context ────────────────────────────────────────
    last_player_action = _safe_dict(runtime_state.get("last_player_action"))
    player_action_context: Dict[str, Any] = {}
    if _safe_str(last_player_action.get("text")):
        player_action_context = {
            "action_type": _safe_str(last_player_action.get("action_type")),
            "text": _safe_str(last_player_action.get("text"))[:200],
            "target_id": _safe_str(last_player_action.get("target_id")),
        }

    # ── Recent scene context (player-driven beats) ───────────────────────
    recent_beats_context: List[Dict[str, str]] = []
    for beat in _safe_list(runtime_state.get("recent_scene_beats"))[-_MAX_PROMPT_SCENE_BEATS:]:
        beat = _safe_dict(beat)
        summary = _safe_str(beat.get("summary")).strip()
        if not summary:
            continue
        recent_beats_context.append({
            "kind": _safe_str(beat.get("kind")),
            "summary": summary[:200],
        })

    active_interactions_context = _build_active_interaction_prompt_context(
        simulation_state,
        _safe_int(simulation_state.get("tick"), 0),
    )

    _log_interaction_trace(
        "semantic_prompt_context",
        {
            "tick": _safe_int(simulation_state.get("tick"), 0),
            "interaction_count": len(active_interactions_context),
            "interaction_ids": [_safe_str(x.get("id")) for x in active_interactions_context],
        },
        runtime_state,
    )

    prompt_payload = {
        "scene_title": _safe_str(simulation_state.get("scene_title")),
        "location_name": _safe_str(simulation_state.get("location_name")),
        "allowed_semantic_actions": sorted(list(_allowed_semantic_actions().keys())),
        "allowed_delta_fields": ["activity", "availability", "location_id", "mood", "intent", "engagement"],
        "actors": [
            {
                "id": _safe_str(a.get("id")),
                "name": _safe_str(a.get("name")),
                "activity": _safe_str(a.get("activity")),
                "availability": _safe_str(a.get("availability")),
                "location_id": _safe_str(a.get("location_id")),
                "mood": _safe_str(a.get("mood")),
                "intent": _safe_str(a.get("intent")),
                "engagement": _safe_str(a.get("engagement")),
            }
            for a in actor_states[:_MAX_LLM_PROPOSAL_CANDIDATES]
        ],
        "locations": location_rows[:12],
        "active_interactions": interaction_rows[:8],
        "interacting_actor_ids": interacting_actor_ids[:_MAX_LLM_PROPOSAL_CANDIDATES],
        "interacting_actors": interacting_actor_rows,
    }
    if player_action_context:
        prompt_payload["recent_player_action"] = player_action_context
    if recent_beats_context:
        prompt_payload["recent_scene_beats"] = recent_beats_context[-_MAX_PROMPT_SCENE_BEATS:]
    if active_interactions_context:
        prompt_payload["active_interactions"] = active_interactions_context

    player_context_instruction = ""
    if player_action_context:
        player_context_instruction = (
            "IMPORTANT — REACT TO PLAYER ACTION:\n"
            "The player recently performed an action (see recent_player_action in INPUT).\n"
            "NPCs MUST react to the player's action rather than continuing generic routines.\n"
            "- NPCs nearby should watch, react, comment, or be affected by what the player is doing.\n"
            "- Do NOT generate generic patrol/observe/tidy actions when a notable player action is happening.\n"
            "- beat_summary MUST reference the player's ongoing activity, not routine NPC behavior.\n\n"
        )

    interaction_context_instruction = ""
    if active_interactions_context:
        interaction_context_instruction = (
            "IMPORTANT — ACTIVE INTERACTION IS STILL ONGOING:\n"
            "There is an unresolved active interaction in the scene (see active_interactions in INPUT).\n"
            "NPCs nearby MUST continue reacting to that interaction until it expires or resolves.\n"
            "- Do NOT revert to generic patrol, tidy, serve, or idle routines while the interaction is active.\n"
            "- beat_summary should reference the ongoing contest / performance / confrontation when appropriate.\n"
            "- Nearby authority figures should watch or react if the interaction is public.\n\n"
        )

    _log_interaction_trace(
        "semantic_prompt_context",
        {
            "tick": _safe_int(simulation_state.get("tick"), 0),
            "interaction_count": len(active_interactions_context),
            "active_interactions": active_interactions_context,
            "recent_player_action": player_action_context,
            "recent_scene_beats_count": len(recent_beats_context),
            "actor_count": len(_safe_list(simulation_state.get("actor_states"))),
        },
        runtime_state,
    )

    return (
        "You are a deterministic state-change generator for an RPG simulation.\n\n"
        "OUTPUT FORMAT REQUIREMENTS (MANDATORY):\n"
        "- Output ONLY valid JSON\n"
        "- No explanations\n"
        "- No thinking\n"
        "- No commentary\n"
        "- No markdown\n"
        "- No text outside JSON\n"
        "- JSON MUST be inside <RESPONSE> ... </RESPONSE>\n\n"
        "REQUIRED JSON STRUCTURE:\n\n"
        "<RESPONSE>{\n"
        '  "actor_id": "<npc_id>",\n'
        '  "proposal_kind": "state_delta",\n'
        '  "semantic_action": "<action>",\n'
        '  "delta": {\n'
        '    "activity": "<non-empty>",\n'
        '    "engagement": "<non-empty>"\n'
        '  },\n'
        '  "beat_summary": "<short sentence>"\n'
        "}</RESPONSE>\n\n"
        + player_context_instruction
        + interaction_context_instruction
        + "RULES:\n"
        '- "delta" MUST NOT be empty\n'
        '- "activity" MUST be meaningful (not "active")\n'
        '- "engagement" MUST be meaningful (not "ongoing")\n'
        "- Choose actions based on scene context\n"
        "- Prefer interaction, movement, or reactions over idle\n"
        "- When a player action is happening, NPCs should react to it\n\n"
        "EXAMPLES OF GOOD ACTIONS:\n"
        "- argue\n"
        "- observe\n"
        "- investigate\n"
        "- negotiate\n"
        "- rest\n"
        "- trade\n"
        "- react_to_player\n\n"
        "INPUT:\n"
        + json.dumps(prompt_payload, ensure_ascii=False, sort_keys=True)
    )


def _extract_json_array(text: str) -> List[Any]:
    text = _safe_str(text)
    if not text:
        return []
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end < start:
        return []
    try:
        parsed = json.loads(text[start:end + 1])
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _normalize_llm_text_output(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        for key in ("text", "output_text", "content", "response"):
            value = raw.get(key)
            if isinstance(value, str):
                return value
        return json.dumps(raw, ensure_ascii=False)
    return _safe_str(raw)


def llm_semantic_proposal_gateway(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Replay-safe gateway stub.

    Source of truth:
    - live mode: consume proposals already captured into runtime_state["recorded_semantic_llm_proposals"]
    - replay mode: consume the same recorded proposals

    This function MUST NOT call a live provider directly. Any future live LLM
    integration should happen upstream through a recorded nondeterministic
    boundary that persists prompt, raw output, and normalized proposals.
    """
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    recorded = _safe_list(runtime_state.get("recorded_semantic_llm_proposals"))
    out: List[Dict[str, Any]] = []
    seen = set()
    for item in recorded[:3]:
        proposal = _normalize_semantic_state_change_proposal(_safe_dict(item))
        proposal_id = _safe_str(proposal.get("proposal_id"))
        if proposal_id and proposal_id in seen:
            continue
        if proposal_id:
            seen.add(proposal_id)
        if not proposal.get("actor_id"):
            continue
        out.append(proposal)
    return out


def preview_semantic_state_change_prompt(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> str:
    return _build_semantic_state_change_prompt_contract(simulation_state, runtime_state)


def normalize_semantic_state_change_llm_output(raw_output: Any, simulation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Helper for an upstream recorded LLM boundary.

    Intended usage:
    - upstream layer calls live LLM
    - upstream layer records prompt + raw output
    - upstream layer passes raw output here to normalize proposals
    - normalized proposals are written to runtime_state["recorded_semantic_llm_proposals"]
    """
    raw_text = _normalize_llm_text_output(raw_output)
    if not raw_text:
        return []

    import json
    import re

    text = str(raw_text)

    # 1. Extract <RESPONSE> block if present
    import re

    match = re.search(r"<RESPONSE>(.*?)</RESPONSE>", text, re.DOTALL)

    if match:
        text = match.group(1)
    else:
        # 🔥 HARD FAIL instead of parsing garbage
        print("SEMANTIC CAPTURE no valid RESPONSE block")
        return []

    text = text.strip()

    try:
        data = json.loads(text)
    except Exception:
        return []

    # 🔥 HANDLE ALL VALID SHAPES
    proposals = []

    # Case 1: wrapped
    if isinstance(data, dict) and "state_changes" in data:
        proposals = data.get("state_changes") or []

    # Case 2: single proposal object
    elif isinstance(data, dict):
        proposals = [data]

    # Case 3: already a list
    elif isinstance(data, list):
        proposals = data

    else:
        return []

    normalized = []

    for p in proposals:
        p = _safe_dict(p)

        actor_id = _safe_str(p.get("actor_id"))
        if not actor_id:
            # fallback: assign first actor in scene
            actor_id = next(iter(simulation_state.get("npc_index", {}).keys()), "")

        if not actor_id:
            continue

        normalized_proposal = {
            "proposal_id": _safe_str(p.get("proposal_id")),
            "actor_id": actor_id,
            "proposal_kind": _safe_str(p.get("proposal_kind")) or "state_delta",
            "semantic_action": _safe_str(p.get("semantic_action")),
            "target_id": _safe_str(p.get("target_id")),
            "target_location_id": _safe_str(p.get("target_location_id")),
            "summary": _safe_str(p.get("summary")),
            "beat_summary": _safe_str(p.get("beat_summary")),
            "priority": int(p.get("priority") or 50),
            "delta": _safe_dict(p.get("delta")),
            "tags": _safe_list(p.get("tags")),
        }
        normalized_proposal["proposal_id"] = (
            _safe_str(normalized_proposal.get("proposal_id"))
            or _stable_semantic_state_change_proposal_id(
                normalized_proposal,
                simulation_state,
                {},
            )
        )
        normalized.append(normalized_proposal)

    return normalized


def _should_generate_llm_semantic_proposals(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> bool:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    # Keep activity generation alive at a low rate even if a small number of
    # queued proposals already exist.
    if len(_safe_list(runtime_state.get("semantic_state_change_proposals"))) > 2:
        return False
    if _safe_list(runtime_state.get("recorded_semantic_llm_proposals")):
        return True

    # Active interactions are explicitly allowed. NPCs should remain visibly
    # active during them, and the LLM proposal layer should be able to describe
    # that bounded behavior.
    actor_states = _safe_actor_states(simulation_state)
    if not actor_states:
        return False
    tick = _safe_int(runtime_state.get("tick", 0), 0)
    last_tick = _safe_int(runtime_state.get("last_semantic_llm_tick", -999999), -999999)
    return (tick - last_tick) >= _SEMANTIC_LLM_PROPOSAL_COOLDOWN_TICKS


def maybe_enqueue_llm_semantic_state_change_proposals(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> Dict[str, Any]:
    print("SEMANTIC ENQUEUE recorded =", runtime_state.get("recorded_semantic_llm_proposals"))
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    if not _should_generate_llm_semantic_proposals(simulation_state, runtime_state):
        return runtime_state
    proposals = llm_semantic_proposal_gateway(simulation_state, runtime_state)
    consumed_any = False
    for proposal in proposals:
        runtime_state = enqueue_semantic_state_change_proposal(runtime_state, proposal)
        consumed_any = True
    # Consume recorded proposals exactly once.
    if _safe_list(runtime_state.get("recorded_semantic_llm_proposals")):
        runtime_state = clear_recorded_semantic_llm_capture(runtime_state)
        consumed_any = True
    print("SEMANTIC ENQUEUE consumed_any =", consumed_any)
    print("SEMANTIC ENQUEUE last_tick =", runtime_state.get("last_semantic_llm_tick"))
    if consumed_any:
        runtime_state["last_semantic_llm_tick"] = _safe_int(runtime_state.get("tick", 0), 0)
    return runtime_state


def _safe_int(value, default=0):
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    try:
        return bool(value)
    except Exception:
        return default


def _interaction_trace_enabled(runtime_state: Dict[str, Any]) -> bool:
    runtime_state = _safe_dict(runtime_state)
    settings = _normalize_runtime_settings(_safe_dict(runtime_state.get("runtime_settings")))
    raw = settings.get("interaction_trace")
    if raw is None:
        return True
    return _safe_bool(raw, True)


def _compact_active_interactions(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for raw in _safe_list(items)[:8]:
        item = _safe_dict(raw)
        state = _safe_dict(item.get("state"))
        out.append(
            {
                "id": _safe_str(item.get("id")),
                "action_type": _safe_str(item.get("action_type")),
                "subtype": _safe_str(item.get("subtype")),
                "phase": _safe_str(item.get("phase")),
                "resolved": _safe_bool(item.get("resolved"), False),
                "updated_tick": _safe_int(item.get("updated_tick"), 0),
                "expires_tick": _safe_int(item.get("expires_tick"), 0),
                "participants": _safe_list(item.get("participants"))[:4],
                "mode": _safe_str(state.get("duration_mode")),
                "summary": _safe_str(state.get("summary"))[:120],
            }
        )
    return out


def _log_interaction_trace(label: str, payload: Dict[str, Any], runtime_state: Dict[str, Any] | None = None) -> None:
    # Temporarily force these traces to always show for debugging
    force_show = label in ("apply_turn_before_semantic_apply", "apply_turn_after_semantic_apply", "apply_turn_after_interaction_creation", "apply_turn_before_session_save", "idle_tick_start", "semantic_prompt_context")
    if runtime_state is not None and not (_interaction_trace_enabled(runtime_state) or force_show):
        return
    try:
        print(f"INTERACTION TRACE {label} = {payload}")
    except Exception:
        pass



def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _copy_dict(value: Any) -> Dict[str, Any]:
    return dict(_safe_dict(value))


def _stable_unique_labeled_items(values: List[Any], limit: int) -> List[str]:
    seen = set()
    out: List[str] = []
    for raw in _safe_list(values):
        if isinstance(raw, dict):
            value = (
                _safe_str(raw.get("summary")).strip()
                or _safe_str(raw.get("description")).strip()
                or _safe_str(raw.get("title")).strip()
                or _safe_str(raw.get("label")).strip()
                or _safe_str(raw.get("name")).strip()
            )
        else:
            value = _safe_str(raw).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
        if len(out) >= limit:
            break
    return out

def _build_world_advance_recap(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    debug_trace: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    debug_trace = _safe_dict(debug_trace)

    # Pull recent world signals
    world_events = _safe_list(simulation_state.get("recent_events"))
    consequences = _safe_list(simulation_state.get("recent_consequences"))
    threads = _safe_list(simulation_state.get("active_threads"))
    npcs = _safe_list(simulation_state.get("npc_states"))
    recent_changes = _safe_list(simulation_state.get("recent_changes"))
    director_log = _safe_list(runtime_state.get("director_log"))
    scene_beats = _safe_list(runtime_state.get("recent_scene_beats"))

    scene_title = (
        _safe_str(simulation_state.get("scene_title")) or
        _safe_str(debug_trace.get("scene_title"))
    )
    location_name = (
        _safe_str(simulation_state.get("location_name")) or
        _safe_str(debug_trace.get("location_name"))
    )

    # Fallbacks for current engine state shape.
    if not world_events:
        world_events = (
            _safe_list(simulation_state.get("events")) or
            _safe_list(simulation_state.get("world_events")) or
            _safe_list(runtime_state.get("world_events")) or
            _safe_list(runtime_state.get("recent_events"))
        )
    if not consequences:
        consequences = (
            _safe_list(simulation_state.get("effects")) or
            recent_changes or
            _safe_list(runtime_state.get("recent_changes"))
        )
    if not threads:
        threads = (
            _safe_list(simulation_state.get("threads")) or
            _safe_list(simulation_state.get("story_threads")) or
            _safe_list(runtime_state.get("threads"))
        )
    if not npcs:
        npcs = (
            _safe_list(simulation_state.get("actors")) or
            _safe_list(simulation_state.get("npcs")) or
            _safe_list(runtime_state.get("npc_states"))
        )

    # Highest-value sources first: active-scene beats, then consequences,
    # threads, recent changes, director activity, world events, NPC state.
    scene_beats_out = _choose_meaningful_recap_lines(scene_beats, limit=5)
    high_value_consequences = consequences if consequences else recent_changes
    consequences_out = _choose_meaningful_recap_lines(high_value_consequences, limit=5)
    threads_out = _choose_meaningful_recap_lines(threads, limit=4)
    director_activity_out = _choose_meaningful_recap_lines(director_log, limit=4)
    world_events_out = _choose_meaningful_recap_lines(world_events, limit=5)
    npc_updates_out = _choose_meaningful_recap_lines(npcs, limit=4)

    # Only backfill higher-value sections. Do NOT restore low-value world/NPC
    # filler after filtering, or the recap regresses to idle noise.
    if not scene_beats_out:
        scene_beats_out = _coerce_recap_labels(scene_beats, limit=5)
    if not consequences_out:
        consequences_out = _coerce_recap_labels(high_value_consequences, limit=5)
    if not threads_out:
        threads_out = _coerce_recap_labels(threads, limit=4)
    if not director_activity_out:
        director_activity_out = _coerce_recap_labels(director_log, limit=4)

    # Prefer scene beats and other higher-value sections over idle/filler event lines.
    if scene_beats_out or consequences_out or threads_out or director_activity_out:
        world_events_out = [
            x for x in world_events_out if _is_meaningful_recap_text(x)
        ]
        npc_updates_out = [
            x for x in npc_updates_out if _is_meaningful_recap_text(x)
        ]
    if scene_beats_out:
        # Keep scene beats in their own section. Do not duplicate them under world events.
        world_events_out = []

    has_sections = bool(
        scene_beats_out or consequences_out or threads_out or director_activity_out or world_events_out or npc_updates_out
    )

    recap = {
        "kind": "world_advance_recap",
        "summary": _build_player_facing_resume_summary(
            scene_title,
            location_name,
            debug_trace.get("advance_ticks", 0),
            has_sections,
        ),
        "additional_moments": int(debug_trace.get("advance_ticks", 0) or 0),
        "scene_beats": scene_beats_out,
        "world_events": world_events_out,
        "consequences": consequences_out,
        "threads": threads_out,
        "npc_updates": npc_updates_out,
        "director_activity": director_activity_out,
    }
    if not _recap_has_meaningful_sections(recap):
        recap["summary"] = _build_player_facing_resume_summary(scene_title, location_name, debug_trace.get("advance_ticks", 0), False)
    return recap


def _recap_has_meaningful_sections(recap: Dict[str, Any]) -> bool:
    recap = _safe_dict(recap)
    return bool(
        _safe_list(recap.get("scene_beats")) or
        _safe_list(recap.get("world_events")) or
        _safe_list(recap.get("consequences")) or
        _safe_list(recap.get("threads")) or
        _safe_list(recap.get("npc_updates")) or
        _safe_list(recap.get("director_activity"))
    )


def _normalize_active_interactions(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)

    raw_items = _safe_list(simulation_state.get("active_interactions"))
    if not raw_items:
        single = _safe_dict(
            simulation_state.get("active_interaction")
            or runtime_state.get("active_interaction")
        )
        if single:
            raw_items = [single]

    out: List[Dict[str, Any]] = []
    for item in raw_items:
        item = _safe_dict(item)
        if not item:
            continue
        interaction_id = _safe_str(item.get("id")) or _safe_str(item.get("interaction_id"))
        interaction_type = _safe_str(item.get("type")) or "interaction"
        interaction_subtype = _safe_str(item.get("subtype")) or interaction_type
        scene_id = _safe_str(item.get("scene_id"))
        location_id = _safe_str(item.get("location_id"))
        phase = _safe_str(item.get("phase"))
        resolved = bool(item.get("resolved"))
        winner = _safe_str(item.get("winner"))

        participants = [_safe_str(x) for x in _safe_list(item.get("participants")) if _safe_str(x)]
        if not participants:
            opponent_id = _safe_str(item.get("opponent_id")) or _safe_str(item.get("npc_id"))
            participants = ["player"] + ([opponent_id] if opponent_id else [])

        display_name = (
            _safe_str(item.get("opponent_name"))
            or _safe_str(item.get("npc_name"))
            or _safe_str(item.get("target_name"))
            or _safe_str(item.get("name"))
            or "your opponent"
        )

        state = _safe_dict(item.get("state"))
        if not state:
            # Backward-compatible flattening for older interaction shapes.
            state = {
                "player_progress": item.get("player_progress"),
                "opponent_progress": item.get("npc_progress"),
                "momentum": item.get("momentum_side"),
                "advantage": item.get("advantage"),
                "crowd_attention": item.get("crowd_attention"),
                "stakes": item.get("stakes"),
                "tone": item.get("tone"),
                "clue_found": item.get("clue_found"),
            }

        out.append(
            {
                "id": interaction_id or f"{interaction_type}:{interaction_subtype}:{scene_id or location_id or 'unknown'}",
                "type": interaction_type,
                "subtype": interaction_subtype,
                "scene_id": scene_id,
                "location_id": location_id,
                "phase": phase,
                "participants": participants,
                "display_name": display_name,
                "resolved": resolved,
                "winner": winner,
                "state": state,
            }
        )
    return out


def _interaction_memory_key(interaction: Dict[str, Any]) -> str:
    interaction = _safe_dict(interaction)
    return _safe_str(interaction.get("id")) or "interaction"


def _snapshot_interaction_for_memory(interaction: Dict[str, Any]) -> Dict[str, Any]:
    interaction = _safe_dict(interaction)
    return {
        "id": _safe_str(interaction.get("id")),
        "type": _safe_str(interaction.get("type")),
        "subtype": _safe_str(interaction.get("subtype")),
        "phase": _safe_str(interaction.get("phase")),
        "resolved": bool(interaction.get("resolved")),
        "winner": _safe_str(interaction.get("winner")),
        "participants": [_safe_str(x) for x in _safe_list(interaction.get("participants")) if _safe_str(x)],
        "state": _safe_dict(interaction.get("state")),
    }


def _detect_interaction_changes(prev_interaction: Dict[str, Any], interaction: Dict[str, Any]) -> List[Dict[str, Any]]:
    prev_interaction = _safe_dict(prev_interaction)
    interaction = _safe_dict(interaction)
    prev_state = _safe_dict(prev_interaction.get("state"))
    state = _safe_dict(interaction.get("state"))

    changes: List[Dict[str, Any]] = []
    if not prev_interaction:
        changes.append({"change_type": "started"})

    prev_phase = _safe_str(prev_interaction.get("phase"))
    phase = _safe_str(interaction.get("phase"))
    if phase and phase != prev_phase:
        changes.append({"change_type": "phase_changed", "from": prev_phase, "to": phase})

    prev_momentum = _safe_str(prev_state.get("momentum") or prev_state.get("advantage"))
    momentum = _safe_str(state.get("momentum") or state.get("advantage"))
    if momentum and momentum != prev_momentum:
        changes.append({"change_type": "momentum_shift", "from": prev_momentum, "to": momentum})

    prev_player_progress = _safe_int(prev_state.get("player_progress"), 0)
    player_progress = _safe_int(state.get("player_progress"), 0)
    if player_progress > prev_player_progress + 1:
        changes.append({
            "change_type": "player_progress",
            "delta": player_progress - prev_player_progress,
        })

    prev_opponent_progress = _safe_int(
        prev_state.get("opponent_progress", prev_state.get("npc_progress")),
        0,
    )
    opponent_progress = _safe_int(
        state.get("opponent_progress", state.get("npc_progress")),
        0,
    )
    if opponent_progress > prev_opponent_progress + 1:
        changes.append({
            "change_type": "opponent_progress",
            "delta": opponent_progress - prev_opponent_progress,
        })

    prev_tone = _safe_str(prev_state.get("tone"))
    tone = _safe_str(state.get("tone"))
    if tone and tone != prev_tone:
        changes.append({"change_type": "tone_changed", "from": prev_tone, "to": tone})

    prev_clue = bool(prev_state.get("clue_found"))
    clue = bool(state.get("clue_found"))
    if clue and not prev_clue:
        changes.append({"change_type": "clue_found"})

    prev_resolved = bool(prev_interaction.get("resolved"))
    resolved = bool(interaction.get("resolved"))
    if resolved and not prev_resolved:
        changes.append({"change_type": "resolved", "winner": _safe_str(interaction.get("winner"))})

    return changes


def _format_generic_interaction_beat(interaction: Dict[str, Any], change: Dict[str, Any]) -> str:
    interaction = _safe_dict(interaction)
    change = _safe_dict(change)
    name = _safe_str(interaction.get("display_name")) or "your opponent"
    subtype = _safe_str(interaction.get("subtype")) or _safe_str(interaction.get("type")) or "interaction"
    change_type = _safe_str(change.get("change_type"))

    if change_type == "started":
        return f"A {subtype.replace('_', ' ')} involving {name} begins."
    if change_type == "phase_changed":
        to_phase = _safe_str(change.get("to")).replace("_", " ")
        return f"The {subtype.replace('_', ' ')} with {name} shifts into a {to_phase} phase."
    if change_type == "momentum_shift":
        to_side = _safe_str(change.get("to"))
        if to_side == "player":
            return f"You gain the upper hand against {name}."
        return f"{name} gains the upper hand."
    if change_type == "player_progress":
        return f"You make visible progress against {name}."
    if change_type == "opponent_progress":
        return f"{name} pushes back and makes progress."
    if change_type == "tone_changed":
        tone = _safe_str(change.get("to")).replace("_", " ")
        return f"The exchange with {name} turns more {tone}."
    if change_type == "clue_found":
        return f"A useful clue emerges during the exchange with {name}."
    if change_type == "resolved":
        winner = _safe_str(change.get("winner"))
        if winner == "player":
            return f"The exchange with {name} ends in your favor."
        if winner:
            return f"{name} comes out ahead as the exchange concludes."
        return f"The exchange with {name} comes to an end."
    return ""


def _format_arm_wrestling_beat(interaction: Dict[str, Any], change: Dict[str, Any]) -> str:
    interaction = _safe_dict(interaction)
    change = _safe_dict(change)
    name = _safe_str(interaction.get("display_name")) or "your opponent"
    change_type = _safe_str(change.get("change_type"))

    if change_type == "started":
        return f"You and {name} lock hands as the arm-wrestling match begins."
    if change_type == "momentum_shift":
        to_side = _safe_str(change.get("to"))
        if to_side == "player":
            return f"{name} starts losing leverage as you force the match your way."
        return f"{name} surges forward, straining to overpower you."
    if change_type == "player_progress":
        return f"{name} struggles to stop your push as the table creaks under the strain."
    if change_type == "opponent_progress":
        return f"{name} digs in and drives your arm back toward the center."
    if change_type == "resolved":
        winner = _safe_str(change.get("winner"))
        if winner == "player":
            return f"{name}'s resistance breaks and the match ends in your favor."
        if winner:
            return f"{name} wins the match after a final burst of strength."
        return f"The arm-wrestling match between you and {name} comes to an end."
    return _format_generic_interaction_beat(interaction, change)


def _format_interaction_beat(interaction: Dict[str, Any], change: Dict[str, Any]) -> str:
    interaction = _safe_dict(interaction)
    interaction_type = _safe_str(interaction.get("type"))
    interaction_subtype = _safe_str(interaction.get("subtype"))

    if interaction_subtype == "arm_wrestling" or interaction_type == "arm_wrestling":
        return _format_arm_wrestling_beat(interaction, change)
    return _format_generic_interaction_beat(interaction, change)


def _emit_scene_beats_from_active_interactions(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = ensure_ambient_runtime_state(_safe_dict(runtime_state))

    interactions = _normalize_active_interactions(simulation_state, runtime_state)
    prev_memory = _safe_dict(runtime_state.get("scene_beat_memory"))
    next_memory: Dict[str, Any] = {}
    tick = _safe_int(runtime_state.get("tick", 0), 0)

    for interaction in interactions:
        # Skip resolved interactions — no new beats should be emitted for them.
        if _safe_bool(interaction.get("resolved"), False):
            continue
        key = _interaction_memory_key(interaction)
        prev_interaction = _safe_dict(prev_memory.get(key))
        changes = _detect_interaction_changes(prev_interaction, interaction)

        for idx, change in enumerate(changes):
            summary = _format_interaction_beat(interaction, change)
            if not _safe_str(summary):
                continue
            runtime_state = emit_scene_beat(
                runtime_state,
                tick=tick,
                summary=summary,
                kind="interaction_beat",
                priority=95 - idx,
                scene_id=_safe_str(interaction.get("scene_id")),
                interaction_id=_safe_str(interaction.get("id")),
                actors=[_safe_str(x) for x in _safe_list(interaction.get("participants")) if _safe_str(x)],
                location_id=_safe_str(interaction.get("location_id")),
                recap_level="major" if _safe_str(change.get("change_type")) == "resolved" else "notable",
                tags=["scene", "interaction", _safe_str(interaction.get("type")), _safe_str(interaction.get("subtype"))],
            )

        next_memory[key] = _snapshot_interaction_for_memory(interaction)

    runtime_state["scene_beat_memory"] = next_memory
    return runtime_state


def ensure_ambient_runtime_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    runtime_state.setdefault("ambient_queue", [])
    runtime_state.setdefault("ambient_history", [])
    runtime_state.setdefault("director_log", [])
    runtime_state.setdefault("scene_beat_memory", {})
    runtime_state.setdefault("recent_scene_beats", [])
    runtime_state["ambient_queue"] = _safe_list(runtime_state.get("ambient_queue"))[-_MAX_AMBIENT_UPDATES:]
    runtime_state["ambient_history"] = _safe_list(runtime_state.get("ambient_history"))[-_MAX_AMBIENT_UPDATES:]
    runtime_state["director_log"] = _safe_list(runtime_state.get("director_log"))[-_MAX_DIRECTOR_LOG:]
    runtime_state["scene_beat_memory"] = _safe_dict(runtime_state.get("scene_beat_memory"))
    runtime_state = _ensure_recent_scene_beats(runtime_state)
    return runtime_state


def _stable_unique_strs(values: List[Any]) -> List[str]:
    seen = set()
    out: List[str] = []
    for raw in values:
        value = _safe_str(raw).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _normalize_prompt_location_name(value: str, grounded_fallback: str) -> str:
    value = _safe_str(value).strip()
    if not value:
        return grounded_fallback
    if value.startswith("scene:tick:"):
        return grounded_fallback
    return value


def _resolve_location_name(
    simulation_state: Dict[str, Any],
    location_id: str,
    fallback_name: str = "",
) -> str:
    simulation_state = _safe_dict(simulation_state)
    location_id = _safe_str(location_id).strip()
    if not location_id:
        return _safe_str(fallback_name).strip()

    # Normalize location id (handle both colon and underscore formats)
    normalized_id = location_id.replace(":", "_").replace("-", "_").lower()
    
    # Modern format: locations is object dict keyed by location_id
    locations_map = _safe_dict(simulation_state.get("locations"))
    for key in locations_map:
        key_normalized = key.replace(":", "_").replace("-", "_").lower()
        if key_normalized == normalized_id:
            loc = _safe_dict(locations_map[key])
            return _safe_str(loc.get("name") or loc.get("title") or fallback_name or location_id)
    
    # Legacy format: locations is list
    for loc in _safe_list(simulation_state.get("locations")):
        loc = _safe_dict(loc)
        loc_id = _safe_str(loc.get("location_id") or loc.get("id")).replace(":", "_").replace("-", "_").lower()
        if loc_id == normalized_id:
            return _safe_str(loc.get("name") or loc.get("title") or fallback_name or location_id)
    
    final_fallback = _safe_str(fallback_name).strip() or location_id
    return final_fallback if final_fallback else "Current Location"


def _resolve_actor_names(simulation_state: Dict[str, Any], actor_ids: List[str]) -> List[str]:
    simulation_state = _safe_dict(simulation_state)
    npc_index = _safe_dict(simulation_state.get("npc_index"))
    names: List[str] = []
    for actor_id in _stable_unique_strs(actor_ids):
        npc = _safe_dict(npc_index.get(actor_id))
        names.append(_safe_str(npc.get("name") or actor_id))
    return names


def _derive_grounded_scene_context(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    turn_result: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    turn_result = _safe_dict(turn_result)

    opening_text = _safe_str(runtime_state.get("opening"))
    current_scene = _safe_dict(runtime_state.get("current_scene"))
    player_state = _safe_dict(simulation_state.get("player_state"))

    player_loc_id = _safe_str(player_state.get("location_id")).strip()
    nearby_ids = _safe_list(player_state.get("nearby_npc_ids"))
    present_scene_ids = _safe_list(current_scene.get("present_npc_ids"))
    actor_objs = _safe_list(current_scene.get("actors"))
    actor_obj_ids = [
        _safe_str(_safe_dict(a).get("id") or _safe_dict(a).get("npc_id") or _safe_dict(a).get("name"))
        for a in actor_objs
    ]

    location_id = (
        player_loc_id
        or _safe_str(current_scene.get("location_id"))
        or _safe_str(turn_result.get("location_id"))
    ).strip()
    location_name = _resolve_location_name(
        simulation_state,
        location_id,
        _safe_str(current_scene.get("location_name")).strip(),
    )

    present_actor_ids = _stable_unique_strs(nearby_ids + present_scene_ids + actor_obj_ids)
    present_actor_names = _resolve_actor_names(simulation_state, present_actor_ids)

    scene_title = (
        _safe_str(current_scene.get("title")).strip()
        or _safe_str(current_scene.get("scene_title")).strip()
        or location_name
        or "Current Scene"
    )
    scene_summary = (
        _safe_str(current_scene.get("summary")).strip()
        or _safe_str(current_scene.get("scene")).strip()
        or opening_text.strip()
        or "Your adventure continues."
    )

    return {
        "scene_title": scene_title,
        "location_id": location_id,
        "location_name": location_name or "Current Location",
        "scene_summary": scene_summary,
        "present_actor_ids": present_actor_ids,
        "present_actor_names": present_actor_names,
    }


def _apply_grounded_scene_overlay(scene: Dict[str, Any], grounded: Dict[str, Any]) -> Dict[str, Any]:
    scene = _copy_dict(_safe_dict(scene))
    grounded = _safe_dict(grounded)

    scene["title"] = _safe_str(scene.get("title")).strip() or _safe_str(grounded.get("scene_title")) or "Current Scene"
    scene["location_id"] = _safe_str(scene.get("location_id")).strip() or _safe_str(grounded.get("location_id"))
    scene["location_name"] = _safe_str(scene.get("location_name")).strip() or _safe_str(grounded.get("location_name")) or "Current Location"
    scene["summary"] = _safe_str(scene.get("summary")).strip() or _safe_str(grounded.get("scene_summary")) or "Your adventure continues."

    actor_names = _safe_list(grounded.get("present_actor_names"))
    if actor_names:
        scene["actors"] = actor_names

    present_ids = _safe_list(grounded.get("present_actor_ids"))
    if present_ids and not _safe_list(scene.get("present_npc_ids")):
        scene["present_npc_ids"] = present_ids

    return scene


def _ensure_scene_runtime_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    return ensure_persistent_scene_runtime_state(runtime_state)


def _filter_salient_player_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only player-meaningful events for idle initiative context."""
    result: List[Dict[str, Any]] = []
    for evt in _safe_list(events):
        evt = _safe_dict(evt)
        text = " ".join(
            [
                _safe_str(evt.get("type")),
                _safe_str(evt.get("event_type")),
                _safe_str(evt.get("description")),
                _safe_str(evt.get("summary")),
                _safe_str(evt.get("text")),
                _safe_str(evt.get("goal")),
                _safe_str(evt.get("label")),
            ]
        ).lower()
        if any(
            p in text
            for p in (
                "maintain awareness",
                "awareness of player",
                "baseline",
                "loyalty baseline",
                "faction loyalty baseline",
                "goal maintenance",
                "state driver",
            )
        ):
            continue
        result.append(evt)
    return result[-4:]


# ── Phase F — effective world behavior config ─────────────────────────────


def get_effective_world_behavior(session: Dict[str, Any]) -> Dict[str, Any]:
    """Merge setup world_behavior with runtime override.

    The setup config provides adventure-level defaults.
    The runtime override lets the player tune mid-game.
    """
    session = _safe_dict(session)
    setup = _safe_dict(session.get("setup_payload"))
    runtime = _safe_dict(session.get("runtime_state"))

    base = normalize_world_behavior_config(_safe_dict(setup.get("world_behavior")))
    override = _safe_dict(runtime.get("world_behavior_override"))

    effective = dict(base)
    from app.rpg.creator.schema import _WORLD_BEHAVIOR_ENUMS
    for key, allowed in _WORLD_BEHAVIOR_ENUMS.items():
        val = override.get(key)
        if isinstance(val, str) and val.strip().lower() in allowed:
            effective[key] = val.strip().lower()

    return effective


# ── Phase 1 — idle tick cadence policy ────────────────────────────────────


def compute_idle_tick_count(
    session: Dict[str, Any],
    *,
    elapsed_seconds: int = 0,
    reason: str = "heartbeat",
) -> int:
    """Decide how many idle ticks to apply based on context.

    Rules:
    - tab open heartbeat: usually 1 tick
    - resume catch-up: capped batch via elapsed_seconds
    - active encounter: suppress or reduce ambient chatter ticks
    - recent player action: lower ambient aggression briefly
    """
    session = _safe_dict(session)
    runtime = _safe_dict(session.get("runtime_state"))
    sim = _safe_dict(session.get("simulation_state"))

    encounter_active = bool(
        sim.get("encounter_active") or sim.get("active_encounter")
    )
    quiet_ticks = int(runtime.get("post_player_quiet_ticks", 0) or 0)

    if reason == "resume_catchup":
        raw = max(0, elapsed_seconds // 5)
        return min(raw, _MAX_RESUME_CATCHUP_TICKS)

    if reason == "heartbeat":
        # Suppress during active encounters
        if encounter_active:
            return 0
        # Reduce during quiet window after player action
        if quiet_ticks > 0:
            return 0
        return 1

    return 1


# ── Phase 5 — opening-aware runtime metadata ─────────────────────────────


def _build_opening_runtime(setup: Dict[str, Any]) -> Dict[str, Any]:
    """Build opening-aware runtime metadata from setup payload.

    Persisted as runtime_state["opening_runtime"].
    """
    setup = _safe_dict(setup)
    opening = _safe_dict(setup.get("opening"))

    if not opening:
        return {"active": False, "opening_resolved": True}

    return {
        "active": True,
        "scene_frame": _safe_str(opening.get("scene_frame")),
        "immediate_problem": _safe_str(opening.get("immediate_problem")),
        "player_involvement_reason": _safe_str(opening.get("player_involvement_reason")),
        "starter_conflict": _safe_str(setup.get("starter_conflict")),
        "present_npc_ids": _safe_list(opening.get("present_npc_ids")),
        "first_choices": _safe_list(opening.get("first_choices")),
        "opening_resolved": False,
    }


def _check_opening_resolution(
    session: Dict[str, Any],
) -> Dict[str, Any]:
    """Check simple rule-based conditions for opening resolution.

    Returns updated opening_runtime dict.
    """
    session = _safe_dict(session)
    runtime = _safe_dict(session.get("runtime_state"))
    sim = _safe_dict(session.get("simulation_state"))
    opening_rt = _safe_dict(runtime.get("opening_runtime"))

    if not opening_rt.get("active") or opening_rt.get("opening_resolved"):
        return opening_rt

    opening_rt = dict(opening_rt)

    # Rule: player has acted on opening conflict (tick > 3 means some engagement)
    tick = int(sim.get("tick", 0) or 0)
    player_turns = len(_safe_list(runtime.get("turn_history")))

    # Simple heuristics for opening resolution
    resolved = False

    # Player engaged with key opening NPCs (at least 2 turns)
    if player_turns >= 2:
        # Check if player interacted with opening NPCs
        turn_history = _safe_list(runtime.get("turn_history"))
        opening_npcs = set(_safe_list(opening_rt.get("present_npc_ids")))
        engaged_opening_npcs = set()
        for turn in turn_history:
            turn = _safe_dict(turn)
            action = _safe_dict(turn.get("action"))
            target = _safe_str(action.get("target_id") or action.get("npc_id"))
            if target in opening_npcs:
                engaged_opening_npcs.add(target)
        if engaged_opening_npcs:
            resolved = True

    # Player left opening location
    player_state = _safe_dict(sim.get("player_state"))
    player_loc = _safe_str(player_state.get("location_id"))
    opening_loc = _safe_str(_safe_dict(_safe_dict(session.get("setup_payload")).get("opening")).get("location_id"))
    if opening_loc and player_loc and player_loc != opening_loc and player_turns >= 1:
        resolved = True

    # Tick-based fallback: after tick 10, opening bias decays
    if tick >= 10:
        resolved = True

    if resolved:
        opening_rt["opening_resolved"] = True
        opening_rt["active"] = False

    return opening_rt


# ── Known NPC tracking ─────────────────────────────────────────────────────

_MAX_KNOWN_NPC_IDS = 64

def _update_known_npc_ids(runtime_state: Dict[str, Any], simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Update known NPC list from current player presence.
    
    Adds nearby NPCs to known list (append only, never remove).
    Maintains hard cap to prevent unbounded growth.
    Present NPCs are always drawn from current simulation state, not known list.
    """
    runtime_state = dict(runtime_state) if isinstance(runtime_state, dict) else {}
    simulation_state = _safe_dict(simulation_state)
    
    known = _safe_list(runtime_state.get("known_npc_ids", []))
    known_set = set(known)
    
    # Add currently nearby NPCs
    player = _safe_dict(simulation_state.get("player_state"))
    nearby = _safe_list(player.get("nearby_npc_ids", []))
    
    for npc_id in nearby:
        npc_id = _safe_str(npc_id).strip()
        if npc_id and npc_id not in known_set:
            known.append(npc_id)
            known_set.add(npc_id)
    
    # Cap to maximum size (keep most recent entries)
    if len(known) > _MAX_KNOWN_NPC_IDS:
        known = known[-_MAX_KNOWN_NPC_IDS:]
    
    runtime_state["known_npc_ids"] = known
    return runtime_state


def _build_opening_text(generated: Dict[str, Any]) -> str:
    opening_situation = _safe_dict(generated.get("opening_situation"))
    parts: List[str] = []
    summary = _safe_str(opening_situation.get("summary")).strip()
    location = _safe_str(opening_situation.get("location")).strip()
    present_actors = [str(v) for v in _safe_list(opening_situation.get("present_actors")) if str(v).strip()]
    if summary:
        parts.append(summary)
    if location:
        parts.append(f"You find yourself in {location}.")
    if present_actors:
        parts.append(f"Present: {', '.join(present_actors)}.")
    return " ".join(parts).strip() or "Your adventure begins…"


def _build_world_payload(setup: Dict[str, Any], generated: Dict[str, Any], canon_summary: Dict[str, Any]) -> Dict[str, Any]:
    world_frame = _safe_dict(generated.get("world_frame"))
    return {
        "title": _safe_str(setup.get("title") or world_frame.get("title")),
        "genre": _safe_str(setup.get("genre")),
        "setting": _safe_str(setup.get("setting")),
        "premise": _safe_str(setup.get("premise")),
        "summary": _safe_str(canon_summary.get("summary")),
    }


def _build_npc_cards(generated: Dict[str, Any]) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    for npc in _safe_list(generated.get("seed_npcs")):
        npc = _safe_dict(npc)
        if not npc:
            continue
        cards.append({
            "id": _safe_str(npc.get("npc_id")),
            "name": _safe_str(npc.get("name") or "Unknown"),
            "role": _safe_str(npc.get("role")),
            "description": _safe_str(npc.get("description")),
            "faction_id": npc.get("faction_id"),
            "location_id": npc.get("location_id"),
        })
    return cards


def _get_player_location_id(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> str:
    player_state = _safe_dict(simulation_state.get("player_state"))
    current_scene = _safe_dict(runtime_state.get("current_scene"))
    return (
        _safe_str(player_state.get("location_id")).strip()
        or _safe_str(current_scene.get("location_id")).strip()
        or _safe_str(current_scene.get("scene_id")).strip()
    )


def _extract_equipment(player_state: Dict[str, Any]) -> Dict[str, Any]:
    inventory_state = _safe_dict(player_state.get("inventory_state"))
    return _safe_dict(inventory_state.get("equipment"))


def select_primary_action(simulation_state: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    return candidates[0] if candidates else {"action_type": "investigate"}


def _structured_action_prompt(action: Dict[str, Any]) -> str:
    action = _safe_dict(action)
    npc_name = _safe_str(action.get("npc_name")).strip()
    npc_id = _safe_str(action.get("npc_id") or action.get("target_id")).strip()
    label = npc_name or npc_id or "them"
    action_type = _safe_str(action.get("action_type")).strip()
    legacy_action = _safe_str(action.get("action")).strip().lower()

    if legacy_action == "talk" or action_type == "persuade":
        return f"Talk to {label}"
    if legacy_action == "threaten" or action_type == "intimidate":
        return f"Threaten {label}"
    if label and action_type:
        return f"{action_type.replace('_', ' ').title()} {label}"
    if action_type:
        return action_type.replace("_", " ").title()
    return ""


def _normalize_structured_action(action: Any, player_input: str = "") -> Dict[str, Any]:
    normalized = _safe_dict(action)
    if not normalized:
        raw_input = _safe_str(player_input).strip()
        if raw_input.startswith("{") and raw_input.endswith("}"):
            try:
                normalized = _safe_dict(json.loads(raw_input))
            except Exception:
                normalized = {}

    if not normalized:
        return {}

    if normalized.get("action_type"):
        action_type = _safe_str(normalized.get("action_type")).strip().lower()
        if action_type == "talk":
            normalized["action_type"] = "persuade"
        elif action_type == "threaten":
            normalized["action_type"] = "intimidate"
        elif action_type == "threat":
            normalized["action_type"] = "threat"
        elif action_type == "social":
            normalized["action_type"] = "social_activity"
        normalized.setdefault(
            "target_id",
            _safe_str(normalized.get("target_id") or normalized.get("npc_id")).strip(),
        )
        return normalized

    legacy_type = _safe_str(normalized.get("type")).strip().lower()
    legacy_action = _safe_str(normalized.get("action")).strip().lower()
    npc_id = _safe_str(normalized.get("npc_id")).strip()
    npc_name = _safe_str(normalized.get("npc_name")).strip()

    if legacy_type == "npc_action":
        if legacy_action == "talk":
            return {
                "action_type": "persuade",
                "npc_id": npc_id,
                "npc_name": npc_name,
                "target_id": npc_id,
                "interaction": "talk",
                "difficulty": "normal",
            }
        if legacy_action == "threaten":
            return {
                "action_type": "intimidate",
                "npc_id": npc_id,
                "npc_name": npc_name,
                "target_id": npc_id,
                "interaction": "threaten",
                "difficulty": "normal",
            }

    normalized.setdefault("target_id", _safe_str(normalized.get("target_id") or npc_id).strip())
    if normalized.get("type") and not normalized.get("action_type"):
        normalized["action_type"] = _safe_str(normalized.get("type")).strip()
    return normalized


def _ensure_simulation_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _copy_dict(simulation_state)
    simulation_state = ensure_player_state(simulation_state)
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_memory_state(simulation_state)
    simulation_state = ensure_actor_memory_state(simulation_state)
    simulation_state = ensure_world_memory_state(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)
    simulation_state = ensure_world_item_state(simulation_state)
    simulation_state = _ensure_active_interactions(simulation_state)

    player_state = _safe_dict(simulation_state.get("player_state"))
    player_state = ensure_player_progression_state(player_state)
    inventory_state = _safe_dict(player_state.get("inventory_state"))
    player_state["inventory_state"] = inventory_state
    simulation_state["player_state"] = player_state
    return simulation_state


def _pickup_item_action(
    simulation_state: Dict[str, Any],
    action: Dict[str, Any],
) -> Dict[str, Any]:
    instance_id = _safe_str(action.get("instance_id")).strip()
    result = pickup_world_item(simulation_state, instance_id)
    next_state = _safe_dict(result.get("simulation_state"))
    picked_item = _safe_dict(result.get("picked_up_item"))
    if picked_item.get("item_id"):
        player_state = _safe_dict(next_state.get("player_state"))
        inventory_state = _safe_dict(player_state.get("inventory_state"))
        inventory_state = add_inventory_items(inventory_state, [picked_item])
        player_state["inventory_state"] = inventory_state
        next_state["player_state"] = player_state
    return {
        "simulation_state": next_state,
        "result": _safe_dict(result.get("result")),
        "picked_up_item": picked_item,
    }


def _drop_item_action(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    action: Dict[str, Any],
) -> Dict[str, Any]:
    item_id = _safe_str(action.get("item_id")).strip()
    qty = int(action.get("qty", 1) or 1)
    player_state = _safe_dict(simulation_state.get("player_state"))
    inventory_state = _safe_dict(player_state.get("inventory_state"))
    dropped_item = get_inventory_item_for_drop(inventory_state, item_id)
    inventory_state = remove_inventory_item(inventory_state, item_id, qty=qty)
    player_state["inventory_state"] = inventory_state
    simulation_state["player_state"] = player_state

    location_id = _get_player_location_id(simulation_state, runtime_state)
    drop_payload = dropped_item if dropped_item else {"item_id": item_id, "qty": qty}
    result = drop_world_item(simulation_state, drop_payload, location_id, qty=qty)
    next_state = _safe_dict(result.get("simulation_state"))
    return {
        "simulation_state": next_state,
        "result": _safe_dict(result.get("result")),
    }


def _equip_item_action(
    simulation_state: Dict[str, Any],
    action: Dict[str, Any],
) -> Dict[str, Any]:
    item_id = _safe_str(action.get("item_id")).strip()
    slot = _safe_str(action.get("slot")).strip()
    player_state = _safe_dict(simulation_state.get("player_state"))
    inventory_state = _safe_dict(player_state.get("inventory_state"))
    inventory_state = equip_inventory_item(inventory_state, item_id, slot)
    player_state["inventory_state"] = inventory_state
    simulation_state["player_state"] = player_state
    return {
        "simulation_state": simulation_state,
        "result": {
            "ok": True,
            "action_type": "equip_item",
            "item_id": item_id,
            "slot": slot or _safe_str(_safe_dict(_extract_equipment(player_state)).get("main_hand")),
            "equipment": _safe_dict(inventory_state.get("equipment")),
        },
    }


def _unequip_item_action(
    simulation_state: Dict[str, Any],
    action: Dict[str, Any],
) -> Dict[str, Any]:
    slot = _safe_str(action.get("slot")).strip()
    player_state = _safe_dict(simulation_state.get("player_state"))
    inventory_state = _safe_dict(player_state.get("inventory_state"))
    inventory_state = unequip_inventory_slot(inventory_state, slot)
    player_state["inventory_state"] = inventory_state
    simulation_state["player_state"] = player_state
    return {
        "simulation_state": simulation_state,
        "result": {
            "ok": True,
            "action_type": "unequip_item",
            "slot": slot,
            "equipment": _safe_dict(inventory_state.get("equipment")),
        },
    }


def _use_item_action(
    simulation_state: Dict[str, Any],
    action: Dict[str, Any],
) -> Dict[str, Any]:
    item_id = _safe_str(action.get("item_id")).strip()
    result = apply_item_use(simulation_state, item_id)
    return {
        "simulation_state": _safe_dict(result.get("simulation_state")),
        "result": _safe_dict(result.get("result")),
    }


def _apply_authoritative_action(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    action: Dict[str, Any],
) -> Dict[str, Any]:
    action_type = _safe_str(action.get("action_type")).strip()

    if action_type == "pickup_item":
        return _pickup_item_action(simulation_state, action)
    if action_type == "drop_item":
        return _drop_item_action(simulation_state, runtime_state, action)
    if action_type == "equip_item":
        return _equip_item_action(simulation_state, action)
    if action_type == "unequip_item":
        return _unequip_item_action(simulation_state, action)
    if action_type == "use_item":
        return _use_item_action(simulation_state, action)

    resolved = resolve_player_action(simulation_state, action)
    next_state = _safe_dict(resolved.get("simulation_state")) or simulation_state
    return {
        "simulation_state": next_state,
        "result": _safe_dict(resolved.get("result")),
    }


def _award_progression(
    simulation_state: Dict[str, Any],
    resolved_result: Dict[str, Any],
) -> Dict[str, Any]:
    player_state = _safe_dict(simulation_state.get("player_state"))
    explicit_player_xp = int(_safe_dict(resolved_result.get("xp_result")).get("player_xp", 0) or 0)
    computed_player_xp = int(compute_action_player_xp(resolved_result) or 0)
    action_xp = max(0, explicit_player_xp + computed_player_xp)
    stat_bonus = int(compute_stat_influence_bonus(player_state, resolved_result) or 0) if action_xp > 0 else 0
    total_player_xp = max(0, action_xp + stat_bonus)
    explicit_awards = _safe_dict(_safe_dict(resolved_result.get("skill_xp_result")).get("awards"))
    computed_skill_awards = {}

    if not explicit_awards:
        computed_skill_awards = compute_action_skill_xp(resolved_result)

    skill_xp_awards = dict(explicit_awards)
    for skill_id, amount in computed_skill_awards.items():
        skill_xp_awards[skill_id] = int(skill_xp_awards.get(skill_id, 0) or 0) + int(amount or 0)

    for skill_id, amount in skill_xp_awards.items():
        if int(amount or 0) > 0:
            player_state = award_skill_xp(player_state, skill_id, int(amount), source=_safe_str(resolved_result.get("action_type")))

    player_state = resolve_level_ups(player_state)
    level_ups = list(player_state.pop("_level_ups", []) or [])
    player_state = resolve_skill_level_ups(player_state)
    skill_level_ups = list(player_state.pop("_skill_level_ups", []) or [])

    simulation_state["player_state"] = player_state
    return {
        "simulation_state": simulation_state,
        "xp_result": {
            "player_xp": total_player_xp,
            "base_player_xp": action_xp,
            "explicit_player_xp": explicit_player_xp,
            "computed_player_xp": computed_player_xp,
            "stat_bonus": stat_bonus,
        },
        "skill_xp_result": {
            "awards": skill_xp_awards,
        },
        "level_up": level_ups,
        "skill_level_ups": skill_level_ups,
    }


def _initial_scene_state(generated: Dict[str, Any]) -> Dict[str, Any]:
    opening = _safe_dict(generated.get("opening_situation"))
    anchor = _safe_dict(generated.get("initial_scene_anchor"))
    scene_id = _safe_str(anchor.get("scene_id") or anchor.get("anchor_id") or "scene:opening")
    location_id = _safe_str(anchor.get("location_id") or opening.get("location_id"))
    location_name = _safe_str(anchor.get("location_name") or opening.get("location"))
    body = _safe_str(anchor.get("summary") or opening.get("summary"))
    present_actors = _safe_list(opening.get("present_actors"))
    return {
        "scene_id": scene_id,
        "scene": body or "Your adventure begins…",
        "summary": body or "Your adventure begins…",
        "location_id": location_id,
        "location_name": location_name,
        "actors": [{"id": _safe_str(name), "name": _safe_str(name)} for name in present_actors if _safe_str(name)],
        "options": [],
        "meta": {"origin": "adventure_start"},
        "metadata": {"origin": "adventure_start"},
    }


def build_session_from_start_result(setup_payload: Dict[str, Any], start_result: Dict[str, Any]) -> Dict[str, Any]:
    setup = apply_adventure_defaults(dict(setup_payload or {}))
    generated = _safe_dict(start_result.get("generated"))
    canon_summary = _safe_dict(start_result.get("canon_summary"))
    setup_id = _safe_str(setup.get("setup_id")).strip() or f"adventure_{_utc_now_iso()}"
    now = _utc_now_iso()

    metadata = _safe_dict(setup.get("metadata"))
    simulation_state = _safe_dict(metadata.get("simulation_state"))
    if not simulation_state:
        simulation_state = build_initial_simulation_state(setup)
        metadata["simulation_state"] = simulation_state
        setup["metadata"] = metadata

    simulation_state = _ensure_simulation_state(simulation_state)
    world = _build_world_payload(setup, generated, canon_summary)
    npcs = _build_npc_cards(generated)
    opening = _build_opening_text(generated)
    current_scene = _initial_scene_state(generated)

    session = {
        "manifest": {
            "session_id": setup_id,
            "schema_version": _SCHEMA_VERSION,
            "title": _safe_str(setup.get("title") or world.get("title") or "Untitled Adventure"),
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "source_pack_id": "",
            "source_template_id": _safe_str(metadata.get("template_name")),
        },
        "setup_payload": setup,
        "simulation_state": simulation_state,
        "runtime_state": {
            "tick": int(simulation_state.get("tick", 0) or 0),
            "opening": opening,
            "world": world,
            "npcs": npcs,
            "current_scene": current_scene,
            "last_turn_result": {},
            "turn_history": [],
            "voice_assignments": {},
            "settings": {
                "response_length": "short",
                "idle_conversation_seconds": 15,
                "idle_conversations_enabled": True,
                "idle_npc_to_player_enabled": True,
                "idle_npc_to_npc_enabled": True,
                "follow_reactions_enabled": True,
                "reaction_style": "normal",
                "console_debug_enabled": True,
                "world_events_panel_enabled": True,
                "interaction_duration_mode": "until_next_command",
                "interaction_duration_ticks": 5,
            },
            # Living-world ambient state (Phase 0.2)
            "ambient_queue": [],
            "ambient_seq": 0,
            "last_idle_tick_at": "",
            "last_player_turn_at": "",
            "idle_streak": 0,
            "ambient_cooldowns": {},
            "recent_ambient_ids": [],
            "pending_interrupt": None,
            "subscription_state": {"last_polled_seq": 0},
            "ambient_metrics": {"emitted": 0, "suppressed": 0, "coalesced": 0},
            "last_real_player_activity_at": "",
            "last_player_action_context": {},
            "idle_debug_trace": {},
            "recent_world_event_rows": [],
        },
    }
    session["session_id"] = setup_id
    return session


def build_frontend_bootstrap_payload(session: Dict[str, Any]) -> Dict[str, Any]:
    session = _safe_dict(session)
    manifest = _safe_dict(session.get("manifest"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    simulation_state = _safe_dict(session.get("simulation_state"))
    world = _safe_dict(runtime_state.get("world"))
    npcs = _safe_list(runtime_state.get("npcs"))
    opening = _safe_str(runtime_state.get("opening"))
    turn_result = _safe_dict(runtime_state.get("last_turn_result"))
    player_state = _safe_dict(simulation_state.get("player_state"))

    # Ensure grounded scene context is always available
    if not runtime_state.get("grounded_scene_context"):
        grounded = _derive_grounded_scene_context(simulation_state, runtime_state)
        current_scene = _safe_dict(runtime_state.get("current_scene"))
        current_scene = _apply_grounded_scene_overlay(current_scene, grounded)
        runtime_state["grounded_scene_context"] = grounded
        runtime_state["current_scene"] = current_scene

    current_scene = _safe_dict(runtime_state.get("current_scene"))
    narration = _safe_str(turn_result.get("narration")) or opening

    nearby_npcs = build_nearby_npc_cards(simulation_state, current_scene)

    inventory_state = _safe_dict(player_state.get("inventory_state"))
    equipment = _safe_dict(inventory_state.get("equipment"))

    return {
        "success": True,
        "session_id": _safe_str(manifest.get("id")),
        "title": _safe_str(manifest.get("title")),
        "opening": opening,
        "narration": narration,
        "player": {
            "stats": _safe_dict(player_state.get("stats")),
            "skills": _safe_dict(player_state.get("skills")),
            "level": int(player_state.get("level", 1) or 1),
            "xp": int(player_state.get("xp", 0) or 0),
            "xp_to_next": int(player_state.get("xp_to_next", 100) or 100),
            "inventory_state": inventory_state,
            "equipment": equipment,
            "nearby_npc_ids": _safe_list(player_state.get("nearby_npc_ids")),
            "available_checks": _safe_list(player_state.get("available_checks")),
        },
        "nearby_npcs": nearby_npcs,
        "known_npcs": npcs,
        "scene": {
            "scene_id": _safe_str(current_scene.get("scene_id")),
            "items": _safe_list(current_scene.get("items")),
            "available_checks": _safe_list(current_scene.get("available_checks")),
            "present_npc_ids": _safe_list(current_scene.get("present_npc_ids")),
        },
        "memory_summary": build_memory_ui_summary(simulation_state),
        "combat_result": _safe_dict(turn_result.get("combat_result")),
        "xp_result": _safe_dict(turn_result.get("xp_result")),
        "skill_xp_result": _safe_dict(turn_result.get("skill_xp_result")),
        "level_up": _safe_list(turn_result.get("level_up")),
        "skill_level_ups": _safe_list(turn_result.get("skill_level_ups")),
        "presentation": build_runtime_presentation_payload(simulation_state),
        "settings": _normalize_runtime_settings(_safe_dict(runtime_state.get("runtime_settings"))),
        "world_events_summary": {
            "recent_world_event_rows": _safe_list(runtime_state.get("recent_world_event_rows"))[-12:],
        },
        "grounded_scene_context": _safe_dict(runtime_state.get("grounded_scene_context")),
    }


def _find_target_by_name(bucket: Dict[str, Any], text: str) -> str:
    text_lc = text.lower()
    for entity_id, entity in sorted(bucket.items()):
        entity = _safe_dict(entity)
        candidates = [
            _safe_str(entity_id),
            _safe_str(entity.get("name")),
            _safe_str(entity.get("title")),
            _safe_str(entity.get("summary")),
        ]
        for candidate in candidates:
            candidate = candidate.strip().lower()
            if candidate and candidate in text_lc:
                return _safe_str(entity_id)
    return ""


def derive_player_action(simulation_state: Dict[str, Any], player_input: str) -> Dict[str, Any]:
    text = _safe_str(player_input).strip()
    text_lc = text.lower()
    threads = _safe_dict(simulation_state.get("threads"))
    factions = _safe_dict(simulation_state.get("factions"))

    if not text:
        return {}

    if any(token in text_lc for token in ("help", "intervene", "stop", "de-escalate", "defuse")):
        target_id = _find_target_by_name(threads, text)
        if target_id:
            return {
                "type": INTERVENE_THREAD,
                "target_id": target_id,
                "action_id": f"action:{int(simulation_state.get('tick', 0) or 0)}:{target_id}:intervene",
            }

    if any(token in text_lc for token in ("support", "aid", "ally with", "back ")) or text_lc.startswith("support "):
        target_id = _find_target_by_name(factions, text)
        if target_id:
            return {
                "type": SUPPORT_FACTION,
                "target_id": target_id,
                "action_id": f"action:{int(simulation_state.get('tick', 0) or 0)}:{target_id}:support",
            }

    if any(token in text_lc for token in ("attack", "escalate", "strike", "provoke")):
        target_id = _find_target_by_name(threads, text)
        if target_id:
            return {
                "type": ESCALATE_CONFLICT,
                "target_id": target_id,
                "action_id": f"action:{int(simulation_state.get('tick', 0) or 0)}:{target_id}:escalate",
            }

    return {}


def derive_action_candidates(simulation_state, player_input):
    candidates = []
    text = str(player_input.get("text", "") if isinstance(player_input, dict) else player_input).lower()
    target_id = _find_npc_target_by_name(simulation_state, text)

    # Passive observation: no XP path
    if any(w in text for w in ["look around", "look about", "observe", "glance", "scan", "take in"]):
        candidates.append({"action_type": "observe", "priority": 4})

    # Real investigation: deliberate scrutiny
    if any(w in text for w in ["investigate", "search", "examine", "inspect", "analyze"]):
        candidates.append({"action_type": "investigate", "priority": 6})

    # Unarmed combat
    if any(w in text for w in ["punch", "kick", "headbutt", "slam"]):
        candidates.append({"action_type": "attack_unarmed", "priority": 10})

    # Armed / generic combat
    if any(w in text for w in ["attack", "hit", "strike", "fight", "slash", "stab"]):
        candidates.append({"action_type": "attack_melee", "priority": 9})

    if any(w in text for w in ["shoot", "fire", "aim"]):
        candidates.append({"action_type": "attack_ranged", "priority": 10})

    # Defense
    if any(w in text for w in ["block", "defend", "shield"]):
        candidates.append({"action_type": "block", "priority": 8})
    if any(w in text for w in ["dodge", "evade", "roll"]):
        candidates.append({"action_type": "dodge", "priority": 8})
    # Social
    if any(w in text for w in ["persuade", "convince", "talk", "negotiate"]):
        candidates.append({"action_type": "persuade", "priority": 7, "target_id": target_id})
    if any(w in text for w in ["threaten", "intimidate", "scare"]):
        candidates.append({"action_type": "intimidate", "priority": 7, "target_id": target_id})

    # Broad open-ended social / activity lane.
    # The semantic action interpreter will determine whether this is darts,
    # singing, drinking, hugging, competing, trading, ritual, etc.
    if any(w in text for w in [
        "play", "challenge", "invite", "join", "dance", "sing", "perform",
        "hug", "embrace", "kiss", "toast", "drink with", "buy", "trade",
        "bet", "gamble", "pray", "ritual", "compete", "contest",
    ]):
        candidates.append({"action_type": "social_activity", "priority": 8, "target_id": target_id})
    # Stealth
    if any(w in text for w in ["sneak", "hide", "stealth"]):
        candidates.append({"action_type": "sneak", "priority": 6})
    if any(w in text for w in ["hack", "crack", "decrypt"]):
        candidates.append({"action_type": "hack", "priority": 6})
    if any(w in text for w in ["cast", "spell", "magic"]):
        candidates.append({"action_type": "cast_spell", "priority": 7})
    if any(w in text for w in ["threat", "warn", "menace"]):
        candidates.append({"action_type": "threat", "priority": 7, "target_id": target_id})
    # Items
    if any(w in text for w in ["pick up", "pickup", "grab", "take", "loot"]):
        candidates.append({"action_type": "pickup_item", "priority": 5})
    if any(w in text for w in ["equip", "wear", "wield"]):
        candidates.append({"action_type": "equip_item", "priority": 5})
    if any(w in text for w in ["use", "drink", "eat", "consume"]):
        candidates.append({"action_type": "use_item", "priority": 5})

    if not candidates:
        # Open-ended fallback: use observe as the safe minimum,
        # then let the semantic layer refine this into a bounded semantic action.
        candidates.append({"action_type": "observe", "priority": 1, "target_id": target_id})

    candidates.sort(key=lambda c: c.get("priority", 0), reverse=True)
    return candidates


def _fallback_scene(simulation_state: Dict[str, Any], player_input: str) -> Dict[str, Any]:
    return {
        "scene_id": f"scene:tick:{int(simulation_state.get('tick', 0) or 0)}",
        "scene": f"You act: {player_input}",
        "summary": f"You act: {player_input}",
        "location_id": _safe_str(_safe_dict(simulation_state.get("player_state")).get("location_id")),
        "actors": [],
        "options": [],
        "meta": {"origin": "fallback"},
        "metadata": {"origin": "fallback"},
    }


def _build_turn_payload(session: Dict[str, Any], narration_result: Dict[str, Any], summary: List[str]) -> Dict[str, Any]:
    session = _safe_dict(session)
    simulation_state = _safe_dict(session.get("simulation_state"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    current_scene = _safe_dict(runtime_state.get("current_scene"))
    memory_context = build_dialogue_memory_context(
        simulation_state,
        actor_id="player",
    )
    # Phase 18.3A — extract player state for XP/progression fields
    player_state = _safe_dict(simulation_state.get("player_state"))
    last_turn = _safe_dict(runtime_state.get("last_turn_result"))
    return {
        "success": True,
        "session_id": _safe_str(_safe_dict(session.get("manifest")).get("id")),
        "narration": _safe_str(narration_result.get("narrative") or current_scene.get("summary")),
        "choices": _safe_list(narration_result.get("choices")),
        "npcs": _safe_list(runtime_state.get("npcs")),
        "player": player_state,
        "memory": _safe_list(memory_context.get("items")),
        "worldEvents": _safe_list(simulation_state.get("events"))[-8:],
        "world_events": _safe_list(simulation_state.get("events"))[-8:],
        "summary": summary[:8],
        "scene": current_scene,
        "scene_presentation": build_scene_presentation_payload(simulation_state, current_scene),
        "presentation": build_runtime_presentation_payload(simulation_state),
        "dialogue_memory_context": memory_context,
        "llm_memory_prompt_block": build_llm_memory_prompt_block(memory_context),
        "voice_assignments": _safe_dict(runtime_state.get("voice_assignments")),
        "npc_reactions": _safe_list(narration_result.get("npc_reactions")),
        "dialogue_blocks": _safe_list(narration_result.get("dialogue_blocks")),
        "metadata": _safe_dict(narration_result.get("metadata")),
        "turn": int(runtime_state.get("tick", 0) or 0),
        # Phase 18.3A — XP and progression in turn response
        "player_level": int(player_state.get("level", 1) or 1),
        "player_xp": int(player_state.get("xp", 0) or 0),
        "player_skills": _safe_dict(player_state.get("skills")),
        "level_up": bool(last_turn.get("level_up")),
        "skill_level_ups": _safe_list(last_turn.get("skill_level_ups")),
    }


def load_runtime_session(session_id: str) -> Dict[str, Any] | None:
    if not session_id:
        return None
    return load_canonical_session(session_id)


def save_runtime_session(session: Dict[str, Any]) -> Dict[str, Any]:
    return save_canonical_session(session)


def apply_turn(session_id: str, player_input: str, action: Dict[str, Any] | None = None) -> Dict[str, Any]:
    session = load_runtime_session(session_id)
    if session is None:
        return {"ok": False, "error": "session_not_found"}

    session = _copy_dict(session)
    manifest = _safe_dict(session.get("manifest"))
    runtime_state = _copy_dict(session.get("runtime_state"))
    setup = apply_adventure_defaults(_copy_dict(session.get("setup_payload")))
    simulation_state = _ensure_simulation_state(_safe_dict(session.get("simulation_state")))

    player_input = _safe_str(player_input).strip()
    action = _normalize_structured_action(action, player_input)
    action = _coerce_action_target(simulation_state, action, player_input)

    if not action:
        candidates = derive_action_candidates(simulation_state, player_input)
        action = select_primary_action(simulation_state, candidates)

    action = _safe_dict(action)
    action_type = _safe_str(action.get("action_type")).strip()

    if not player_input:
        player_input = _structured_action_prompt(action)
    player_input = player_input or action_type.replace("_", " ").strip() or "Wait"

    llm_gateway = build_app_llm_gateway()
    advisory = {}
    semantic_advisory = {}
    semantic_action_record = {}
    runtime_state.setdefault("llm_records", [])
    runtime_state["llm_records_index"] = _safe_dict(runtime_state.get("llm_records_index"))
    runtime_state.setdefault("conversation_settings", {})
    runtime_state.setdefault("offscreen_conversation_summaries", [])
    runtime_state.setdefault("last_player_action", {})
    runtime_state.setdefault("last_conversation_intervention", {})
    mode = _safe_str(runtime_state.get("mode")).strip().lower() or "live"
    current_tick = int(runtime_state.get("tick", 0) or 0)

    runtime_state["last_player_action"] = {
        "action_id": f"player_action:{current_tick + 1}",
        "action_type": action_type,
        "text": _safe_str(player_input),
        "target_id": _safe_str(action.get("target_id")) if isinstance(action, dict) else "",
    }

    if mode == "live":
        advisory = get_action_advisory(
            llm_gateway=llm_gateway,
            player_input=player_input,
            simulation_state=simulation_state,
            runtime_state=runtime_state,
            candidate_action=action,
        )
        record = {
            "type": "action_advisory",
            "tick": current_tick,
            "player_input": player_input,
            "candidate_action": {
                "action_type": _safe_str(action.get("action_type")),
                "target_id": _safe_str(action.get("target_id")),
                "npc_id": _safe_str(action.get("npc_id")),
                "item_id": _safe_str(action.get("item_id")),
            },
            "output": _safe_dict(advisory),
        }
        runtime_state["llm_records"].append(record)
        runtime_state["llm_records_index"][
            f"action_advisory:{current_tick}"
        ] = record

        semantic_advisory = get_semantic_action_advisory(
            llm_gateway=llm_gateway,
            player_input=player_input,
            simulation_state=simulation_state,
            runtime_state=runtime_state,
            candidate_action=action,
        )
        semantic_record_capture = {
            "type": "semantic_action_advisory",
            "tick": current_tick,
            "player_input": player_input,
            "candidate_action": {
                "action_type": _safe_str(action.get("action_type")),
                "target_id": _safe_str(action.get("target_id")),
            },
            "output": _safe_dict(semantic_advisory),
        }
        runtime_state["llm_records"].append(semantic_record_capture)
        runtime_state["llm_records_index"][f"semantic_action_advisory:{current_tick}"] = semantic_record_capture
        runtime_state = _prune_llm_records_state(runtime_state)
    else:
        key = f"action_advisory:{current_tick}"
        record = _safe_dict(runtime_state.get("llm_records_index")).get(key)
        if not record:
            raise RuntimeError(f"missing_replay_action_advisory_for_tick:{current_tick}")
        advisory = _safe_dict(record.get("output"))

        semantic_key = f"semantic_action_advisory:{current_tick}"
        semantic_record = _safe_dict(runtime_state.get("llm_records_index")).get(semantic_key)
        if not semantic_record:
            raise RuntimeError(f"missing_replay_semantic_action_advisory_for_tick:{current_tick}")
        semantic_advisory = _safe_dict(semantic_record.get("output"))
    if advisory:
        action = merge_action_advisory(action, advisory)
        action_type = _safe_str(action.get("action_type")).strip()

    semantic_compiled_key = f"semantic_action_compiled:{current_tick}"
    if mode == "live":
        semantic_action_record = _compile_semantic_action_record(
            simulation_state=simulation_state,
            runtime_state=runtime_state,
            player_input=player_input,
            action=action,
            semantic_advisory=semantic_advisory,
        )
        semantic_compiled_capture = {
            "type": "semantic_action_compiled",
            "tick": current_tick,
            "player_input": player_input,
            "output": _safe_dict(semantic_action_record),
        }
        runtime_state["llm_records"].append(semantic_compiled_capture)
        runtime_state["llm_records_index"][semantic_compiled_key] = semantic_compiled_capture
        runtime_state = _prune_llm_records_state(runtime_state)
    else:
        semantic_compiled_record = _safe_dict(runtime_state.get("llm_records_index")).get(semantic_compiled_key)
        if not semantic_compiled_record:
            raise RuntimeError(f"missing_replay_semantic_action_compiled_for_tick:{current_tick}")
        semantic_action_record = _safe_dict(semantic_compiled_record.get("output"))

    action_metadata = _safe_dict(action.get("metadata"))
    action_metadata["semantic_action"] = semantic_action_record
    action["metadata"] = action_metadata
    runtime_state["last_player_action"] = _build_last_player_action_record(
        tick=current_tick,
        player_input=player_input,
        action=action,
        semantic_action_record=semantic_action_record,
    )

    authoritative = _apply_authoritative_action(simulation_state, runtime_state, action)
    after_action_state = _ensure_simulation_state(_safe_dict(authoritative.get("simulation_state")))
    resolved_result = _safe_dict(authoritative.get("result"))
    resolved_result.setdefault("action_type", action_type)

    progression = _award_progression(after_action_state, resolved_result)
    after_progression_state = _ensure_simulation_state(_safe_dict(progression.get("simulation_state")))

    metadata = _safe_dict(setup.get("metadata"))
    metadata["simulation_state"] = after_progression_state
    setup["metadata"] = metadata

    step_result = step_simulation_state(setup)
    next_setup = _safe_dict(step_result.get("next_setup")) or setup
    after_state = _ensure_simulation_state(_safe_dict(step_result.get("after_state")))

    # step_simulation_state does not carry over runtime-level active_interactions.
    after_state["active_interactions"] = _safe_list(after_progression_state.get("active_interactions"))

    _log_interaction_trace(
        "apply_turn_before_semantic_apply",
        {
            "tick": _safe_int(after_state.get("tick"), current_tick),
            "last_player_action": _safe_dict(runtime_state.get("last_player_action")),
            "count": len(_safe_list(after_state.get("active_interactions"))),
            "items": _compact_active_interactions(_safe_list(after_state.get("active_interactions"))),
        },
        runtime_state,
    )
    after_state, runtime_state = _apply_semantic_action_to_runtime(
        simulation_state=after_state,
        runtime_state=runtime_state,
        record=semantic_action_record,
    )
    _log_interaction_trace(
        "apply_turn_after_semantic_apply",
        {
            "tick": _safe_int(after_state.get("tick"), current_tick),
            "last_player_action": _safe_dict(runtime_state.get("last_player_action")),
            "count": len(_safe_list(after_state.get("active_interactions"))),
            "items": _compact_active_interactions(_safe_list(after_state.get("active_interactions"))),
        },
        runtime_state,
    )
    after_state, runtime_state = _persist_player_interaction_state_after_turn(
        after_state,
        runtime_state,
        player_input,
        semantic_action_record,
        current_tick,
    )
    after_state = _refresh_active_interactions_for_tick(
        after_state,
        _safe_int(after_state.get("tick"), current_tick),
    )
    _log_interaction_trace(
        "apply_turn_after_interaction_creation",
        {
            "tick": _safe_int(after_state.get("tick"), current_tick),
            "last_player_action": _safe_dict(runtime_state.get("last_player_action")),
            "count": len(_safe_list(after_state.get("active_interactions"))),
            "items": _compact_active_interactions(_safe_list(after_state.get("active_interactions"))),
        },
        runtime_state,
    )
    after_state = _resolve_until_next_command_interactions(
        after_state,
        runtime_state,
        semantic_action_record,
        current_tick,
    )
    after_state = _expire_stale_active_interactions(after_state, _safe_int(after_state.get("tick"), current_tick))
    runtime_state = _clean_resolved_interaction_world_event_rows(after_state, runtime_state)


    scenes = generate_scenes_from_simulation(after_state)
    current_scene = _safe_dict(scenes[0]) if scenes else _fallback_scene(after_state, player_input)

    player_state = _safe_dict(after_state.get("player_state"))
    current_location_id = _get_player_location_id(after_state, runtime_state)
    current_scene["items"] = list_scene_items(after_state, current_location_id)
    current_scene["nearby_npcs"] = build_nearby_npc_cards(after_state, current_scene)

    narration_context = {
        "simulation_state": after_state,
        "player_input": player_input,
        "resolved_result": resolved_result,
        "xp_result": _safe_dict(progression.get("xp_result")),
        "skill_xp_result": _safe_dict(progression.get("skill_xp_result")),
        "level_up": _safe_list(progression.get("level_up")),
        "skill_level_ups": _safe_list(progression.get("skill_level_ups")),
        "settings": runtime_state.get("runtime_settings", {}),
    }

    llm_gateway = build_app_llm_gateway()
    gateway_available = bool(llm_gateway)
    # ✅ FIX: Always apply authoritative grounded scene overlay before narration
    grounded = _derive_grounded_scene_context(after_state, runtime_state, resolved_result)
    current_scene = _apply_grounded_scene_overlay(current_scene, grounded)
    runtime_state["grounded_scene_context"] = grounded
    runtime_state["current_scene"] = current_scene
    runtime_state["tick"] = int(after_state.get("tick", runtime_state.get("tick", 0)) or 0)

    narration_result = narrate_scene(
        current_scene,
        narration_context,
        llm_gateway=llm_gateway,
        tone="dramatic",
    )
    if gateway_available and not narration_result.get("used_llm"):
        logger.error("RPG narration fallback occurred despite gateway availability")
    summary = summarize_simulation_step(step_result)
    runtime_state["last_turn_result"] = {
        "player_input": player_input,
        "action": action,
        "semantic_action": semantic_action_record,
        "resolved_result": resolved_result,
        "combat_result": _safe_dict(resolved_result.get("combat_result")),
        "xp_result": _safe_dict(progression.get("xp_result")),
        "skill_xp_result": _safe_dict(progression.get("skill_xp_result")),
        "level_up": _safe_list(progression.get("level_up")),
        "skill_level_ups": _safe_list(progression.get("skill_level_ups")),
        "summary": summary[:8],
        "narration": _safe_str(narration_result.get("narrative")),
    }
    runtime_state = _clear_stale_last_player_action(runtime_state, _safe_int(runtime_state.get("tick"), current_tick))
    turn_history = _safe_list(runtime_state.get("turn_history"))
    turn_history.append(_copy_dict(runtime_state["last_turn_result"]))
    runtime_state["turn_history"] = turn_history[-_MAX_HISTORY:]

    # Living-world: record player turn timing, reset idle streak
    runtime_state = ensure_ambient_runtime_state(runtime_state)
    runtime_state["last_player_turn_at"] = _utc_now_iso()
    runtime_state = _record_real_player_activity(runtime_state)
    # Classify player action context for reaction lane
    runtime_state["last_player_action_context"] = _classify_player_action_context(
        player_input, resolved_result, after_state, runtime_state,
    )
    # Phase 3D: quiet-window suppression after player action (idle chatter only)
    runtime_state["post_player_quiet_ticks"] = _DEFAULT_POST_PLAYER_QUIET_TICKS
    # Phase 5C: check if opening is resolved after player acts
    session["runtime_state"] = runtime_state
    runtime_state["opening_runtime"] = _check_opening_resolution(session)

    # Update known NPC list based on current presence
    runtime_state = _update_known_npc_ids(runtime_state, after_state)
    session["runtime_state"] = runtime_state

    _log_interaction_trace(
        "apply_turn_before_session_save",
        {
            "tick": _safe_int(after_state.get("tick"), current_tick),
            "last_player_action": _safe_dict(runtime_state.get("last_player_action")),
            "count": len(_safe_list(after_state.get("active_interactions"))),
            "items": _compact_active_interactions(_safe_list(after_state.get("active_interactions"))),
        },
        runtime_state,
    )
    session["simulation_state"] = after_state
    session["runtime_state"] = runtime_state
    session["setup_payload"] = next_setup
    manifest["updated_at"] = _utc_now_iso()
    session["manifest"] = manifest
    session = save_runtime_session(session)

    return {
        "ok": True,
        "session": session,
        "payload": {
            **build_frontend_bootstrap_payload(session),
            "narration": _safe_str(narration_result.get("narrative")),
            "combat_result": _safe_dict(resolved_result.get("combat_result")),
            "xp_result": _safe_dict(progression.get("xp_result")),
            "skill_xp_result": _safe_dict(progression.get("skill_xp_result")),
            "level_up": _safe_list(progression.get("level_up")),
            "skill_level_ups": _safe_list(progression.get("skill_level_ups")),
            "action_metadata": _safe_dict(action.get("metadata")),
            "structured_narration": _safe_dict(narration_result.get("structured_narration")),
            "speaker_turns": _safe_list(narration_result.get("speaker_turns")),
            "narration": _safe_str(narration_result.get("narrative")),
            "used_app_llm": bool(narration_result.get("used_llm")),
            "gateway_available": gateway_available,
            "raw_llm_narrative": _safe_str(narration_result.get("raw_llm_narrative")),
            "response_length": _safe_str(runtime_state.get("runtime_settings", {}).get("response_length", "short")),
            "presentation": build_runtime_presentation_payload(after_state),
        },
    }


# ── Living world: idle tick engine (Phase 1) ──────────────────────────────


def _advance_simulation_for_idle(session: Dict[str, Any], *, reason: str = "heartbeat") -> Dict[str, Any]:
    """Step simulation forward without player input.

    Uses existing step_simulation_state() but does not require player action.
    Preserves canonical tick order and records metadata.
    """
    setup = apply_adventure_defaults(_copy_dict(session.get("setup_payload")))
    simulation_state = _ensure_simulation_state(_safe_dict(session.get("simulation_state")))

    metadata = _safe_dict(setup.get("metadata"))
    metadata["simulation_state"] = simulation_state
    setup["metadata"] = metadata

    step_result = step_simulation_state(setup)
    after_state = _ensure_simulation_state(_safe_dict(step_result.get("after_state")))
    next_setup = _safe_dict(step_result.get("next_setup")) or setup

    # step_simulation_state evolves factions/locations/events but does not
    # know about runtime-level active_interactions.  Carry them forward from
    # the pre-step simulation state so they survive idle ticks.
    after_state["active_interactions"] = _safe_list(simulation_state.get("active_interactions"))

    return {
        "ok": True,
        "before_state": _safe_dict(step_result.get("before_state")),
        "after_state": after_state,
        "next_setup": next_setup,
        "step_result": step_result,
        "reason": reason,
    }


def _build_idle_player_context(
    after_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> Dict[str, Any]:
    player_state = _safe_dict(after_state.get("player_state"))
    current_scene = _safe_dict(runtime_state.get("current_scene"))
    idle_streak = int(runtime_state.get("idle_streak", 0) or 0)
    return {
        "player_location": _safe_str(
            player_state.get("location_id")
            or current_scene.get("location_id")
        ),
        "nearby_npc_ids": _safe_list(player_state.get("nearby_npc_ids")),
        "scene_id": _safe_str(current_scene.get("scene_id")),
        "world_summary": _safe_str(current_scene.get("summary") or current_scene.get("scene")),
        "player_idle": idle_streak > 0,
        "active_conflict": _safe_str(
            _safe_dict(after_state.get("active_conflict")).get("conflict_id")
            if isinstance(after_state.get("active_conflict"), dict) else ""
        ),
        "recent_incidents": _safe_list(after_state.get("incidents"))[-4:],
        "salient_events": _filter_salient_player_events(
            _safe_list(after_state.get("events"))
        ),
    }


def _apply_idle_tick_to_session(
    session: Dict[str, Any],
    *,
    reason: str = "heartbeat",
) -> Dict[str, Any]:
    """Apply one idle tick to an in-memory session.

    This is the canonical implementation for idle ticking.
    Public wrappers should load/save around this helper rather than
    recursively calling apply_idle_tick() in a loop.
    """
    session = _copy_dict(session)
    runtime_state = ensure_ambient_runtime_state(_copy_dict(session.get("runtime_state")))
    simulation_state = _safe_dict(session.get("simulation_state"))

    _log_interaction_trace(
        "idle_tick_start",
        {
            "tick": _safe_int(simulation_state.get("tick"), 0),
            "count": len(_safe_list(simulation_state.get("active_interactions"))),
            "items": _compact_active_interactions(_safe_list(simulation_state.get("active_interactions"))),
            "last_player_action": _safe_dict(runtime_state.get("last_player_action")),
        },
        runtime_state,
    )

    mode = _safe_str(runtime_state.get("mode")).strip().lower() or "live"

    # Simulation tick is authoritative; runtime tick is only a mirror/cache.
    current_tick = int(_safe_dict(session.get("simulation_state")).get("tick", runtime_state.get("tick", 0)) or 0)
    idle_capture_key = f"idle_tick:{current_tick}"

    if mode == "replay":
        captured = _safe_dict(_safe_dict(runtime_state.get("llm_records_index")).get(idle_capture_key))
        if not captured:
            return {"ok": False, "error": f"missing_replay_idle_tick_for_tick:{current_tick}"}
        replay_updates = _safe_list(captured.get("updates"))
        if not replay_updates:
            return {"ok": False, "error": f"missing_replay_ambient_updates_for_tick:{current_tick}"}

        # Harden replay contract: updates must already be presentation-ready.
        for idx, update in enumerate(replay_updates):
            update = _safe_dict(update)
            if not _safe_str(update.get("text")):
                return {"ok": False, "error": f"missing_replay_ambient_text_for_tick:{current_tick}:index:{idx}"}
            if not _safe_str(update.get("delivery")):
                return {"ok": False, "error": f"missing_replay_ambient_delivery_for_tick:{current_tick}:index:{idx}"}

        return {
            "ok": True,
            "session": session,
            "updates": replay_updates,
            "latest_seq": int(captured.get("latest_seq", 0) or 0),
            "idle_streak": int(captured.get("idle_streak", 0) or 0),
        }

    advance_result = _advance_simulation_for_idle(session, reason=reason)
    if not advance_result.get("ok"):
        return {"ok": False, "error": "idle_advance_failed"}

    before_state = _safe_dict(advance_result.get("before_state"))
    after_state = _safe_dict(advance_result.get("after_state"))
    next_setup = _safe_dict(advance_result.get("next_setup"))

    # Phase 3D: quiet-window suppression after player action
    quiet_ticks = int(runtime_state.get("post_player_quiet_ticks", 0) or 0)
    if quiet_ticks > 0:
        runtime_state["post_player_quiet_ticks"] = quiet_ticks - 1

    # Phase F: effective world behavior config
    session["runtime_state"] = runtime_state
    world_behavior = get_effective_world_behavior(session)

    # Debug trace for full observability
    debug_trace: Dict[str, Any] = {
        "reason": reason,
        "tick_before": int(before_state.get("tick", 0) or 0),
        "quiet_ticks_before": int(runtime_state.get("post_player_quiet_ticks", 0) or 0),
        "world_behavior": dict(world_behavior),
        "last_player_action_context": _safe_dict(runtime_state.get("last_player_action_context")),
        "raw_counts": {},
        "selected": {},
        "visibility": {},
        "delivery": {},
        "filters": [],
    }

    # Real idle-seconds calculation
    idle_seconds = _seconds_since_iso(_safe_str(runtime_state.get("last_real_player_activity_at")))
    settings = _normalize_runtime_settings(_safe_dict(runtime_state.get("runtime_settings")))
    conversation_idle_seconds = int(settings.get("idle_conversation_seconds", 15) or 15)
    prior_idle_streak = int(runtime_state.get("idle_streak", 0) or 0)
    idle_gate_open = bool(settings.get("idle_conversations_enabled")) and (
        idle_seconds >= conversation_idle_seconds
        or prior_idle_streak >= 2
    )
    debug_trace["idle_seconds"] = idle_seconds
    debug_trace["idle_gate_open"] = idle_gate_open
    debug_trace["idle_gate_reason"] = (
        "time_threshold"
        if idle_seconds >= conversation_idle_seconds else
        ("idle_streak" if prior_idle_streak >= 2 else "closed")
    )
    debug_trace["conversation_idle_seconds"] = conversation_idle_seconds

    player_context = _build_idle_player_context(after_state, runtime_state)
    context = {
        "player_location": _safe_str(player_context.get("player_location")),
        "nearby_npc_ids": _safe_list(player_context.get("nearby_npc_ids")),
        "recent_ambient_ids": _safe_list(runtime_state.get("recent_ambient_ids")),
    }

    raw_updates = build_ambient_updates(before_state, after_state, runtime_state)

    # Phase 2: NPC initiative candidates (in addition to ambient dialogue)
    initiative_candidates = build_npc_initiative_candidates(
        after_state, runtime_state, player_context,
    )
    # Phase F4: apply world behavior bias to initiative candidates
    initiative_candidates = apply_world_behavior_bias(initiative_candidates, world_behavior)
    selected_initiative = select_npc_initiative_candidate(initiative_candidates, runtime_state)

    # ── Phase G / G+1: scene weaving + continuity ───────────────────
    scene_beats = []
    current_tick = int(after_state.get("tick", runtime_state.get("tick", 0)) or 0)
    continuing_scene = select_continuing_scene(runtime_state, after_state, current_tick)
    selected_scene = None

    if continuing_scene:
        scene_beats = build_continuation_beats(continuing_scene, after_state)[:3]
        runtime_state = advance_scene(
            runtime_state,
            _safe_str(continuing_scene.get("scene_id")),
            current_tick,
            player_ignored=True,
        )

        for beat in scene_beats:
            raw_updates.append(_make_scene_update_from_beat(beat))

        # When continuing a scene, suppress same-speaker standalone initiative.
        continuing_participants = set(_safe_list(continuing_scene.get("participants")))
        if selected_initiative and _safe_str(selected_initiative.get("speaker_id")) in continuing_participants:
            selected_initiative = None
    else:
        scene_candidates = build_scene_candidates(
            after_state,
            runtime_state,
            player_context,
        )
        selected_scene = select_scene_candidate(scene_candidates, runtime_state)
        scene_runtime = _safe_dict(runtime_state.get("scene_runtime"))
        last_scene_tick = int(scene_runtime.get("last_scene_tick", -999) or -999)

        if selected_scene and (current_tick - last_scene_tick) < 2:
            selected_scene = None

        if selected_scene and selected_initiative:
            scene_participants = set(_safe_list(selected_scene.get("participants")))
            if _safe_str(selected_initiative.get("speaker_id")) in scene_participants:
                selected_initiative = None

        if selected_scene:
            runtime_state = apply_scene_cooldowns(runtime_state, selected_scene)
            runtime_state = start_persistent_scene(runtime_state, selected_scene, current_tick)
            scene_beats = build_scene_beats(
                selected_scene,
                after_state,
                runtime_state,
            )[:3]

            scene_runtime = _safe_dict(runtime_state.get("scene_runtime"))
            scene_runtime["last_scene_tick"] = current_tick
            runtime_state["scene_runtime"] = scene_runtime

            for beat in scene_beats:
                raw_updates.append(_make_scene_update_from_beat(beat))

    if selected_initiative:
        runtime_state = apply_initiative_cooldowns(runtime_state, selected_initiative)
        raw_updates.append(
            _make_initiative_update_from_candidate(selected_initiative)
        )

    # Phase 6: world event director
    world_event_candidates = build_world_event_candidates(
        after_state, runtime_state, player_context,
    )
    world_event_candidates = apply_world_behavior_to_events(
        world_event_candidates, world_behavior,
    )
    filtered_events = filter_world_events(world_event_candidates, session)
    event_updates = convert_events_to_ambient_updates(filtered_events, runtime_state)
    raw_updates.extend(event_updates)

    # ── Reaction lane: immediate NPC reactions to player actions ──
    reaction_candidates = build_ambient_dialogue_candidates(
        after_state, runtime_state, player_context, lane="reaction",
    )
    reaction_initiative = build_npc_initiative_candidates(
        after_state, runtime_state, player_context, lane="reaction",
    )
    reaction_initiative = apply_world_behavior_bias(reaction_initiative, world_behavior)
    reaction_candidates.extend(reaction_initiative)
    selected_reaction = select_ambient_dialogue_candidate(reaction_candidates, runtime_state)
    if selected_reaction and quiet_ticks > 0:
        # Reaction lane bypasses quiet suppression for important kinds
        rk = _safe_str(selected_reaction.get("kind"))
        if rk not in _CRITICAL_REACTION_KINDS:
            selected_reaction = None
    if selected_reaction:
        runtime_state = apply_dialogue_cooldowns(runtime_state, selected_reaction)
        raw_updates.append(
            _make_dialogue_update_from_candidate(
                selected_reaction,
                {
                    "scene_id": _safe_str(player_context.get("scene_id")),
                    "world_summary": _safe_str(player_context.get("world_summary")),
                },
            )
        )

    # ── Idle conversation lane: only if idle gate is open ──
    idle_dialogue_candidates: List[Dict[str, Any]] = []
    selected_dialogue = None
    if idle_gate_open:
        idle_dialogue_candidates = build_ambient_dialogue_candidates(
            after_state, runtime_state, player_context, lane="idle",
        )
        selected_dialogue = select_ambient_dialogue_candidate(idle_dialogue_candidates, runtime_state)
    if selected_dialogue:
        runtime_state = apply_dialogue_cooldowns(runtime_state, selected_dialogue)
        raw_updates.append(
            _make_dialogue_update_from_candidate(
                selected_dialogue,
                {
                    "scene_id": _safe_str(player_context.get("scene_id")),
                    "world_summary": _safe_str(player_context.get("world_summary")),
                },
            )
        )

    # Record debug trace counts
    debug_trace["raw_counts"] = {
        "ambient_updates": len(raw_updates),
        "initiative_candidates": len(initiative_candidates),
        "reaction_candidates": len(reaction_candidates),
        "idle_dialogue_candidates": len(idle_dialogue_candidates),
        "scene_beats": len(scene_beats) if scene_beats else 0,
        "world_event_candidates": len(world_event_candidates),
    }
    debug_trace["selected"] = {
        "initiative": _safe_dict(selected_initiative) if selected_initiative else {},
        "reaction": _safe_dict(selected_reaction) if selected_reaction else {},
        "idle_dialogue": _safe_dict(selected_dialogue) if selected_dialogue else {},
        "scene": _safe_dict(selected_scene) if selected_scene else {},
    }

    visible = [u for u in raw_updates if is_player_visible_update(u, session)]
    for u in visible:
        u["priority"] = score_ambient_salience(u, context)
    coalesced = coalesce_ambient_updates(visible, runtime_state)
    debug_trace["visibility"] = {
        "visible_count": len(visible),
        "coalesced_count": len(coalesced),
    }

    runtime_state = enqueue_ambient_updates(runtime_state, coalesced)

    # Scene continuity cleanup + scene-driven consequence
    scene_runtime = _safe_dict(runtime_state.get("scene_runtime"))
    for scene in _safe_list(scene_runtime.get("active_scenes")):
        consequence = maybe_build_scene_consequence(scene, after_state)
        if consequence:
            scene["consequence_emitted"] = True
            runtime_state = enqueue_ambient_updates(runtime_state, [consequence])
    runtime_state = compact_finished_scenes(runtime_state)
    queued_updates = get_pending_ambient_updates(
        {"runtime_state": runtime_state},
        after_seq=max(0, int(runtime_state.get("ambient_seq", 0) or 0) - len(coalesced)),
        limit=max(1, len(coalesced) or 1),
    )
    narrated_updates, runtime_state = _apply_ambient_narration_and_delivery(
        session=session,
        updates=queued_updates,
        after_state=after_state,
        runtime_state=runtime_state,
        idle_capture_key=idle_capture_key,
    )
    if narrated_updates:
        queue = _safe_list(runtime_state.get("ambient_queue"))
        by_seq = {int(_safe_dict(u).get("seq", 0) or 0): u for u in narrated_updates}
        runtime_state["ambient_queue"] = [
            _copy_dict(by_seq.get(int(_safe_dict(item).get("seq", 0) or 0)) or item)
            for item in queue
        ]

    runtime_state["idle_streak"] = int(runtime_state.get("idle_streak", 0) or 0) + 1
    runtime_state["last_idle_tick_at"] = _utc_now_iso()
    runtime_state["tick"] = int(after_state.get("tick", runtime_state.get("tick", 0)) or 0)
    runtime_state = normalize_ambient_state(runtime_state)

    # Advance living-world activities
    runtime_state = advance_actor_activities_for_tick(after_state, runtime_state)
    runtime_state = emit_activity_beats_for_tick(after_state, runtime_state)
    runtime_state = propagate_activity_consequences_for_tick(after_state, runtime_state)
    runtime_state = decay_world_consequences_for_tick(after_state, runtime_state)

    # Use the advanced simulation state for emitted scene beats.
    simulation_state = after_state

    # Derive replay-safe, player-facing scene beats AFTER tick advancement so
    # the emitted beats reflect the newly advanced interaction state.
    runtime_state = _emit_scene_beats_from_active_interactions(simulation_state, runtime_state)

    # Ask the LLM for bounded semantic state-change proposals only when there
    # is no active unresolved interaction and no queued proposals already.
    runtime_state = maybe_enqueue_llm_semantic_state_change_proposals(simulation_state, runtime_state)

    # NPC reaction pass
    authoritative_tick = current_tick
    simulation_state, runtime_state = _run_npc_reaction_pass(
        simulation_state,
        runtime_state,
        authoritative_tick,
    )
    session["simulation_state"] = simulation_state
    session["runtime_state"] = runtime_state

    # Compile and apply structured semantic state-change proposals, then emit
    # beats from the accepted canonical deltas.
    simulation_state, runtime_state = process_semantic_state_change_proposals(simulation_state, runtime_state)

    session["runtime_state"] = runtime_state

    # Phase 5C: check opening resolution during idle
    runtime_state["opening_runtime"] = _check_opening_resolution(session)
    session["runtime_state"] = runtime_state

    session["simulation_state"] = simulation_state
    session["setup_payload"] = next_setup
    session["runtime_state"] = runtime_state

    manifest = _safe_dict(session.get("manifest"))
    manifest["updated_at"] = _utc_now_iso()
    session["manifest"] = manifest

    runtime_state.setdefault("llm_records", [])
    runtime_state.setdefault("llm_records_index", {})

    # FIX: prevent [-0:] returning entire queue when no updates were emitted
    queue = _safe_list(runtime_state.get("ambient_queue"))
    emitted_count = len(narrated_updates) if narrated_updates else len(coalesced)
    if emitted_count > 0:
        final_updates = queue[-emitted_count:]
    else:
        final_updates = []
    idle_record = {
        "type": "idle_tick",
        "tick": current_tick,
        "reason": reason,
        "updates": final_updates,
        "latest_seq": int(runtime_state.get("ambient_seq", 0) or 0),
        "idle_streak": int(runtime_state.get("idle_streak", 0) or 0),
        # Phase 8: capture initiative and event decisions for replay
        "initiative_candidate": _safe_dict(selected_initiative) if selected_initiative else None,
        "scene_candidate": _safe_dict(selected_scene) if selected_scene else None,
        "scene_beats_emitted": len(scene_beats) if scene_beats else 0,
        "continuing_scene": _safe_dict(continuing_scene) if continuing_scene else None,
        "world_events_emitted": len(event_updates) if event_updates else 0,
        "dialogue_candidate": _safe_dict(selected_dialogue) if selected_dialogue else None,
    }
    runtime_state["llm_records"].append(idle_record)
    runtime_state["llm_records_index"][idle_capture_key] = idle_record
    session["runtime_state"] = runtime_state

    # Update known NPC list after idle tick
    runtime_state = _update_known_npc_ids(runtime_state, after_state)

    # Record debug trace
    runtime_state["idle_debug_trace"] = debug_trace

    # Update recent world event rows for frontend
    try:
        from app.rpg.analytics.world_events import build_incremental_world_event_rows
        new_rows = build_incremental_world_event_rows(after_state, runtime_state, debug_trace)

        print(
            "DEBUG WORLD EVENTS MERGE new_rows =",
            {
                "count": len(_safe_list(new_rows)),
                "event_ids": [_safe_str(r.get("event_id")) for r in _safe_list(new_rows)],
            },
        )

        existing_rows = _safe_list(runtime_state.get("recent_world_event_rows"))

        print(
            "DEBUG WORLD EVENTS MERGE existing_rows_before =",
            {
                "count": len(_safe_list(existing_rows)),
                "event_ids": [_safe_str(r.get("event_id")) for r in _safe_list(existing_rows)],
            },
        )

        merged_rows = existing_rows + new_rows
        deduped_rows: List[Dict[str, Any]] = []
        seen_event_ids = set()
        for row in reversed(merged_rows):
            row = _safe_dict(row)
            event_id = _safe_str(row.get("event_id")).strip()
            if not event_id:
                event_id = f"recent_world_event:{len(deduped_rows)}"
                row["event_id"] = event_id
            if event_id in seen_event_ids:
                continue
            seen_event_ids.add(event_id)
            deduped_rows.append(row)
        deduped_rows.reverse()
        runtime_state["recent_world_event_rows"] = deduped_rows[-_MAX_RECENT_WORLD_EVENT_ROWS:]

        print(
            "DEBUG WORLD EVENTS MERGE final_rows =",
            {
                "count": len(_safe_list(runtime_state.get("recent_world_event_rows"))),
                "event_ids": [
                    _safe_str(r.get("event_id"))
                    for r in _safe_list(runtime_state.get("recent_world_event_rows"))
                ],
            },
        )

    except (ImportError, AttributeError):
        pass  # world_events module may not be available yet

    session["runtime_state"] = runtime_state

    # Force authoritative tick persistence
    after_state = _safe_dict(after_state)
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)

    authoritative_tick = (
        int(after_state.get("tick", 0) or 0)
        or int(after_state.get("current_tick", 0) or 0)
        or int(simulation_state.get("tick", 0) or 0)
        or int(simulation_state.get("current_tick", 0) or 0)
        or int(runtime_state.get("tick", 0) or 0)
    )

    simulation_state["tick"] = authoritative_tick
    simulation_state["current_tick"] = authoritative_tick
    simulation_state = _refresh_active_interactions_for_tick(simulation_state, authoritative_tick)
    simulation_state = _expire_stale_active_interactions(simulation_state, authoritative_tick)
    runtime_state["tick"] = authoritative_tick
    simulation_state, runtime_state = _run_npc_reaction_pass(
        simulation_state,
        runtime_state,
        authoritative_tick,
    )
    runtime_state = _clear_stale_last_player_action(runtime_state, authoritative_tick)

    session["simulation_state"] = simulation_state
    session["runtime_state"] = runtime_state

    # Debug prints
    print("END-IDLE authoritative_tick =", authoritative_tick)
    print("END-IDLE simulation_state.tick =", simulation_state.get("tick"))
    print("END-IDLE simulation_state.current_tick =", simulation_state.get("current_tick"))
    print("END-IDLE runtime_state.tick =", runtime_state.get("tick"))

    return {
        "ok": True,
        "session": session,
        "updates": final_updates,
        "latest_seq": int(runtime_state.get("ambient_seq", 0) or 0),
        "idle_streak": int(runtime_state.get("idle_streak", 0) or 0),
        "idle_debug_trace": _safe_dict(runtime_state.get("idle_debug_trace")),
        "idle_seconds": idle_seconds,
        "idle_gate_open": idle_gate_open,
        "settings": settings,
    }



_RECAP_LOW_VALUE_PHRASES = (
    "watches the situation carefully",
    "checks in with",
    "waits nearby",
    "remains nearby",
    "observes quietly",
    "stands by",
    "keeps watch",
    "lingers nearby",
    "looks on",
)


def _is_meaningful_recap_text(text):
    text = _safe_str(text).strip().lower()
    if not text:
        return False
    for phrase in _RECAP_LOW_VALUE_PHRASES:
        if phrase in text:
            return False
    return True


def _score_recap_text(text):
    text = _safe_str(text).strip().lower()
    if not text:
        return -100

    score = 0

    strong_terms = (
        "attacks", "wounded", "killed", "defeated", "escapes", "stolen",
        "discovers", "reveals", "unlocked", "opens", "collapses", "burns",
        "ambush", "fight", "combat", "injured", "dies", "arrested",
        "quest", "objective", "rumor", "secret", "clue", "evidence",
        "arrives", "departs", "missing", "threat", "danger", "pressure",
        "faction", "betray", "alliance", "consequence", "changed",
        "moved", "travel", "entered", "left", "scene", "location",
    )

    medium_terms = (
        "argues", "warns", "demands", "refuses", "agrees", "offers",
        "searches", "investigates", "hides", "prepares", "gathers",
        "reports", "announces", "tracks", "follows", "negotiates",
    )

    for token in strong_terms:
        if token in text:
            score += 5

    for token in medium_terms:
        if token in text:
            score += 2

    for phrase in _RECAP_LOW_VALUE_PHRASES:
        if phrase in text:
            score -= 10

    return score


def _choose_meaningful_recap_lines(items, limit=5):
    candidates = []
    seen = set()

    for item in _safe_list(items):
        label = ""
        if isinstance(item, dict):
            label = (
                _safe_str(item.get("summary")) or
                _safe_str(item.get("description")) or
                _safe_str(item.get("title")) or
                _safe_str(item.get("name")) or
                _safe_str(item.get("label")) or
                _safe_str(item.get("text"))
            )
        else:
            label = _safe_str(item)

        label = label.strip()
        if not label or label in seen:
            continue
        seen.add(label)

        if not _is_meaningful_recap_text(label):
            continue

        candidates.append((_score_recap_text(label), label))

    candidates.sort(key=lambda pair: (-pair[0], pair[1]))
    return [label for _, label in candidates[:limit]]


def _coerce_recap_labels(items, limit=5):
    out = []
    seen = set()
    for item in _safe_list(items):
        label = ""
        if isinstance(item, dict):
            label = (
                _safe_str(item.get("summary")) or
                _safe_str(item.get("description")) or
                _safe_str(item.get("title")) or
                _safe_str(item.get("name")) or
                _safe_str(item.get("label")) or
                _safe_str(item.get("text"))
            )
        else:
            label = _safe_str(item)
        label = label.strip()
        if label and label not in seen:
            seen.add(label)
            out.append(label)
        if len(out) >= limit:
            break
    return out


def _build_player_facing_resume_summary(scene_title, location_name, excess_ticks, has_sections):
    scene_title = _safe_str(scene_title).strip()
    location_name = _safe_str(location_name).strip()
    moments = int(excess_ticks or 0)

    if has_sections:
        if scene_title and location_name:
            return (
                f"While you were away, the world shifted around {location_name} "
                f"and the situation in {scene_title} moved forward over {moments} ticks."
            )
        if scene_title:
            return f"While you were away, the situation in {scene_title} moved forward over {moments} ticks."
        if location_name:
            return f"While you were away, events developed around {location_name} over {moments} ticks."
        return f"While you were away, the world changed in meaningful ways over {moments} ticks."

    # No meaningful sections survived filtering, so keep the summary honest.
    if scene_title and location_name:
        return f"While you were away, {location_name} remained active and the situation in {scene_title} continued to evolve."
    if scene_title:
        return f"While you were away, the situation in {scene_title} continued to evolve."
    return "While you were away, time passed and nearby actors continued their routines."


def _build_resume_fallback_recap(session, runtime_state, excess_ticks):
    session = _safe_dict(session)
    runtime_state = _safe_dict(runtime_state)
    simulation_state = _safe_dict(session.get("simulation_state"))

    scene = _safe_dict(session.get("scene"))
    world = _safe_dict(session.get("world"))
    npcs = _safe_list(session.get("npcs"))

    scene_title = (
        _safe_str(scene.get("title")) or
        _safe_str(simulation_state.get("scene_title")) or
        _safe_str(world.get("title")) or
        "The world moved on in your absence."
    )
    location_name = (
        _safe_str(scene.get("location")) or
        _safe_str(simulation_state.get("location_name")) or
        _safe_str(world.get("setting"))
    )

    npc_updates = _coerce_recap_labels(npcs, limit=4)
    director_activity = _coerce_recap_labels(runtime_state.get("director_log"), limit=4)

    has_sections = bool(npc_updates or director_activity)

    recap = {
        "kind": "world_advance_recap",
        "summary": _build_player_facing_resume_summary(
            scene_title,
            location_name,
            excess_ticks,
            has_sections,
        ),
        "additional_moments": int(excess_ticks or 0),
        "world_events": [],
        "consequences": [],
        "threads": [],
        "npc_updates": npc_updates,
        "director_activity": director_activity,
    }

    return recap


def _recap_has_renderable_content(recap):
    recap = _safe_dict(recap)
    if not recap:
        return False
    for key in ("world_events", "consequences", "threads", "npc_updates", "director_activity"):
        if _safe_list(recap.get(key)):
            return True
    return bool(_safe_str(recap.get("summary")))


def _make_dialogue_update_from_candidate(
    candidate: Dict[str, Any],
    session_context: Dict[str, Any],
) -> Dict[str, Any]:
    req = build_ambient_dialogue_request(candidate, session_context)
    return {
        "tick": int(req.get("tick", 0) or 0),
        "kind": _safe_str(req.get("kind") or "npc_to_player"),
        "priority": float(_safe_dict(candidate).get("salience", 0.0) or 0.0),
        "interrupt": bool(req.get("interrupt")),
        "speaker_id": _safe_str(req.get("speaker_id")),
        "speaker_name": _safe_str(req.get("speaker_name")),
        "target_id": _safe_str(req.get("target_id")),
        "target_name": _safe_str(req.get("target_name")),
        "scene_id": _safe_str(req.get("scene_id")),
        "location_id": _safe_str(req.get("location_id")),
        "text": _safe_str(req.get("text_hint")),
        "structured": {
            "emotion": _safe_str(req.get("emotion")),
            "lane": _safe_str(candidate.get("lane") or "idle"),
            "world_context": _safe_str(req.get("world_context")),
        },
        "source_event_ids": [],
        "source": "dialogue",
        "created_at": _utc_now_iso(),
        "lane": _safe_str(candidate.get("lane") or "idle"),
    }


def _make_initiative_update_from_candidate(
    candidate: Dict[str, Any],
) -> Dict[str, Any]:
    """Convert an NPC initiative candidate into an ambient update."""
    candidate = _safe_dict(candidate)
    kind = _safe_str(candidate.get("kind") or "npc_to_player")
    speaker_name = _safe_str(candidate.get("speaker_name"))
    reason = _safe_str(candidate.get("reason"))
    action_intent = _safe_str(candidate.get("action_intent"))

    # Build default text from candidate metadata
    text = _safe_str(candidate.get("text_hint"))
    if not text:
        if kind == "quest_prompt":
            text = f"{speaker_name} has something important to share about your quest."
        elif kind == "recruitment_offer":
            text = f"{speaker_name} approaches with an offer."
        elif kind == "plea_for_help":
            text = f"{speaker_name} urgently needs your help."
        elif kind in ("taunt", "demand"):
            text = f"{speaker_name} confronts you."
        elif kind == "warning":
            text = f"{speaker_name} warns you of danger."
        elif kind == "companion_comment":
            reason = _safe_str(_safe_dict(candidate.get("structured")).get("reason") or candidate.get("reason"))
            if reason == "companion_idle_presence":
                text = f"{speaker_name} glances around, then leans closer to you."
            else:
                text = f"{speaker_name} murmurs a quick thought under their breath."
        else:
            text = f"{speaker_name} wants your attention."

    return {
        "tick": int(candidate.get("tick", 0) or 0),
        "kind": kind,
        "priority": float(candidate.get("salience", 0.0) or 0.0),
        "interrupt": bool(candidate.get("interrupt")),
        "speaker_id": _safe_str(candidate.get("speaker_id")),
        "speaker_name": speaker_name,
        "target_id": _safe_str(candidate.get("target_id")),
        "target_name": _safe_str(candidate.get("target_name")),
        "scene_id": "",
        "location_id": _safe_str(candidate.get("location_id")),
        "text": text,
        "structured": {
            "reason": reason,
            "action_intent": action_intent,
        },
        "source_event_ids": [],
        "source": "initiative",
        "created_at": _utc_now_iso(),
    }


def _make_scene_update_from_beat(beat: Dict[str, Any]) -> Dict[str, Any]:
    beat = _safe_dict(beat)
    return {
        "tick": 0,
        "kind": _safe_str(beat.get("kind") or "npc_to_npc"),
        "priority": float(beat.get("priority", 0.0) or 0.0),
        "interrupt": False,
        "speaker_id": _safe_str(beat.get("speaker_id")),
        "speaker_name": _safe_str(beat.get("speaker_name")),
        "target_id": _safe_str(beat.get("target_id")),
        "target_name": _safe_str(beat.get("target_name")),
        "scene_id": _safe_str(beat.get("scene_id")),
        "location_id": _safe_str(beat.get("location_id")),
        "text": _safe_str(beat.get("text_hint")),
        "structured": {
            "reason": _safe_str(beat.get("reason")),
            "scene_id": _safe_str(beat.get("scene_id")),
            "scene_kind": _safe_str(beat.get("scene_kind")),
            "beat_index": int(beat.get("beat_index", 0) or 0),
        },
        "source": "scene_weaver",
    }


def _apply_ambient_narration_and_delivery(
    *,
    session: Dict[str, Any],
    updates: List[Dict[str, Any]],
    after_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    idle_capture_key: str,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    session = _copy_dict(session)
    runtime_state = _copy_dict(runtime_state)
    current_scene = _safe_dict(runtime_state.get("current_scene"))
    narrated_updates: List[Dict[str, Any]] = []

    llm_gateway = None
    try:
        from app.shared import get_provider
        llm_gateway = get_provider()
    except Exception:
        llm_gateway = None

    runtime_state.setdefault("llm_records", [])
    runtime_state.setdefault("llm_records_index", {})

    # Defensive contract: this helper expects already-enqueued updates
    # so that seq/ambient_id are stable for capture and replacement.
    for idx, update in enumerate(updates):
        update = _safe_dict(update)
        if int(update.get("seq", 0) or 0) <= 0 or not _safe_str(update.get("ambient_id")):
            raise ValueError(
                f"_apply_ambient_narration_and_delivery requires enqueued updates with seq/ambient_id (index={idx})"
            )

    for idx, update in enumerate(updates):
        update = _copy_dict(update)
        narration = narrate_ambient_update(
            ambient_update=update,
            simulation_state=after_state,
            current_scene=current_scene,
            llm_gateway=llm_gateway,
        )
        update["text"] = _safe_str(narration.get("text"))
        update["speaker_turns"] = _safe_list(narration.get("speaker_turns"))
        update["narration"] = {
            "used_app_llm": bool(narration.get("used_app_llm")),
            "raw_llm_narrative": _safe_str(narration.get("raw_llm_narrative")),
            "structured": _safe_dict(narration.get("structured")),
        }
        update["delivery"] = classify_ambient_delivery(session, update, is_typing=False)

        if update["delivery"] == "interrupt":
            session = record_interrupt(session, update)
            runtime_state = _safe_dict(session.get("runtime_state"))

        capture_record = {
            "type": "ambient_narration",
            "idle_capture_key": idle_capture_key,
            "index": idx,
            "ambient_id": _safe_str(update.get("ambient_id")),
            "kind": _safe_str(update.get("kind")),
            "text": _safe_str(update.get("text")),
            "speaker_turns": _safe_list(update.get("speaker_turns")),
            "delivery": _safe_str(update.get("delivery")),
            "narration": _safe_dict(update.get("narration")),
        }
        runtime_state["llm_records"].append(capture_record)
        runtime_state["llm_records_index"][f"{idle_capture_key}:ambient:{idx}"] = capture_record
        narrated_updates.append(update)

    return narrated_updates, runtime_state


def apply_idle_tick(session_id: str, *, reason: str = "heartbeat") -> Dict[str, Any]:
    session = load_runtime_session(session_id)
    if session is None:
        return {"ok": False, "error": "session_not_found"}

    session = _copy_dict(session)
    result = _apply_idle_tick_to_session(session, reason=reason)
    if not result.get("ok"):
        return result

    session = save_runtime_session(_safe_dict(result.get("session")))
    runtime_state = _safe_dict(session.get("runtime_state"))

    return {
        "ok": True,
        "session": session,
        "updates": _safe_list(result.get("updates")),
        "latest_seq": int(runtime_state.get("ambient_seq", 0) or 0),
        "idle_streak": int(runtime_state.get("idle_streak", 0) or 0),
        "idle_debug_trace": result.get("idle_debug_trace", {}),
        "idle_seconds": result.get("idle_seconds", 0),
        "idle_gate_open": result.get("idle_gate_open", False),
        "settings": result.get("settings", {}),
    }


def apply_idle_ticks(session_id: str, count: int, *, reason: str = "heartbeat") -> Dict[str, Any]:
    """Apply multiple idle ticks, clamped to _MAX_IDLE_TICKS_PER_REQUEST.

    Coalesces results across ticks in memory and saves once at the end.
    """
    count = max(1, min(int(count), _MAX_IDLE_TICKS_PER_REQUEST))
    session = load_runtime_session(session_id)
    if session is None:
        return {"ok": False, "error": "session_not_found"}

    session = _copy_dict(session)
    all_updates: List[Dict[str, Any]] = []
    ticks_applied = 0

    for _ in range(count):
        result = _apply_idle_tick_to_session(session, reason=reason)
        if not result.get("ok"):
            if ticks_applied == 0:
                return result
            break
        session = _safe_dict(result.get("session"))
        all_updates.extend(_safe_list(result.get("updates")))
        ticks_applied += 1

    session = save_runtime_session(session)
    runtime_state = _safe_dict(session.get("runtime_state"))
    return {
        "ok": True,
        "session": session,
        "updates": all_updates,
        "latest_seq": int(runtime_state.get("ambient_seq", 0) or 0),
        "idle_streak": int(runtime_state.get("idle_streak", 0) or 0),
        "idle_debug_trace": result.get("idle_debug_trace", {}),
        "idle_seconds": result.get("idle_seconds", 0),
        "idle_gate_open": result.get("idle_gate_open", False),
        "settings": result.get("settings", {}),
    }


def apply_resume_catchup(session_id: str, *, elapsed_seconds: int = 0) -> Dict[str, Any]:
    """Apply bounded catch-up ticks on session resume.
    
    Converts elapsed time to capped idle ticks. If excess ticks would be
    generated, summarizes them into a single catch-up ambient update.
    """
    session = load_runtime_session(session_id)
    if session is None:
        return {"ok": False, "error": "session_not_found"}
    
    runtime_state = ensure_ambient_runtime_state(_safe_dict(session.get("runtime_state")))
    
    # Compute ticks from elapsed time (1 tick per ~5 seconds of real time)
    raw_ticks = max(0, elapsed_seconds // 5)
    capped_ticks = min(raw_ticks, _MAX_RESUME_CATCHUP_TICKS)
    excess_ticks = max(0, raw_ticks - capped_ticks)
    
    if capped_ticks == 0:
        return {
            "ok": True,
            "session": session,
            "updates": [],
            "latest_seq": int(runtime_state.get("ambient_seq", 0) or 0),
            "ticks_applied": 0,
            "excess_summarized": 0,
        }
    
    # Apply the capped ticks
    result = apply_idle_ticks(session_id, capped_ticks, reason="resume_catchup")
    if not result.get("ok"):
        return result

    excess_ticks = int(result.get("excess_summarized", 0) or 0)
    ticks_applied = int(result.get("ticks_applied", 0) or 0)
    all_updates = _safe_list(result.get("updates"))
    recap = {}

    # If the world advanced at all, build a resume recap
    if ticks_applied > 0:
        session = _safe_dict(result.get("session"))
        runtime_state = ensure_ambient_runtime_state(_safe_dict(session.get("runtime_state")))

        # Preserve bounded resume metadata for the richer recap payload, but do
        # not enqueue the old one-line system_summary update. The frontend will
        # render the recap block from world_advance_recap instead.
        runtime_state["resume_advance_ticks"] = ticks_applied
        session["runtime_state"] = runtime_state
        session = save_runtime_session(session)

        # 🔥 BUILD RECAP (THIS WAS MISSING)
        simulation_state = _safe_dict(session.get("simulation_state"))

        print("DEBUG SIM STATE recent_events =", simulation_state.get("recent_events"))
        print("DEBUG SIM STATE recent_consequences =", simulation_state.get("recent_consequences"))
        print("DEBUG SIM STATE active_threads =", simulation_state.get("active_threads"))
        print("DEBUG SIM STATE npc_states =", simulation_state.get("npc_states"))

        recap = _build_world_advance_recap(
            simulation_state,
            runtime_state,
            {
                "advance_ticks": ticks_applied,
                "summary": "",
                "scene_title": _safe_str(simulation_state.get("scene_title")),
                "location_name": _safe_str(simulation_state.get("location_name")),
            }
        )

        if not _recap_has_renderable_content(recap):
            recap = _build_resume_fallback_recap(session, runtime_state, ticks_applied)

        result["world_advance_recap"] = recap
        print("DEBUG BUILT RECAP:", recap)

    response = {
        "ok": True,
        "session": session if ticks_applied > 0 else _safe_dict(result.get("session")),
        "updates": all_updates,
        "latest_seq": int(result.get("latest_seq", 0) or 0),
        "ticks_applied": ticks_applied,
        "excess_summarized": excess_ticks,
        "world_advance_recap": _safe_dict(recap) if ticks_applied > 0 else _safe_dict(result.get("world_advance_recap")),
    }

    return response