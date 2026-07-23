from __future__ import annotations

import json
from typing import Any, Dict, List

from app.providers.structured.legacy import decode_legacy_json_object
from app.rpg.ai.pre_runtime_intent_fast_path import FAST_PATH_SOURCE
from app.rpg.session.turn_grounding import build_turn_grounding_packet

_ALLOWED_ACTION_TYPES = {"attack_unarmed", "attack_melee", "attack_ranged", "block", "dodge", "parry", "persuade", "intimidate", "deceive", "sneak", "investigate", "hack", "cast_spell", "use_item", "pickup_item", "drop_item", "equip_item", "unequip_item", "observe", "social_activity", "social_competition", "social_affection", "social_performance", "trade", "ritual", "exploration", "threat", "service_inquiry", "service_purchase", "service_consumption", "duration_action"}
_ALLOWED_SEMANTIC_FAMILIES = {"combat", "defense", "social", "trade", "commerce", "ritual", "exploration", "stealth", "magic", "technical", "item", "threat", "observation"}
_ALLOWED_INTERACTION_MODES = {"solo", "direct", "group", "public"}
_ALLOWED_VISIBILITY = {"private", "local", "public"}
_ALLOWED_INTENSITY = {0, 1, 2, 3}
_ALLOWED_STAKES = {0, 1, 2, 3}
_ALLOWED_EFFECT_AXES = {"camaraderie", "respect", "trust", "fear", "tension", "curiosity", "suspicion", "morale"}
_ALLOWED_OBSERVER_HOOKS = {"spectacle", "conversation_seed", "crowd_attention", "authority_notice", "relationship_shift", "rumor_seed"}
_ALLOWED_SCENE_IMPACTS = {"none", "minor_focus_shift", "gathers_attention", "disrupts_flow", "changes_mood"}
_ALLOWED_UTTERANCE_MODES = {
    "action_request", "casual_conversation", "clarification", "emotional_expression",
    "greeting", "identity_inquiry", "local_knowledge", "lore_question",
    "opinion_question", "wellbeing_inquiry",
}
_ALLOWED_RISK_DOMAINS = {
    "none", "combat", "commerce", "inventory", "item", "persuasion_outcome",
    "quest", "relationship_change", "reward", "service", "threat", "travel", "unknown",
}
_SEMANTIC_FAST_PATH_SOURCE = "phase14_18_semantic_reused_action_fast_path_v1"
_SEMANTIC_PACKET_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "action_intent": {"type": "object"},
        "semantic_advisory": {"type": "object"},
        "dialogue_gate": {"type": "object"},
        "final_narration_candidate": {"type": "object"},
        "reason": {"type": "string"},
    },
    "required": [
        "action_intent", "semantic_advisory", "dialogue_gate",
        "final_narration_candidate", "reason",
    ],
    "additionalProperties": False,
}


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _safe_str(v: Any) -> str:
    return str(v) if v is not None else ""


def _safe_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        lowered = v.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    if v is None:
        return default
    return bool(v)


def _safe_confidence(value: Any, default: float = 0.5) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _clip_text(text: Any, limit: int = 120) -> str:
    return _safe_str(text).strip()[:limit]


def _prompt_payload(prompt: str) -> Dict[str, Any]:
    if "INPUT:\n" not in prompt:
        return {}
    try:
        return _safe_dict(json.loads(prompt.split("INPUT:\n", 1)[1]))
    except Exception:
        return {}


def _semantic_family_for_action(action_type: str) -> str:
    action_type = _safe_str(action_type).strip().lower()
    if action_type in {"attack_unarmed", "attack_melee", "attack_ranged"}:
        return "combat"
    if action_type in {"block", "dodge", "parry"}:
        return "defense"
    if action_type in {"social_activity", "social_competition", "social_affection", "social_performance", "persuade", "deceive"}:
        return "social"
    if action_type == "trade":
        return "trade"
    if action_type in {"service_inquiry", "service_purchase", "service_consumption", "duration_action"}:
        return "commerce"
    if action_type == "ritual":
        return "ritual"
    if action_type in {"exploration", "investigate"}:
        return "exploration"
    if action_type in {"intimidate", "threat"}:
        return "threat"
    if action_type == "sneak":
        return "stealth"
    if action_type == "cast_spell":
        return "magic"
    if action_type == "hack":
        return "technical"
    if action_type in {"pickup_item", "drop_item", "equip_item", "unequip_item", "use_item"}:
        return "item"
    return "observation"


