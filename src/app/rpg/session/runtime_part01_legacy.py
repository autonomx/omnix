"""Canonical RPG session runtime.

Single source of truth for:
- building a persisted session from adventure-builder startup
- loading/saving canonical sessions
- executing player turns against canonical session state
- shaping turn/bootstrap payloads for the frontend

This replaces the legacy in-memory GameSession / pipeline.py / routes.py flow.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import logging
import os
import re
import time as _time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.rpg.session.deferred_narration_guard import suppress_provider_runtime_narration
from app.rpg.session.narration_trace import (
    record_narration_trace,
    record_narration_trace_stack,
)
from app.rpg.session.turn_perf_trace import (
    record_elapsed_turn_stage,
    record_turn_perf_trace,
    record_turn_perf_trace_stack,
)

logger = logging.getLogger(__name__)


from app.rpg.interactions.resolver import (
    detect_interaction_intent,
)
from app.rpg.interactions.resolver import (
    resolve_general_interaction as resolve_general_interaction_v2,
)


def _has_pending_conversation_response(simulation_state: Dict[str, Any]) -> bool:
    thread_state = _safe_dict(simulation_state.get("conversation_thread_state"))
    pending = _safe_dict(thread_state.get("pending_player_response"))
    return bool(pending.get("thread_id") and pending.get("topic_id"))


def _interaction_visible_result_reason(general_interaction_result: Dict[str, Any]) -> str:
    general_interaction_result = _safe_dict(general_interaction_result)
    interaction = _safe_dict(general_interaction_result.get("interaction_result"))

    for key in ("inventory_result", "container_result", "repair_result", "consumable_result", "crafting_result", "merchant_result", "loot_result", "combat_result"):
        nested = _safe_dict(
            interaction.get(key)
            or general_interaction_result.get(key)
        )
        if nested and _safe_str(nested.get("reason")):
            return _safe_str(nested.get("reason"))

    if interaction and _safe_str(interaction.get("reason")):
        return _safe_str(interaction.get("reason"))

    return ""


def _replace_stale_visible_result_text(text: Any, *, visible_reason: str) -> str:
    text = _safe_str(text)
    visible_reason = _safe_str(visible_reason)
    if not visible_reason:
        return text
    if not text.strip():
        return f"Result: {visible_reason}"

    # Replace stale fallback result lines while preserving the rest of the
    # generated narration text. This catches:
    #   Result: unknown_item
    #   Result: item_not_found
    #   Result: unknown
    text = re.sub(
        r"(?im)^(\s*Result:\s*)(unknown_item|item_not_found|unknown)\s*$",
        rf"\1{visible_reason}",
        text,
    )

    # Some payloads embed the stale result mid-line.
    text = re.sub(
        r"(?i)Result:\s*(unknown_item|item_not_found|unknown)",
        f"Result: {visible_reason}",
        text,
    )

    return text


def _patch_visible_interaction_reason_into_payload_text(
    payload: Dict[str, Any],
    *,
    visible_reason: str,
) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    visible_reason = _safe_str(visible_reason)
    if not payload or not visible_reason:
        return payload

    text_keys = (
        "narration",
        "final_narration",
        "narration_preview",
        "raw_payload_narration",
        "action",
        "result",
        "summary",
        "result_summary",
        "action_result",
        "outcome",
    )

    for key in text_keys:
        if key in payload:
            payload[key] = _replace_stale_visible_result_text(
                payload.get(key),
                visible_reason=visible_reason,
            )

    return payload


def _apply_visible_interaction_reason_to_resolved_result(
    resolved_result: Dict[str, Any],
    *,
    general_interaction_result: Dict[str, Any],
) -> Dict[str, Any]:
    resolved_result = _safe_dict(resolved_result)
    visible_reason = _interaction_visible_result_reason(general_interaction_result)
    if not visible_reason:
        return resolved_result

    resolved_result["visible_interaction_reason"] = visible_reason

    stale_values = {
        "",
        "item_not_found",
        "unknown_item",
        "unknown",
        "Action: You act.",
        "You act.",
    }

    current_result = _safe_str(resolved_result.get("result"))
    current_action = _safe_str(resolved_result.get("action"))

    if current_result in stale_values:
        resolved_result["result"] = visible_reason

    if current_action in stale_values or current_action.startswith("Result: item_not_found") or current_action.startswith("Result: unknown_item"):
        resolved_result["action"] = f"Result: {visible_reason}"

    # Some report/narration paths read summary/text instead of result/action.
    for key in ("summary", "result_summary", "action_result", "outcome"):
        current = _safe_str(resolved_result.get(key))
        if current in stale_values or current.startswith("Result: item_not_found") or current.startswith("Result: unknown_item"):
            resolved_result[key] = visible_reason

    return resolved_result


def _runtime_narration_payload_is_final(payload: Dict[str, Any]) -> bool:
    payload = _safe_dict(payload)
    return (
        _safe_str(payload.get("source")) == "provider_runtime_narration"
        and bool(_safe_str(payload.get("narration")).strip())
        and not bool(payload.get("grounding_fallback"))
    )


def _normalize_visible_echo_text(value: Any) -> str:
    return re.sub(r"\W+", " ", _safe_str(value).casefold()).strip()


def _player_input_from_final_result(final_result: Dict[str, Any]) -> str:
    final_result = _safe_dict(final_result)
    nested = _safe_dict(final_result.get("result"))
    turn_contract = (
        _safe_dict(final_result.get("turn_contract"))
        or _safe_dict(nested.get("turn_contract"))
    )
    return _safe_str(
        final_result.get("player_input")
        or nested.get("player_input")
        or turn_contract.get("player_input")
        or turn_contract.get("player_action")
        or turn_contract.get("action")
    )


def _is_preservable_authoritative_narration(final_result: Dict[str, Any], narration: Any) -> bool:
    text = _safe_str(narration).strip()
    if not text:
        return False

    player_input = _player_input_from_final_result(final_result)
    if player_input and _normalize_visible_echo_text(text) == _normalize_visible_echo_text(player_input):
        return False

    lowered = text.casefold()
    blocked_fragments = (
        "result: you cannot find that object here",
        "no known route matches that destination",
        "no routes are currently available",
        "no supported semantic action",
        "no_supported_semantic_action_detected",
        "item_not_found",
        "unknown_item",
    )
    return not any(fragment in lowered for fragment in blocked_fragments)


def _accepted_combat_narration_payload(final_result: Dict[str, Any]) -> Dict[str, Any]:
    final_result = _safe_dict(final_result)
    nested = _safe_dict(final_result.get("result"))
    resolved = _safe_dict(final_result.get("resolved_result")) or _safe_dict(nested.get("resolved_result"))

    validation = (
        _safe_dict(final_result.get("combat_narration_validation"))
        or _safe_dict(nested.get("combat_narration_validation"))
        or _safe_dict(resolved.get("combat_narration_validation"))
    )
    payload = (
        _safe_dict(final_result.get("combat_narration_payload"))
        or _safe_dict(nested.get("combat_narration_payload"))
        or _safe_dict(resolved.get("combat_narration_payload"))
    )
    if validation.get("ok") is True and _safe_str(payload.get("narration")).strip():
        return payload
    return {}


def _accepted_direct_companion_presentation(final_result: Dict[str, Any]) -> Dict[str, Any]:
    final_result = _safe_dict(final_result)
    nested = _safe_dict(final_result.get("result"))
    resolved = _safe_dict(final_result.get("resolved_result")) or _safe_dict(nested.get("resolved_result"))
    direct = (
        _safe_dict(final_result.get("direct_companion_turn_result"))
        or _safe_dict(nested.get("direct_companion_turn_result"))
        or _safe_dict(resolved.get("direct_companion_turn_result"))
    )
    line = _safe_str(direct.get("line")).strip()
    if direct.get("matched") is True and line:
        return {
            "source": "direct_companion_response",
            "narration": line,
            "npc": {
                "speaker": _safe_str(direct.get("name") or direct.get("npc_id") or "Companion"),
                "line": line,
            },
        }
    return {}


def _select_final_visible_presentation(
    final_result: Dict[str, Any],
    *,
    runtime_narration_payload: Dict[str, Any],
    prior_narration: str,
    prior_npc: Dict[str, Any],
    prior_llm_called: bool,
) -> Dict[str, Any]:
    final_result = _safe_dict(final_result)
    runtime_narration_payload = _safe_dict(runtime_narration_payload)

    combat_payload = _accepted_combat_narration_payload(final_result)
    if combat_payload:
        return {
            "source": "combat_narration",
            "narration": _safe_str(combat_payload.get("narration")).strip(),
            "npc": _safe_dict(combat_payload.get("npc")),
            "llm_called": True,
            "runtime_payload_source": _safe_str(runtime_narration_payload.get("source")),
        }

    direct_companion_payload = _accepted_direct_companion_presentation(final_result)
    if direct_companion_payload:
        return {
            "source": _safe_str(direct_companion_payload.get("source")),
            "narration": _safe_str(direct_companion_payload.get("narration")).strip(),
            "npc": _safe_dict(direct_companion_payload.get("npc")),
            "llm_called": False,
            "runtime_payload_source": _safe_str(runtime_narration_payload.get("source")),
        }

    if _runtime_narration_payload_is_final(runtime_narration_payload):
        return {
            "source": "provider_runtime_narration",
            "narration": _safe_str(runtime_narration_payload.get("narration")).strip(),
            "npc": _safe_dict(runtime_narration_payload.get("npc")),
            "llm_called": True,
            "runtime_payload_source": _safe_str(runtime_narration_payload.get("source")),
        }

    if _is_preservable_authoritative_narration(final_result, prior_narration):
        return {
            "source": "authoritative_runtime_result",
            "narration": _safe_str(prior_narration).strip(),
            "npc": _safe_dict(prior_npc),
            "llm_called": bool(prior_llm_called),
            "runtime_payload_source": _safe_str(runtime_narration_payload.get("source")),
        }

    return {
        "source": _safe_str(runtime_narration_payload.get("source")) or "runtime_narration",
        "narration": _safe_str(runtime_narration_payload.get("narration")).strip(),
        "npc": _safe_dict(runtime_narration_payload.get("npc")),
        "llm_called": _safe_str(runtime_narration_payload.get("source")) == "provider_runtime_narration",
        "runtime_payload_source": _safe_str(runtime_narration_payload.get("source")),
    }


def _call_combat_narration_provider_text(prompt: str) -> str:
    """Call the app's central active LLM provider for combat narration.

    This must not hardcode Cerebras, LM Studio, OpenRouter, etc.
    It should use whichever provider the app currently marks active.
    """

    system_text = (
        "You are the RPG combat narration layer. "
        "Return only the strict JSON requested by the user prompt."
    )

    # Preferred: use the same central gateway normal RPG narration uses.
    try:
        from app.shared import chat_completion  # type: ignore

        raw = chat_completion(
            messages=[
                {"role": "system", "content": system_text},
                {"role": "user", "content": prompt},
            ],
            stream=False,
            purpose="combat_narration",
        )
        return _extract_llm_text_from_response(raw)
    except ImportError:
        pass

    # Fallback: active provider object, but still fetched from central state.
    try:
        from app.shared import get_active_provider  # type: ignore

        provider = get_active_provider()
    except Exception:
        try:
            from app.shared import get_provider  # type: ignore

            provider = get_provider()
        except Exception as exc:
            raise RuntimeError(
                f"combat_narration_active_provider_not_available:{type(exc).__name__}: {exc}"
            )

    if provider is None:
        raise RuntimeError("combat_narration_active_provider_not_available")

    provider_debug = {
        "type": type(provider).__name__,
        "module": type(provider).__module__,
        "has_chat_completion": hasattr(provider, "chat_completion"),
    }

    if not hasattr(provider, "chat_completion"):
        raise RuntimeError(
            "combat_narration_active_provider_has_no_chat_completion:"
            + json.dumps(provider_debug, ensure_ascii=False, sort_keys=True)
        )

    try:
        from app.providers.base import ChatMessage  # type: ignore

        messages = [
            ChatMessage(role="system", content=system_text),
            ChatMessage(role="user", content=prompt),
        ]
    except Exception:
        # Only use dict fallback if your active-provider gateway supports it.
        # Most app providers expect ChatMessage.
        messages = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": prompt},
        ]

    try:
        raw = provider.chat_completion(
            messages=messages,
            stream=False,
        )
    except Exception as exc:
        raise RuntimeError(
            "combat_narration_active_provider_call_failed:"
            + f"{type(exc).__name__}: {exc}:"
            + json.dumps(provider_debug, ensure_ascii=False, sort_keys=True)
        )

    return _extract_llm_text_from_response(raw)


def _extract_llm_text_from_response(raw: Any) -> str:
    if hasattr(raw, "content") and isinstance(getattr(raw, "content", None), str):
        text = getattr(raw, "content")
    elif isinstance(raw, dict):
        if isinstance(raw.get("content"), str):
            text = raw["content"]
        elif isinstance(raw.get("text"), str):
            text = raw["text"]
        elif isinstance(raw.get("response"), str):
            text = raw["response"]
        elif isinstance(raw.get("message"), dict) and isinstance(raw["message"].get("content"), str):
            text = raw["message"]["content"]
        elif isinstance(raw.get("choices"), list) and raw["choices"]:
            first = raw["choices"][0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    text = message["content"]
                elif isinstance(first.get("text"), str):
                    text = first["text"]
                else:
                    text = json.dumps(raw, ensure_ascii=False)
            else:
                text = json.dumps(raw, ensure_ascii=False)
        else:
            text = json.dumps(raw, ensure_ascii=False)
    else:
        text = "" if raw is None else str(raw)

    text = text.strip()
    if not text:
        raise RuntimeError("combat_narration_provider_returned_empty_text")

    return text


def _apply_combat_narration_if_needed(
    payload: Dict[str, Any],
    *,
    combat_result: Dict[str, Any],
    combat_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Attach real LLM combat narration to the active result payload.

    This must run before fallback visible narration is finalized.
    """

    payload = _safe_dict(payload)
    combat_result = _safe_dict(combat_result)
    combat_state = _safe_dict(combat_state)

    payload["combat_narration_attempted"] = True

    if not combat_contract_requires_llm(combat_result):
        return payload

    payload["combat_narration_attempted"] = True
    payload["llm_purpose"] = "combat_narration"
    payload["combat_narration_error"] = ""

    try:
        combat_narration = generate_combat_narration_sync(
            combat_result=combat_result,
            combat_state=combat_state,
            llm_json_call=_call_combat_narration_provider_text,
        )

        contract = _safe_dict(combat_narration.get("combat_narration_contract"))
        validation = _safe_dict(combat_narration.get("combat_narration_validation"))
        narration_payload = _safe_dict(combat_narration.get("payload"))

        payload["llm_called"] = bool(combat_narration.get("llm_called"))
        payload["llm_purpose"] = "combat_narration"
        payload["combat_narration_contract"] = deepcopy(contract)
        payload["combat_narration_validation"] = deepcopy(validation)
        payload["combat_narration_payload"] = deepcopy(narration_payload)
        payload["combat_narration_accepted"] = bool(combat_narration.get("accepted"))

        if combat_narration.get("accepted") is True:
            narration = _safe_str(narration_payload.get("narration"))
            action = _safe_str(narration_payload.get("action"))

            payload["narration"] = narration
            payload["final_narration"] = narration
            payload["narration_preview"] = narration
            payload["raw_payload_narration"] = narration
            payload["action"] = action
            payload["npc"] = _safe_dict(narration_payload.get("npc"))
            payload["reward"] = _safe_str(narration_payload.get("reward"))
            payload["followup_hooks"] = _safe_list(narration_payload.get("followup_hooks"))
        else:
            payload["combat_narration_rejected"] = True
            # Keep fallback, but expose validation warnings.
            fallback = f"Result: {_safe_str(combat_result.get('reason'))}"
            if not _safe_str(payload.get("narration")).strip():
                payload["narration"] = fallback
            if not _safe_str(payload.get("final_narration")).strip():
                payload["final_narration"] = payload["narration"]
            if not _safe_str(payload.get("narration_preview")).strip():
                payload["narration_preview"] = payload["narration"]

    except Exception as exc:
        payload["llm_called"] = False
        payload["llm_purpose"] = "combat_narration"
        payload["combat_narration_error"] = f"{type(exc).__name__}: {exc}"
        if not _safe_dict(payload.get("combat_narration_contract")):
            payload["combat_narration_contract"] = build_combat_narration_contract(
                combat_result=combat_result,
                combat_state=combat_state,
            )
        if not _safe_dict(payload.get("combat_narration_validation")):
            payload["combat_narration_validation"] = {
                "ok": False,
                "warnings": ["combat_narration_provider_error"],
                "source": "deterministic_combat_narration_validator",
            }
        fallback = f"Result: {_safe_str(combat_result.get('reason'))}"
        if not _safe_str(payload.get("narration")).strip():
            payload["narration"] = fallback
        if not _safe_str(payload.get("final_narration")).strip():
            payload["final_narration"] = payload["narration"]
        if not _safe_str(payload.get("narration_preview")).strip():
            payload["narration_preview"] = payload["narration"]

    return payload


