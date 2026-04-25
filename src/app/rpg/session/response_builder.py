from __future__ import annotations

from typing import Any, Callable, Dict, List

from app.rpg.memory.dialogue_context import (
    build_dialogue_memory_context,
    build_llm_memory_prompt_block,
)
from app.rpg.presentation import (
    build_runtime_presentation_payload,
    build_scene_presentation_payload,
)
from app.rpg.session.state_normalization import _safe_dict, _safe_list, _safe_str


def _first_dict(*values):
    for value in values:
        value = _safe_dict(value)
        if value:
            return value
    return {}


def _first_list(*values):
    for value in values:
        value = _safe_list(value)
        if value:
            return value
    return []


def build_turn_payload(
    session: Dict[str, Any],
    narration_result: Dict[str, Any],
    summary: List[str],
    *,
    build_transaction_menus_for_state: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
) -> Dict[str, Any]:
    session = _safe_dict(session)
    simulation_state = _safe_dict(session.get("simulation_state"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    current_scene = _safe_dict(runtime_state.get("current_scene"))
    memory_context = build_dialogue_memory_context(
        simulation_state,
        actor_id="player",
    )
    player_state = _safe_dict(simulation_state.get("player_state"))
    last_turn = _safe_dict(runtime_state.get("last_turn_result"))
    inventory_state = _safe_dict(player_state.get("inventory_state"))
    equipment = _safe_dict(inventory_state.get("equipment"))
    transaction_menus = build_transaction_menus_for_state(simulation_state, runtime_state)

    return {
        "success": True,
        "session_id": _safe_str(_safe_dict(session.get("manifest")).get("id")),
        "narration": _safe_str(narration_result.get("narrative") or current_scene.get("summary")),
        "choices": _safe_list(narration_result.get("choices")),
        "npcs": _safe_list(runtime_state.get("npcs")),
        "player": {
            "stats": _safe_dict(player_state.get("stats")),
            "skills": _safe_dict(player_state.get("skills")),
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
        "player_level": int(player_state.get("level", 1) or 1),
        "player_xp": int(player_state.get("xp", 0) or 0),
        "player_skills": _safe_dict(player_state.get("skills")),
        "level_up": bool(last_turn.get("level_up")),
        "skill_level_ups": _safe_list(last_turn.get("skill_level_ups")),
        "combat_result": _safe_dict(last_turn.get("combat_result")),
        "xp_result": _safe_dict(last_turn.get("xp_result")),
        "resource_changes": _safe_dict(last_turn.get("resource_changes")),
        "player_resources": _safe_dict(last_turn.get("player_resources")),
        "effect_result": _safe_dict(last_turn.get("effect_result")),
        "transaction_menus": transaction_menus,
    }



def build_apply_turn_response(authoritative_result: Dict[str, Any]) -> Dict[str, Any]:
    authoritative_result = _safe_dict(authoritative_result)
    authoritative = _safe_dict(authoritative_result.get("authoritative"))
    turn_contract = _safe_dict(authoritative.get("turn_contract"))
    result_sub = _safe_dict(authoritative_result.get("result"))
    narration = result_sub.get("narration")
    if narration is None:
        narration = authoritative.get("deterministic_fallback_narration")
    raw_llm_narrative = result_sub.get("raw_llm_narrative")
    if raw_llm_narrative is None:
        raw_llm_narrative = ""
    used_llm = result_sub.get("used_llm")
    if used_llm is None:
        used_llm = False
    narration_status = result_sub.get("narration_status")
    if narration_status is None:
        narration_status = "queued"

    result_payload = {
        "turn_id": authoritative.get("turn_id"),
        "tick": authoritative.get("tick"),
        "resolved_result": authoritative.get("resolved_result"),
        "combat_result": authoritative.get("combat_result"),
        "xp_result": authoritative.get("xp_result"),
        "skill_xp_result": authoritative.get("skill_xp_result"),
        "level_up": authoritative.get("level_up"),
        "skill_level_ups": authoritative.get("skill_level_ups"),
        "summary": authoritative.get("summary"),
        "presentation": authoritative.get("presentation"),
        "response_length": authoritative.get("response_length"),
        "narration": narration,
        "raw_llm_narrative": raw_llm_narrative,
        "used_llm": used_llm,
        "narration_status": narration_status,
        "narration_debug": _safe_dict(result_sub.get("narration_debug")),
        "living_world_debug": _safe_dict(_safe_dict(authoritative.get("resolved_result")).get("living_world_debug")),
        "memory_state": _safe_dict(_safe_dict(authoritative.get("resolved_result")).get("memory_state")),
        "relationship_state": _safe_dict(_safe_dict(authoritative.get("resolved_result")).get("relationship_state")),
        "npc_emotion_state": _safe_dict(_safe_dict(authoritative.get("resolved_result")).get("npc_emotion_state")),
        "service_offer_state": _safe_dict(_safe_dict(authoritative.get("resolved_result")).get("service_offer_state")),
        "recalled_service_memories": _safe_list(_safe_dict(authoritative.get("resolved_result")).get("recalled_service_memories")),
        "service_memory_recall_debug": _safe_dict(_safe_dict(authoritative.get("resolved_result")).get("service_memory_recall_debug")),
    }

    narration_debug = _safe_dict(result_payload.get("narration_debug"))
    resolved_result = _safe_dict(
        result_payload.get("resolved_result")
        or result_payload.get("resolved_action")
        or result_payload
    )
    service_application = _safe_dict(resolved_result.get("service_application"))

    result_payload["living_world_debug"] = _first_dict(
        result_payload.get("living_world_debug"),
        resolved_result.get("living_world_debug"),
        service_application.get("living_world_debug"),
        {
            "memory_entry": _first_dict(
                resolved_result.get("memory_entry"),
                service_application.get("memory_entry"),
            ),
            "social_effects": _first_dict(
                resolved_result.get("social_effects"),
                service_application.get("social_effects"),
            ),
            "stock_update": _first_dict(
                resolved_result.get("stock_update"),
                service_application.get("stock_update"),
            ),
        },
    )
    result_payload["memory_state"] = _first_dict(
        result_payload.get("memory_state"),
        resolved_result.get("memory_state"),
    )
    result_payload["relationship_state"] = _first_dict(
        result_payload.get("relationship_state"),
        resolved_result.get("resolved_result"),
    )
    result_payload["npc_emotion_state"] = _first_dict(
        result_payload.get("npc_emotion_state"),
        resolved_result.get("npc_emotion_state"),
    )
    result_payload["service_offer_state"] = _first_dict(
        result_payload.get("service_offer_state"),
        resolved_result.get("service_offer_state"),
    )
    result_payload["recalled_service_memories"] = _first_list(
        result_payload.get("recalled_service_memories"),
        resolved_result.get("recalled_service_memories"),
        narration_debug.get("recalled_service_memories"),
    )
    result_payload["service_memory_recall_debug"] = _first_dict(
        result_payload.get("service_memory_recall_debug"),
        resolved_result.get("service_memory_recall_debug"),
        narration_debug.get("service_memory_recall_debug"),
    )

    return {
        "ok": True,
        "session": authoritative_result.get("session"),
        "turn_contract": turn_contract,
        "result": result_payload,
    }