def _attach_first_call_diagnostics(
    advisory: Dict[str, Any],
    *,
    prompt: str = "",
    raw_result: Any,
    raw_text: str = "",
    source: str,
    provider_called: bool = False,
    provider_error: str = "",
    parse_ok: bool | None = None,
) -> Dict[str, Any]:
    advisory = _safe_dict(advisory)
    prompt = _safe_str(prompt)
    payload = _prompt_payload(prompt) if prompt else {}
    raw_text = _safe_str(raw_text)
    parsed_visible_response = bool(_safe_dict(advisory.get("visible_response")))
    if parse_ok is None:
        parse_ok = (
            bool(_safe_dict(raw_result))
            if isinstance(raw_result, dict)
            else bool(decode_legacy_json_object(raw_text))
        )
    provider_response_empty = provider_called and not raw_text.strip() and not parse_ok
    provider_malformed_json = provider_called and bool(raw_text.strip()) and not parse_ok
    semantic_fast_path = source == _SEMANTIC_FAST_PATH_SOURCE
    if semantic_fast_path:
        provider_status = "semantic_reused_action_fast_path"
    elif provider_error:
        provider_status = "provider_error"
    elif provider_response_empty:
        provider_status = "empty_response"
    elif provider_malformed_json:
        provider_status = "malformed_json"
    elif parse_ok:
        provider_status = "valid_json"
    elif provider_called:
        provider_status = "called_without_parseable_json"
    else:
        provider_status = "not_called"
    prompt_built = bool(prompt)
    action_fast_path_reason = _safe_str(advisory.get("pre_runtime_intent_fast_path_reason"))
    diagnostics = {
        "source": source,
        "prompt": prompt,
        "prompt_preview": prompt[:4000],
        "prompt_truncated": len(prompt) > 4000,
        "prompt_built": prompt_built,
        "prompt_available": prompt_built,
        "semantic_prompt_built": prompt_built,
        "turn_grounding_packet": _safe_dict(payload.get("turn_grounding_packet")),
        "normalized_result": {k: v for k, v in advisory.items() if k != "first_call_grounding_diagnostics"},
        "raw_text": _clip_text(raw_text, 4000),
        "raw_text_length": len(raw_text),
        "raw_result_type": type(raw_result).__name__,
        "provider_requested": not semantic_fast_path,
        "provider_called": provider_called,
        "provider_status": provider_status,
        "provider_error": provider_error,
        "provider_response_empty": provider_response_empty,
        "provider_parse_ok": bool(parse_ok),
        "provider_malformed_json": provider_malformed_json,
        "provider_visible_response_present": parsed_visible_response,
        "provider_non_stateful": not _safe_bool(advisory.get("stateful"), True),
        "provider_needs_runtime_resolution": _safe_bool(advisory.get("needs_runtime_resolution"), True),
        "intent_fast_path_used": semantic_fast_path,
        "intent_llm_used": bool(provider_called and not semantic_fast_path),
        "intent_fast_path_reason": action_fast_path_reason,
        "intent_fast_path_source": _safe_str(advisory.get("pre_runtime_intent_fast_path_source")),
        "semantic_fast_path_used": semantic_fast_path,
        "semantic_llm_used": bool(provider_called and not semantic_fast_path),
        "semantic_reused_action_fast_path": semantic_fast_path,
        "semantic_fast_path_reason": action_fast_path_reason or "action_fast_path_reused",
        "semantic_fast_path_source": _SEMANTIC_FAST_PATH_SOURCE if semantic_fast_path else "",
        "format_version": "first_call_grounding_diagnostics_v4",
    }
    advisory["first_call_grounding_diagnostics"] = diagnostics
    return advisory


def _complete_raw_text(llm_gateway: Any, prompt: str) -> tuple[Any, str, str]:
    if hasattr(llm_gateway, "complete_semantic_packet"):
        result = llm_gateway.complete_semantic_packet(
            prompt,
            response_schema=_SEMANTIC_PACKET_SCHEMA,
        )
        raw_text = (
            _safe_str(result.get("text") or result.get("content") or "")
            if isinstance(result, dict)
            else _safe_str(result)
        )
        return result, raw_text, "semantic_action_intelligence.complete_semantic_packet"
    if hasattr(llm_gateway, "complete"):
        result = llm_gateway.complete(prompt)
        raw_text = (
            _safe_str(result.get("text") or result.get("content") or "")
            if isinstance(result, dict)
            else _safe_str(result)
        )
        return result, raw_text, "semantic_action_intelligence.complete"
    if hasattr(llm_gateway, "complete_json"):
        result = llm_gateway.complete_json(prompt)
        raw_text = json.dumps(result, ensure_ascii=False, sort_keys=True) if isinstance(result, dict) and result else ""
        return result, raw_text, "semantic_action_intelligence.complete_json"
    return {}, "", "semantic_action_intelligence.no_provider_method"