def _sync_combat_narration_fields(
    target: Dict[str, Any],
    source: Dict[str, Any],
) -> Dict[str, Any]:
    """Copy combat narration fields into the object that feeds final response assembly."""
    target = _safe_dict(target)
    source = _safe_dict(source)

    keys = (
        "combat_narration_attempted",
        "llm_called",
        "llm_purpose",
        "combat_narration_contract",
        "combat_narration_validation",
        "combat_narration_payload",
        "combat_narration_error",
        "combat_narration_accepted",
        "combat_narration_rejected",
        "narration",
        "final_narration",
        "narration_preview",
        "raw_payload_narration",
        "action",
        "npc",
        "reward",
        "followup_hooks",
    )

    for key in keys:
        if key in source:
            target[key] = deepcopy(source.get(key))

    return target


from app.rpg.action_resolver import resolve_player_action  # noqa: E402
from app.rpg.ai.action_intelligence import get_action_advisory, merge_action_advisory
from app.rpg.ai.ambient_dialogue import (
    apply_dialogue_cooldowns,
    build_ambient_dialogue_candidates,
    build_ambient_dialogue_request,
    select_ambient_dialogue_candidate,
)
from app.rpg.ai.conversation_threads import (
    add_thread_line,
    build_conversation_thread_prompt_context,
    expire_conversation_threads,
    normalize_conversation_threads,
    seed_or_update_thread,
)
from app.rpg.ai.grounding_settings import normalize_grounding_settings
from app.rpg.ai.grounding_soft_audit import run_grounding_soft_audit
from app.rpg.ai.npc_initiative import (
    apply_initiative_cooldowns,
    apply_world_behavior_bias,
    build_npc_initiative_candidates,
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
from app.rpg.campaign_journal_runtime import advance_campaign_journal_for_turn
from app.rpg.combat.abilities import (
    decrement_participant_cooldowns,
    resolve_combat_ability,
)
from app.rpg.combat.apply import (
    apply_attack_resolution,
    apply_defense_resolution,
    apply_flee_resolution,
)
from app.rpg.combat.companion_ai import (
    apply_companion_intent,
    choose_companion_intent,
    parse_companion_command,
)
from app.rpg.combat.conditions import (
    add_status_effect_to_participant,
    build_condition_effect,
    build_condition_result,
    tick_start_of_turn_status_effects,
)
from app.rpg.combat.encounters import build_encounter_from_preset
from app.rpg.combat.initiative import advance_turn, begin_combat
from app.rpg.combat.lifecycle import build_combat_participants, evaluate_combat_exit
from app.rpg.combat.models import AttackIntent
from app.rpg.combat.npc_turns import run_npc_turn
from app.rpg.combat.positioning import (
    can_attack_target,
    reposition_participant,
)
from app.rpg.combat.recovery import (
    revive_participant_with_healing,
    stabilize_participant,
)
from app.rpg.combat.resolver import resolve_attack, resolve_defend, resolve_flee
from app.rpg.combat.state import (
    build_empty_combat_state,
    get_current_actor_id,
    normalize_combat_state,
)
from app.rpg.combat.world_consequences import emit_combat_world_consequence
from app.rpg.creator.defaults import apply_adventure_defaults
from app.rpg.creator.schema import normalize_world_behavior_config
from app.rpg.creator.world_player_actions import (
    ESCALATE_CONFLICT,
    INTERVENE_THREAD,
    SUPPORT_FACTION,
)
from app.rpg.creator.world_scene_generator import generate_scenes_from_simulation
from app.rpg.creator.world_simulation import (
    build_initial_simulation_state,
    step_simulation_state,
    summarize_simulation_step,
)
from app.rpg.economy.currency import (
    can_afford,
    currency_delta,
    currency_to_copper_value,
    normalize_currency,
    subtract_currency_cost,
)
from app.rpg.economy.menu_catalog import (
    build_available_transaction_menus,
    build_provider_transaction_menus,
)
from app.rpg.economy.provider_catalog import (
    derive_npc_transaction_providers,
    derive_world_transaction_providers,
)
from app.rpg.economy.service_resolver import resolve_service_turn
from app.rpg.economy.transaction_effects import apply_transaction_effects
from app.rpg.economy.transactions import (
    build_transaction_metadata,
    enrich_action_with_registry_price,
)
from app.rpg.interactions.interaction_runtime import resolve_general_interaction
from app.rpg.items.inventory_state import (
    normalize_inventory_state,
)
from app.rpg.items.item_effects import apply_item_effects
from app.rpg.items.world_items import (
    list_scene_items,
)
from app.rpg.llm_app_gateway import build_app_llm_gateway
from app.rpg.memory.social_effects import apply_general_social_effects
from app.rpg.narration.combat_contract import (
    build_combat_narration_contract,
    combat_contract_requires_llm,
)
from app.rpg.narration.combat_service import generate_combat_narration_sync
from app.rpg.narration.contradictions import validate_narration_contradictions
from app.rpg.narration.quality import (
    build_narration_quality_context,
    update_narration_quality_memory,
    validate_narration_quality,
)
from app.rpg.narration.runtime_narration_contract import build_runtime_narration_payload
from app.rpg.narration.runtime_provider import get_runtime_llm_provider
from app.rpg.party.companion_commands import maybe_apply_companion_command
from app.rpg.party.companion_memory import (
    companion_loyalty_projection,
    companion_memory_summary,
    maybe_apply_companion_relationship_drift_from_player_input,
    record_companion_join_memory,
)
from app.rpg.party.companion_presence import (
    build_party_aware_turn_context,
    companion_presence_summary,
    project_active_companions_into_presence,
)
from app.rpg.party.companion_quests import (
    companion_quest_summary,
    maybe_progress_companion_quest_from_player_input,
    seed_companion_quest_from_arc,
)
from app.rpg.party.companion_turns import maybe_build_direct_companion_turn_response
from app.rpg.party.party_composition import project_party_composition_effects
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
)
from app.rpg.presentation.memory_inspector import build_memory_ui_summary
from app.rpg.presentation.speaker_cards import build_nearby_npc_cards
from app.rpg.presentation.visual_state import ensure_visual_state
from app.rpg.profiles.character_cards import list_character_cards_for_simulation_state
from app.rpg.profiles.dynamic_npc_profiles import load_npc_profile
from app.rpg.profiles.profile_drafts import profile_draft_summary
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
from app.rpg.session.ambient_intent import is_ambient_wait_or_listen_intent
from app.rpg.session.ambient_policy import (
    classify_ambient_delivery,
    record_interrupt,
)
from app.rpg.session.ambient_tick_runtime import (
    advance_autonomous_ambient_tick,
    is_ambient_tick_command,
)
from app.rpg.session.conversation_thread_runtime import (
    advance_conversation_threads_for_turn,
)
from app.rpg.session.idle_runtime import (
    advance_simulation_for_idle,
    build_idle_player_context,
)
from app.rpg.session.inventory_runtime import (
    drop_item_action,
    equip_item_action,
    extract_equipment,
    pickup_item_action,
    unequip_item_action,
)
from app.rpg.session.narration_runtime import (
    assemble_turn_narration_response,
    build_turn_narration_context,
    build_turn_narration_request,
)
from app.rpg.session.narration_worker import (
    ensure_narration_worker_running,
    publish_narration_event,
    signal_narration_work,
)
from app.rpg.session.response_builder import (
    build_apply_turn_response,
    build_turn_payload,
)
from app.rpg.session.service import load_session as load_canonical_session
from app.rpg.session.service import save_session as save_canonical_session
from app.rpg.session.service_runtime import (
    merge_service_result_into_contract_resolved,
    mirror_service_result,
    service_action_from_result,
    service_authoritative_result,
    service_semantic_action_from_result,
)
from app.rpg.session.state_normalization import (
    _apply_starting_resources_to_player_state,
    _copy_dict,
    _ensure_active_interactions,
    _ensure_npc_reaction_runtime_state,
    _ensure_semantic_action_runtime_state,
    _ensure_simulation_state,
    _normalize_active_interactions,
    _normalize_final_narration_text,
    _normalize_performance_settings,
    _normalize_runtime_settings,
    _normalize_social_axes,
    _normalize_story_policy,
    _normalize_structured_action,
    _safe_bool,
    _safe_dict,
    _safe_int,
    _safe_list,
    _safe_str,
    _story_policy_record_replay_artifacts,
)
from app.rpg.session.turn_contract import (
    apply_state_delta,
    build_turn_contract,
)
from app.rpg.social.npc_backbone import resolve_npc_backbone_decision
from app.rpg.world.companion_acceptance import (
    get_pending_companion_offer_debug,
    hydrate_companion_acceptance_from_pending_offers,
    resolve_pending_companion_offer_response,
)

__all__ = [name for name in globals() if not name.startswith("__")]
