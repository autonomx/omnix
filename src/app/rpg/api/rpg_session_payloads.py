"""Shared payload helpers for RPG session API routes."""
from __future__ import annotations

import json
from typing import Any, Dict

from app.rpg.session.ambient_builder import get_pending_ambient_updates
from app.rpg.social.conversation_presentation import build_conversation_payload


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _normalize_turn_request(data: Dict[str, Any]) -> Dict[str, Any]:
    data = _safe_dict(data)
    player_input = _safe_str(data.get("input") or data.get("player_input")).strip()
    action = _safe_dict(data.get("action"))

    if not action and player_input.startswith("{"):
        try:
            parsed = json.loads(player_input)
            action = _safe_dict(parsed)
        except Exception:
            action = {}

    if action and not player_input:
        action_type = _safe_str(action.get("action_type") or action.get("action")).strip().lower()
        npc_name = _safe_str(action.get("npc_name")).strip()
        npc_id = _safe_str(action.get("npc_id") or action.get("target_id")).strip()
        label = npc_name or npc_id or "them"
        if action_type == "talk":
            player_input = f"Talk to {label}"
        elif action_type == "threaten":
            player_input = f"Threaten {label}"
        elif action_type == "persuade":
            player_input = f"Talk to {label}"
        elif action_type == "intimidate":
            player_input = f"Threaten {label}"
        else:
            player_input = action_type.replace("_", " ").strip()

    return {
        "session_id": _safe_str(data.get("session_id")).strip(),
        "player_input": player_input,
        "action": action,
        "performance": _safe_dict(data.get("performance")),
        "runtime_settings": _safe_dict(data.get("runtime_settings")),
    }


def _deep_merge_dict(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(_safe_dict(base))
    for key, value in _safe_dict(updates).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(_safe_dict(merged.get(key)), value)
        else:
            merged[key] = value
    return merged


def _build_turn_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    """Build the canonical turn response payload from an apply_turn result."""
    raw_payload = _safe_dict(result.get("payload"))
    session = _safe_dict(result.get("session"))
    sim = _safe_dict(session.get("simulation_state"))
    player_state = _safe_dict(sim.get("player_state"))
    stats = _safe_dict(player_state.get("stats"))
    skills = _safe_dict(player_state.get("skills"))
    inventory_state = _safe_dict(player_state.get("inventory_state"))
    equipment = _safe_dict(inventory_state.get("equipment"))

    runtime_state = _safe_dict(session.get("runtime_state"))
    scene_state = _safe_dict(runtime_state.get("current_scene")) or _safe_dict(sim.get("current_scene"))
    memory = _safe_dict(sim.get("memory"))

    payload: Dict[str, Any] = {
        "success": True,
        "session_id": _safe_str(raw_payload.get("session_id") or session.get("session_id")),
        "title": _safe_str(raw_payload.get("title")),
        "opening": _safe_str(raw_payload.get("opening")),
        "narration": _safe_str(raw_payload.get("narration")),
        "choices": _safe_list(raw_payload.get("choices")),
        "player": {
            "stats": stats,
            "skills": skills,
            "level": int(player_state.get("level", 1) or 1),
            "xp": int(player_state.get("xp", 0) or 0),
            "xp_to_next": int(player_state.get("xp_to_next", 0) or 0),
            "inventory_state": inventory_state,
            "equipment": equipment,
            "currency": _safe_dict(inventory_state.get("currency")),
            "inventory_items": _safe_list(inventory_state.get("items")),
            "nearby_npc_ids": _safe_list(player_state.get("nearby_npc_ids")),
            "available_checks": _safe_list(player_state.get("available_checks")),
        },
        "nearby_npcs": _safe_list(raw_payload.get("nearby_npcs") or sim.get("nearby_npcs")),
        "known_npcs": _safe_list(raw_payload.get("known_npcs") or sim.get("known_npcs")),
        "scene": {
            "scene_id": _safe_str(scene_state.get("scene_id")),
            "items": _safe_list(scene_state.get("items")),
            "available_checks": _safe_list(scene_state.get("available_checks")),
            "present_npc_ids": _safe_list(scene_state.get("present_npc_ids")),
        },
        "memory_summary": {
            "important_memory": _safe_list(memory.get("important_memory")),
            "recent_memory": _safe_list(memory.get("recent_memory")),
            "recent_world_events": _safe_list(memory.get("recent_world_events")),
        },
        "combat_result": raw_payload.get("combat_result"),
        "xp_result": raw_payload.get("xp_result"),
        "skill_xp_result": raw_payload.get("skill_xp_result"),
        "level_up": _safe_list(raw_payload.get("level_up")),
        "skill_level_ups": _safe_list(raw_payload.get("skill_level_ups")),
        "resource_changes": _safe_dict(raw_payload.get("resource_changes")),
        "player_resources": _safe_dict(raw_payload.get("player_resources")),
        "effect_result": _safe_dict(raw_payload.get("effect_result")),
        "action_metadata": _safe_dict(raw_payload.get("action_metadata")),
        "structured_narration": _safe_dict(raw_payload.get("structured_narration")),
        "speaker_turns": _safe_list(raw_payload.get("speaker_turns")),
        "used_app_llm": bool(raw_payload.get("used_app_llm")),
        "gateway_available": bool(raw_payload.get("gateway_available")),
        "raw_llm_narrative": _safe_str(raw_payload.get("raw_llm_narrative")),
        "grounding_validation": _safe_dict(raw_payload.get("grounding_validation")),
        "grounding_fallback": bool(raw_payload.get("grounding_fallback")),
        "settings": _safe_dict(
            raw_payload.get("settings")
            or runtime_state.get("runtime_settings")
            or runtime_state.get("settings")
        ),
        "response_length": _safe_str(raw_payload.get("response_length", "short")),
        "presentation": _safe_dict(raw_payload.get("presentation")),
        "transaction_menus": _safe_list(raw_payload.get("transaction_menus")),
        "ambient_updates": _safe_list(
            get_pending_ambient_updates(session, after_seq=0, limit=8)
        ),
        "latest_ambient_seq": int(runtime_state.get("ambient_seq", 0) or 0),
        "unread_ambient_count": max(
            0,
            int(runtime_state.get("ambient_seq", 0) or 0)
            - int(_safe_dict(runtime_state.get("subscription_state")).get("last_polled_seq", 0) or 0),
        ),
    }

    location_id = _safe_str(
        runtime_state.get("current_location_id")
        or _safe_dict(sim.get("player_state")).get("location_id")
    )
    conversation_payload = build_conversation_payload(sim, runtime_state, location_id=location_id)
    payload["active_conversations"] = conversation_payload.get("active_conversations", [])
    payload["recent_conversations"] = conversation_payload.get("recent_conversations", [])
    return payload