def build_semantic_action_prompt(player_input: str, simulation_state: Dict[str, Any], runtime_state: Dict[str, Any], candidate_action: Dict[str, Any]) -> str:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    candidate_action = _safe_dict(candidate_action)
    grounding_packet = build_turn_grounding_packet(player_input=player_input, simulation_state=simulation_state, runtime_state=runtime_state, candidate_action=candidate_action)
    payload = {
        "player_input": _clip_text(player_input, 500),
        "turn_grounding_packet": grounding_packet,
        "allowed_action_types": sorted(_ALLOWED_ACTION_TYPES),
        "allowed_semantic_families": sorted(_ALLOWED_SEMANTIC_FAMILIES),
        "allowed_interaction_modes": sorted(_ALLOWED_INTERACTION_MODES),
        "allowed_visibility": sorted(_ALLOWED_VISIBILITY),
        "allowed_effect_axes": sorted(_ALLOWED_EFFECT_AXES),
        "allowed_observer_hooks": sorted(_ALLOWED_OBSERVER_HOOKS),
        "allowed_scene_impacts": sorted(_ALLOWED_SCENE_IMPACTS),
    }
    instructions = (
        "You are the RPG first-call semantic intent router.\n"
        "Return JSON only.\n"
        "Use the turn_grounding_packet before classifying intent. It includes current scene, active modes, recent turns, relevant_memory, rich NPC biography/personality/speech examples, relationship, inventory, capabilities, and knowledge boundaries.\n"
        "Use relevant_memory only for continuity and dialogue context; current runtime state remains authoritative and private memory must not be revealed directly.\n"
        "World/runtime state is authoritative and overrides older profile memory.\n"
        "Convert freeform player intent into a bounded semantic action object.\n"
        "Do not decide success, failure, damage, XP, prices, stock, inventory mutation, quest completion, travel success, rewards, or final state.\n"
        "Do not invent absent actors. Prefer a nearby/addressed NPC id when the target role or name strongly implies one.\n"
        "For non-stateful interpretive NPC dialogue/opinion questions, set stateful false, needs_runtime_resolution false, and provide final_narration_candidate.\n"
        "For commerce, combat, travel, inventory, quests, persuasion with consequences, threats, or anything that may mutate state, set stateful true and needs_runtime_resolution true.\n"
        "Classify semantic risk by meaning, not keywords. Use evidence_spans to cite the smallest player-input phrases supporting your classification.\n"
        "Always include dialogue_gate. Set safe_to_display_now true only for non-mutating dialogue; set it false for any state risk.\n"
        "Never reveal private_context or private NPC biography/inventory in final_narration_candidate.\n"
        "Return exactly action_intent, semantic_advisory, dialogue_gate, final_narration_candidate, and reason with all nested fields required by the schema.\n"
    )
    return instructions + "\nINPUT:\n" + json.dumps(payload, sort_keys=True)


