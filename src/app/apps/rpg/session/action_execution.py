from __future__ import annotations

# RPG session runtime responsibility module.
from app.apps.rpg.session.state_normalization import (
    _normalize_runtime_settings as _normalize_runtime_settings,
    _safe_dict as _safe_dict,
    _safe_str as _safe_str,
)
from app.apps.rpg.foundation.safe_values import safe_list as _safe_list
from app.apps.rpg.genesis.creator.world_player_actions import (
    ESCALATE_CONFLICT as ESCALATE_CONFLICT,
    INTERVENE_THREAD as INTERVENE_THREAD,
    SUPPORT_FACTION as SUPPORT_FACTION,
)
from app.apps.rpg.narration.presentation.visual_state import (
    ensure_visual_state as ensure_visual_state,
)
from app.apps.rpg.session.combat_intent import (
    _apply_grounded_scene_overlay as _apply_grounded_scene_overlay,
    _derive_grounded_scene_context as _derive_grounded_scene_context,
)
from app.apps.rpg.narration.presentation.speaker_cards import (
    build_nearby_npc_cards as build_nearby_npc_cards,
)
from app.apps.rpg.session.player_activity_runtime import (
    _build_transaction_menus_for_state as _build_transaction_menus_for_state,
)
from app.apps.rpg.narration.presentation.memory_inspector import (
    build_memory_ui_summary as build_memory_ui_summary,
)
from app.apps.rpg.narration.presentation.runtime_bridge_n1222 import (
    build_runtime_presentation_payload as build_runtime_presentation_payload,
)
from typing import (
    Any as Any, Dict as Dict, List as List,
)


# ── Known NPC tracking ─────────────────────────────────────────────────────


def build_frontend_bootstrap_payload(session: dict[str, Any]) -> dict[str, Any]:
    session = _safe_dict(session)
    manifest = _safe_dict(session.get("manifest"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    simulation_state = _safe_dict(session.get("simulation_state"))
    simulation_state = ensure_visual_state(simulation_state)
    npcs = _safe_list(runtime_state.get("npcs"))
    opening = _safe_str(runtime_state.get("opening"))
    turn_result = _safe_dict(session.get("turn_result"))
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

    transaction_menus = _build_transaction_menus_for_state(simulation_state, runtime_state)

    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))

    return {
        "success": True,
        "session_id": _safe_str(manifest.get("id")) or _safe_str(session.get("id")),
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
            "currency": _safe_dict(inventory_state.get("currency")),
            "inventory_items": _safe_list(inventory_state.get("items")),
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
        "resource_changes": _safe_dict(turn_result.get("resource_changes")),
        "player_resources": _safe_dict(turn_result.get("player_resources")),
        "effect_result": _safe_dict(turn_result.get("effect_result")),
        "presentation": build_runtime_presentation_payload(simulation_state),
        "visual_state": visual_state,
        "settings": _normalize_runtime_settings(_safe_dict(runtime_state.get("runtime_settings"))),
        "world_events_summary": {
            "recent_world_event_rows": _safe_list(runtime_state.get("recent_world_event_rows"))[-12:],
        },
        "grounded_scene_context": _safe_dict(runtime_state.get("grounded_scene_context")),
        "transaction_menus": transaction_menus,
        "campaign_calendar": _safe_dict(runtime_state.get("campaign_calendar")),
        "player_journal": _safe_dict(runtime_state.get("player_journal")),
    }


def _find_target_by_name(bucket: dict[str, Any], text: str) -> str:
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


def derive_player_action(simulation_state: dict[str, Any], player_input: str) -> dict[str, Any]:
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

__all__ = ["_find_target_by_name", "build_frontend_bootstrap_payload", "derive_player_action"]
