"""Split helpers for RPG world scene narration."""


from app.apps.rpg.narration.ai.world_scene_narrator_payloads import (
    json as json,
    re as re,
    traceback as traceback,
    dataclass as dataclass,
    field as field,
    Any as Any,
    Callable as Callable,
    Dict as Dict,
    List as List,
    Optional as Optional,
    normalize_grounding_settings as normalize_grounding_settings,
    select_grounded_narration_candidate as select_grounded_narration_candidate,
    build_runtime_npc_response_architecture as build_runtime_npc_response_architecture,
    build_runtime_current_turn_prompt_contract as build_runtime_current_turn_prompt_contract,
    build_runtime_presentation_guardrails_block as build_runtime_presentation_guardrails_block,
    build_encounter_view as build_encounter_view,
    logger as logger,
    _extract_llm_text as _extract_llm_text,
    _llm_text as _llm_text,
    _safe_str as _safe_str,
    _safe_dict as _safe_dict,
    _safe_list as _safe_list,
    _force_live_llm_required as _force_live_llm_required,
    _build_ambient_conversation_line as _build_ambient_conversation_line,
    _bound_text as _bound_text,
    _format_recalled_service_memories_for_prompt as _format_recalled_service_memories_for_prompt,
    _format_recalled_npc_memories_for_prompt as _format_recalled_npc_memories_for_prompt,
    _format_conversation_beat_for_prompt as _format_conversation_beat_for_prompt,
    _naturalize_service_debug_language as _naturalize_service_debug_language,
    _build_authoritative_action_line as _build_authoritative_action_line,
    _build_safe_prompt_context as _build_safe_prompt_context,
    _normalize_narration_json as _normalize_narration_json,
    _parse_llm_narration_payload as _parse_llm_narration_payload,
    _strict_narration_payload as _strict_narration_payload,
    _recent_authoritative_facts as _recent_authoritative_facts,
    _authoritative_action_text as _authoritative_action_text,
    _authoritative_reward_text as _authoritative_reward_text,
    _sanitize_narration_payload as _sanitize_narration_payload,
    _recover_narration_from_raw_text as _recover_narration_from_raw_text,
    _structured_fallback_response as _structured_fallback_response,
)


def _build_combat_facts_block(narration_context: Dict[str, Any]) -> str:
    combat_result = _safe_dict(narration_context.get("combat_result"))
    npc_combat_result = _safe_dict(narration_context.get("npc_combat_result"))
    combat_state = _safe_dict(narration_context.get("combat_state"))
    if not combat_result and not combat_state and not npc_combat_result:
        return "- none"

    parts = []
    if combat_state:
        parts.append(f"state={_safe_str(combat_state.get('phase') or 'idle')}")
    if combat_result:
        parts.append(f"hit={bool(combat_result.get('hit'))}")
        parts.append(f"damage={int(combat_result.get('damage_total', 0) or 0)}")
        parts.append(f"target_downed={bool(combat_result.get('target_downed'))}")
    if npc_combat_result:
        parts.append(f"npc_counterattack_hit={bool(npc_combat_result.get('hit'))}")
        parts.append(
            f"npc_counterattack_damage={int(npc_combat_result.get('damage_total', 0) or 0)}"
        )
    return ", ".join(parts) if parts else "- none"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

__all__ = (
    "json",
    "re",
    "traceback",
    "dataclass",
    "field",
    "Any",
    "Callable",
    "Dict",
    "List",
    "Optional",
    "normalize_grounding_settings",
    "select_grounded_narration_candidate",
    "build_runtime_npc_response_architecture",
    "build_runtime_current_turn_prompt_contract",
    "build_runtime_presentation_guardrails_block",
    "build_encounter_view",
    "logger",
    "_extract_llm_text",
    "_llm_text",
    "_safe_str",
    "_safe_dict",
    "_safe_list",
    "_force_live_llm_required",
    "_build_ambient_conversation_line",
    "_bound_text",
    "_format_recalled_service_memories_for_prompt",
    "_format_recalled_npc_memories_for_prompt",
    "_format_conversation_beat_for_prompt",
    "_naturalize_service_debug_language",
    "_build_authoritative_action_line",
    "_build_safe_prompt_context",
    "_normalize_narration_json",
    "_parse_llm_narration_payload",
    "_strict_narration_payload",
    "_recent_authoritative_facts",
    "_authoritative_action_text",
    "_authoritative_reward_text",
    "_sanitize_narration_payload",
    "_recover_narration_from_raw_text",
    "_structured_fallback_response",
    "_build_combat_facts_block",
)