def normalize_semantic_action_advisory(advisory: Dict[str, Any], candidate_action: Dict[str, Any]) -> Dict[str, Any]:
    advisory = _safe_dict(advisory)
    candidate_action = _safe_dict(candidate_action)
    action_intent = _safe_dict(advisory.get("action_intent"))
    semantic_packet = _safe_dict(advisory.get("semantic_advisory"))
    action_type = _safe_str(action_intent.get("action_type") or action_intent.get("type") or advisory.get("action_type")).strip().lower()
    if action_type not in _ALLOWED_ACTION_TYPES:
        action_type = _safe_str(candidate_action.get("action_type")).strip().lower()
    if action_type not in _ALLOWED_ACTION_TYPES:
        action_type = "observe"
    semantic_family = _safe_str(semantic_packet.get("semantic_family") or semantic_packet.get("family") or advisory.get("semantic_family")).strip().lower()
    if semantic_family not in _ALLOWED_SEMANTIC_FAMILIES:
        semantic_family = _semantic_family_for_action(action_type)
    interaction_mode = _safe_str(semantic_packet.get("interaction_mode") or semantic_packet.get("mode") or advisory.get("interaction_mode")).strip().lower()
    if interaction_mode not in _ALLOWED_INTERACTION_MODES:
        interaction_mode = "direct" if _safe_str(advisory.get("target_id") or candidate_action.get("target_id")) else "solo"
    visibility = _safe_str(advisory.get("visibility")).strip().lower()
    if visibility not in _ALLOWED_VISIBILITY:
        visibility = "local"
    try:
        intensity = int(advisory.get("intensity", 1))
    except Exception:
        intensity = 1
    if intensity not in _ALLOWED_INTENSITY:
        intensity = 1
    try:
        stakes = int(advisory.get("stakes", 1))
    except Exception:
        stakes = 1
    if stakes not in _ALLOWED_STAKES:
        stakes = 1
    observer_hooks: list[str] = []
    for value in _safe_list(advisory.get("observer_hooks"))[:4]:
        hook = _safe_str(value).strip().lower()
        if hook in _ALLOWED_OBSERVER_HOOKS and hook not in observer_hooks:
            observer_hooks.append(hook)
    social_axes: list[dict[str, int | str]] = []
    for item in _safe_list(advisory.get("social_axes"))[:4]:
        item = _safe_dict(item)
        axis = _safe_str(item.get("axis")).strip().lower()
        if axis not in _ALLOWED_EFFECT_AXES:
            continue
        try:
            delta = int(item.get("delta", 0))
        except Exception:
            delta = 0
        if delta:
            social_axes.append({"axis": axis, "delta": max(-2, min(2, delta))})
    secondary_actor_ids: list[str] = []
    for value in _safe_list(advisory.get("secondary_actor_ids"))[:4]:
        actor_id = _safe_str(value).strip()
        if actor_id and actor_id not in secondary_actor_ids:
            secondary_actor_ids.append(actor_id)
    scene_impact = _safe_str(advisory.get("scene_impact")).strip().lower()
    if scene_impact not in _ALLOWED_SCENE_IMPACTS:
        scene_impact = "none"
    utterance_mode = _safe_str(semantic_packet.get("utterance_mode") or advisory.get("utterance_mode")).strip().lower()
    if utterance_mode not in _ALLOWED_UTTERANCE_MODES:
        utterance_mode = "action_request" if _safe_bool(advisory.get("literal_action_requested"), False) else "casual_conversation"
    risk_domain = _safe_str(semantic_packet.get("risk_domain") or advisory.get("risk_domain")).strip().lower()
    if risk_domain not in _ALLOWED_RISK_DOMAINS:
        risk_domain = "unknown" if _safe_bool(advisory.get("state_mutation_requested"), False) else "none"
    evidence_spans: list[str] = []
    for value in _safe_list(semantic_packet.get("evidence_spans") or advisory.get("evidence_spans"))[:6]:
        span = _clip_text(value, 120)
        if span and span not in evidence_spans:
            evidence_spans.append(span)
    visible_response = _safe_dict(advisory.get("final_narration_candidate") or advisory.get("visible_response"))
    normalized_visible_response = {}
    if visible_response:
        npc = _safe_dict(visible_response.get("npc"))
        normalized_visible_response = {
            "narration": _clip_text(visible_response.get("narration"), 500),
            "npc": {"speaker": _clip_text(npc.get("speaker"), 80), "line": _clip_text(npc.get("line"), 900)},
        }
    direct_gate = _safe_dict(advisory.get("dialogue_gate") or advisory.get("direct_response_gate"))
    normalized_direct_gate = {
        "safe_to_display_now": _safe_bool(direct_gate.get("safe_to_display_now"), False),
        "reason": _clip_text(direct_gate.get("reason"), 160),
        "risk_flags": [
            _clip_text(flag, 48).lower().replace(" ", "_")
            for flag in _safe_list(direct_gate.get("risk_flags"))[:8]
            if _clip_text(flag, 48)
        ],
    }
    stateful = _safe_bool(action_intent.get("stateful", advisory.get("stateful")), True)
    needs_runtime_resolution = _safe_bool(action_intent.get("needs_runtime_resolution", advisory.get("needs_runtime_resolution")), stateful)
    literal_action_requested = _safe_bool(semantic_packet.get("literal_action_requested", advisory.get("literal_action_requested")), False)
    state_mutation_requested = _safe_bool(semantic_packet.get("state_mutation_requested", advisory.get("state_mutation_requested")), False)
    if not stateful and normalized_direct_gate.get("safe_to_display_now") is True and normalized_visible_response and risk_domain == "none" and not literal_action_requested and not state_mutation_requested:
        needs_runtime_resolution = False
    if not direct_gate and normalized_visible_response and not stateful and not needs_runtime_resolution:
        normalized_direct_gate = {"safe_to_display_now": True, "reason": "legacy_non_stateful_visible_response", "risk_flags": []}
    target_id = _safe_str(action_intent.get("target_id") or advisory.get("target_id") or candidate_action.get("target_id")).strip()
    target_name = _clip_text(action_intent.get("target_name") or advisory.get("target_name") or candidate_action.get("target_name"), 80)
    service_kind = _clip_text(action_intent.get("service_kind") or semantic_packet.get("service_kind") or advisory.get("service_kind") or candidate_action.get("service_kind"), 48).lower().replace(" ", "_")
    offer_id = _clip_text(action_intent.get("offer_id") or semantic_packet.get("offer_id") or advisory.get("offer_id") or candidate_action.get("offer_id"), 120)
    confirmation = _safe_bool(action_intent.get("confirmation", semantic_packet.get("confirmation", advisory.get("confirmation"))), False)
    duration_policy = _clip_text(action_intent.get("duration_policy") or semantic_packet.get("duration_policy") or advisory.get("duration_policy"), 64).lower().replace(" ", "_")
    confidence = _safe_confidence(action_intent.get("confidence", advisory.get("confidence", 0.5)))
    ambiguities = [_clip_text(value, 120) for value in _safe_list(action_intent.get("ambiguities") or advisory.get("ambiguities"))[:6] if _clip_text(value, 120)]
    activity_label = _clip_text(semantic_packet.get("activity_label") or advisory.get("activity_label"), 64).lower().replace(" ", "_")
    intent_summary = _clip_text(semantic_packet.get("intent_summary") or advisory.get("intent_summary"), 220)
    normalized = {
        "action_type": action_type,
        "semantic_family": semantic_family,
        "interaction_mode": interaction_mode,
        "activity_label": activity_label,
        "target_id": target_id,
        "target_name": target_name,
        "service_kind": service_kind,
        "offer_id": offer_id,
        "confirmation": confirmation,
        "duration_policy": duration_policy,
        "confidence": confidence,
        "ambiguities": ambiguities,
        "secondary_actor_ids": secondary_actor_ids,
        "visibility": visibility,
        "intensity": intensity,
        "stakes": stakes,
        "social_axes": social_axes,
        "observer_hooks": observer_hooks,
        "scene_impact": scene_impact,
        "utterance_mode": utterance_mode,
        "literal_action_requested": literal_action_requested,
        "state_mutation_requested": state_mutation_requested,
        "risk_domain": risk_domain,
        "intent_summary": intent_summary,
        "evidence_spans": evidence_spans,
        "stateful": stateful,
        "needs_runtime_resolution": needs_runtime_resolution,
        "visible_response": normalized_visible_response,
        "direct_response_gate": normalized_direct_gate,
        "action_intent": {
            "action_type": action_type,
            "target_id": target_id,
            "target_name": target_name,
            "service_kind": service_kind,
            "offer_id": offer_id,
            "confirmation": confirmation,
            "duration_policy": duration_policy,
            "confidence": confidence,
            "ambiguities": ambiguities,
            "stateful": stateful,
            "needs_runtime_resolution": needs_runtime_resolution,
        },
        "semantic_advisory": {
            "semantic_family": semantic_family,
            "interaction_mode": interaction_mode,
            "activity_label": activity_label,
            "utterance_mode": utterance_mode,
            "literal_action_requested": literal_action_requested,
            "state_mutation_requested": state_mutation_requested,
            "risk_domain": risk_domain,
            "intent_summary": intent_summary,
            "evidence_spans": evidence_spans,
        },
        "dialogue_gate": normalized_direct_gate,
        "final_narration_candidate": normalized_visible_response,
        "grounding_packet_version": "turn_grounding_packet_v1",
        "reason": _clip_text(advisory.get("reason"), 200),
    }
    for key in (
        "pre_runtime_intent_fast_path", "pre_runtime_intent_fast_path_reason",
        "pre_runtime_intent_fast_path_source", "semantic_fast_path_used",
        "semantic_reused_action_fast_path",
    ):
        if key in advisory:
            normalized[key] = advisory[key]
    return normalized


