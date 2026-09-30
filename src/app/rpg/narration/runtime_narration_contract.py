"""Stable compatibility facade for canonical RPG runtime narration.

The previous implementation is retained in ``runtime_narration_legacy`` as a
candidate-generation adapter. Final validation, recovery, rendering, rollout,
and publication are owned by the canonical response-generation pipeline.
"""
from __future__ import annotations

from app.rpg.narration import runtime_narration_legacy as _legacy

from app.rpg.response_generation.runtime_bridge import (
    build_runtime_narration_payload as build_runtime_narration_payload,
)


def __getattr__(name: str):
    """Delegate legacy imports to their narration implementation module."""
    try:
        return getattr(_legacy, name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc


__all__ = (
    "_legacy json logging Any Dict List select_grounded_narration_candidate NARRATION_FORMAT_VERSION _norm _safe_dict _safe_list _safe_str _build_dialogue_state_update_payload _dialogue_aware_bran_line _fallback_npc_line _known_facts_for_npc_reply _line_was_recently_used _recent_npc_lines build_deterministic_narration_payload classify_player_action infer_npc_speaker is_echo_narration CHAT_LIKE_PROVIDER_METHODS PROVIDER_CHILD_CANDIDATES PROVIDER_METHOD_CANDIDATES "
    "_ProviderChatMessage _call_provider_text _call_provider_text_with_diagnostics _candidate_debug_shape _extract_json_object_from_provider_text _extract_json_object_with_diagnostics_from_provider_text _extract_provider_text _is_runtime_narration_candidate_envelope _provider_candidates _provider_shape _public_callable_names _safe_child_objects _try_provider_call RUNTIME_NARRATION_CANDIDATE_MAX_TOKENS RUNTIME_NARRATION_SINGLE_MAX_TOKENS logger RUNTIME_NARRATION_CONTEXT_JSON_LIMIT "
    "RUNTIME_NARRATION_STATE_JSON_LIMIT RUNTIME_NARRATION_CONTRACT_JSON_LIMIT _cap_text _cap_list _compact_mapping _extract_compact_runtime_state_for_narration _extract_compact_turn_contract_for_narration _json_for_prompt _apply_grounding_to_runtime_payload _normalize_candidate_narration_payload _validate_candidate_shape _validate_parsed_provider_payload_or_parse_failure validate_narration_payload _safe_action_acknowledgement _provider_action_looks_authoritative "
    "repair_provider_narration_payload build_provider_narration_payload _runtime_narration_candidate_schema_text build_runtime_narration_payload "
).split()