def _is_action_fast_path_advisory(candidate_action: Dict[str, Any]) -> bool:
    candidate_action = _safe_dict(candidate_action)
    diagnostics = _safe_dict(candidate_action.get("first_call_grounding_diagnostics"))
    return bool(
        candidate_action.get("pre_runtime_intent_fast_path")
        or diagnostics.get("intent_fast_path_used")
        or diagnostics.get("source") == FAST_PATH_SOURCE
        or diagnostics.get("provider_status") == "fast_path"
    )


def _semantic_action_from_action_fast_path(candidate_action: Dict[str, Any]) -> Dict[str, Any]:
    candidate_action = _safe_dict(candidate_action)
    diagnostics = _safe_dict(candidate_action.get("first_call_grounding_diagnostics"))
    reason = _safe_str(
        candidate_action.get("pre_runtime_intent_fast_path_reason")
        or diagnostics.get("intent_fast_path_reason")
        or "action_fast_path_reused"
    )
    action_type = _safe_str(candidate_action.get("action_type")).strip().lower()
    raw = {
        "action_type": action_type,
        "semantic_family": _semantic_family_for_action(action_type),
        "interaction_mode": "direct" if _safe_str(candidate_action.get("target_id")) else "solo",
        "activity_label": "fast_path_" + (reason or action_type or "intent"),
        "target_id": _safe_str(candidate_action.get("target_id")),
        "target_name": _safe_str(candidate_action.get("target_name")),
        "secondary_actor_ids": [],
        "visibility": "local",
        "intensity": 1,
        "stakes": 1,
        "social_axes": [],
        "observer_hooks": [],
        "scene_impact": "none",
        "utterance_mode": _safe_str(candidate_action.get("utterance_mode")),
        "literal_action_requested": _safe_bool(candidate_action.get("literal_action_requested"), False),
        "state_mutation_requested": _safe_bool(candidate_action.get("state_mutation_requested"), True),
        "risk_domain": _safe_str(candidate_action.get("risk_domain") or "unknown"),
        "intent_summary": _safe_str(candidate_action.get("intent_summary")),
        "evidence_spans": _safe_list(candidate_action.get("evidence_spans")),
        "stateful": _safe_bool(candidate_action.get("stateful"), True),
        "needs_runtime_resolution": _safe_bool(candidate_action.get("needs_runtime_resolution"), True),
        "visible_response": _safe_dict(candidate_action.get("visible_response")),
        "direct_response_gate": _safe_dict(candidate_action.get("direct_response_gate")),
        "reason": f"semantic router reused action fast path: {reason}",
        "pre_runtime_intent_fast_path": True,
        "pre_runtime_intent_fast_path_reason": reason,
        "pre_runtime_intent_fast_path_source": _safe_str(candidate_action.get("pre_runtime_intent_fast_path_source") or diagnostics.get("intent_fast_path_source") or FAST_PATH_SOURCE),
        "semantic_fast_path_used": True,
        "semantic_reused_action_fast_path": True,
    }
    return normalize_semantic_action_advisory(raw, candidate_action)


def get_semantic_action_advisory(llm_gateway: Any, player_input: str, simulation_state: Dict[str, Any], runtime_state: Dict[str, Any], candidate_action: Dict[str, Any]) -> Dict[str, Any]:
    candidate_action = _safe_dict(candidate_action)
    if llm_gateway is None:
        return {}
    prompt = build_semantic_action_prompt(player_input, simulation_state, runtime_state, candidate_action)
    raw_result: Any = {}
    raw_text = ""
    source = "semantic_action_intelligence.complete"
    parsed: Dict[str, Any] = {}
    provider_error = ""
    try:
        raw_result, raw_text, source = _complete_raw_text(llm_gateway, prompt)
        parsed = _safe_dict(raw_result) if source.endswith("complete_json") else decode_legacy_json_object(raw_text)
    except Exception as exc:
        provider_error = f"{type(exc).__name__}: {exc}"
    advisory = normalize_semantic_action_advisory(parsed, candidate_action)
    return _attach_first_call_diagnostics(
        advisory,
        prompt=prompt,
        raw_result=raw_result,
        raw_text=raw_text,
        source=source,
        provider_called=not source.endswith("no_provider_method"),
        provider_error=provider_error,
        parse_ok=bool(parsed),
    )
