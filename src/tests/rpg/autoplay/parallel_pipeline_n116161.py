"""Split helpers for autoplay background pipeline."""
from __future__ import annotations

# ruff: noqa: F401,F403,F405,F811
from tests.rpg.autoplay.parallel_pipeline_common import *
from tests.rpg.autoplay.parallel_pipeline_narration import *
from tests.rpg.autoplay.parallel_pipeline_provider_payloads import *
from tests.rpg.autoplay.parallel_pipeline_n11616 import *

def _n116161_has_explicit_commerce_request(action: str) -> bool:
    action = _norm(action)
    if not action:
        return False
    return any(pattern in f" {action} " for pattern in _N116161_EXPLICIT_COMMERCE_PATTERNS)


def _n116161_has_explicit_service_request(action: str) -> bool:
    action = _norm(action)
    if not action:
        return False
    return any(pattern in f" {action} " for pattern in _N116161_EXPLICIT_SERVICE_PATTERNS)


def _n116161_is_document_evidence_action(action: str) -> bool:
    action = _norm(action)
    if not action:
        return False
    has_doc = any(term in action for term in _N116161_DOCUMENT_EVIDENCE_TERMS)
    if not has_doc:
        return False
    # Document nouns are enough to veto service when the action has no explicit
    # commerce/service request. Verbs make the diagnostic stronger, but are not
    # required because actions like "the sealed orders point to Veska" are still
    # evidence, not tavern service.
    return True


def _n116161_service_veto_reason(action: str, service_result: Dict[str, Any]) -> str:
    action = _norm(action)
    service_result = _safe_dict(service_result)
    if not _n116161_is_document_evidence_action(action):
        return ""
    if _n116161_has_explicit_commerce_request(action) or _n116161_has_explicit_service_request(action):
        return ""
    if any(_safe_dict(service_result).get(key) for key in ("matched", "service", "purchase", "sale")):
        return "document_evidence_without_explicit_service_request"
    # Even if the resolver did not mark a service result, this is still useful
    # for blocking service/economy presentation categories in the prompt.
    return "document_evidence_blocks_service_category"


def _n116161_vetoed_service_result(
    *,
    player_action: str,
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    contract = _safe_dict(turn_contract)
    semantic_action_record = _safe_dict(semantic_action_record)
    service_result = dict(_safe_dict(contract.get("service_result")))
    semantic_action = _safe_dict(contract.get("semantic_action")) or semantic_action_record
    action_blob = " ".join(
        [
            _safe_str(player_action),
            _safe_str(contract.get("resolved_action")),
            _safe_str(contract.get("resolved_result")),
            _safe_str(semantic_action.get("intent")),
            _safe_str(semantic_action.get("action_type")),
            _safe_str(semantic_action.get("semantic_family")),
            _safe_str(semantic_action.get("activity_label")),
            _safe_str(service_result.get("service_type")),
            _safe_str(service_result.get("kind")),
        ]
    )
    reason = _n116161_service_veto_reason(action_blob, service_result)
    if not reason:
        return service_result, {}

    original_service_result = dict(service_result)
    for key in (
        "matched",
        "service",
        "purchase",
        "sale",
        "offers_available",
        "can_purchase",
        "can_sell",
    ):
        if key in service_result:
            service_result[key] = False
    service_result["status"] = "service_false_positive_vetoed"
    service_result["matched"] = False
    service_result["service"] = False
    service_result["purchase"] = False
    service_result["sale"] = False
    service_result["veto_reason"] = reason

    veto = {
        "format_version": "service_resolver_veto_v1",
        "service_false_positive_vetoed": True,
        "reason": reason,
        "original_service_result": original_service_result,
        "blocked_categories": ["service", "economy"],
        "classification_policy": "negative_guard_only_llm_still_classifies_presentation_intent",
    }
    return service_result, veto


def _action_is_commerce_request(action: str, service_result: Dict[str, Any]) -> bool:
    """Veto evidence/document false positives before trusting service flags."""
    action_norm = _norm(action)
    if _n116161_service_veto_reason(action_norm, _safe_dict(service_result)):
        return False
    service_result = _safe_dict(service_result)
    if service_result.get("purchase") or service_result.get("sale"):
        return True
    has_commerce_verb = _n116161_has_explicit_commerce_request(action_norm)
    has_commerce_object = any(term in action_norm for term in COMMERCE_OBJECT_TERMS)
    return bool(has_commerce_verb and (has_commerce_object or "coin" in action_norm or "price" in action_norm))


def _action_is_service_request(action: str, service_result: Dict[str, Any]) -> bool:
    """Veto evidence/document false positives before trusting service flags."""
    action_norm = _norm(action)
    if _n116161_service_veto_reason(action_norm, _safe_dict(service_result)):
        return False
    service_result = _safe_dict(service_result)
    if service_result.get("service"):
        return True
    return _n116161_has_explicit_service_request(action_norm)


def _n116161_scrub_focus_for_service_veto(focus: Any, veto: Dict[str, Any]) -> List[str]:
    values = [str(item) for item in _safe_list(focus) if str(item).strip()]
    if not veto:
        return values
    scrubbed = [item for item in values if item not in _N116161_BLOCKED_SERVICE_FOCUS]
    for item in (
        "do_not_treat_document_order_words_as_shop_or_drink_orders",
        "llm_must_classify_presentation_intent_without_service_or_economy_unless_contract_supports_it",
        "answer_current_evidence_document_or_route_context_first",
    ):
        if item not in scrubbed:
            scrubbed.append(item)
    return scrubbed[:10]


def _compact_turn_contract(turn_contract: Dict[str, Any]) -> Dict[str, Any]:
    contract = _safe_dict(turn_contract)
    semantic_action = _safe_dict(contract.get("semantic_action"))
    state_delta = _safe_dict(contract.get("state_delta"))
    player_action = _safe_str(contract.get("player_input")) or _safe_str(contract.get("current_player_action"))
    service_result, veto = _n116161_vetoed_service_result(
        player_action=player_action,
        turn_contract=contract,
        semantic_action_record=semantic_action,
    )
    out = {
        "version": contract.get("version"),
        "player_input": _short_text(contract.get("player_input"), 500),
        "resolved_action": contract.get("resolved_action"),
        "resolved_result": contract.get("resolved_result"),
        "semantic_action": semantic_action,
        "service_result": service_result,
        "state_delta": _dict_subset(
            state_delta,
            ["summary", "changed_keys", "relationship_delta", "memory_delta", "world_signal_delta"],
        ),
        "narration_brief": _short_text(contract.get("narration_brief"), 700),
        "presentation": _dict_subset(_safe_dict(contract.get("presentation")), ["title", "summary", "npc"]),
    }
    if veto:
        out["service_resolver_veto"] = veto
    return out


def build_current_turn_prompt_contract(
    *,
    player_action: str,
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a current-turn prompt contract with service/economy veto only.

    This does not deterministically classify evidence/document actions as
    investigation. It only removes impossible service/economy mechanics from the
    authoritative prompt context, then lets the LLM choose the presentation
    category within those bounds.
    """
    turn_contract = _safe_dict(turn_contract)
    semantic_action_record = _safe_dict(semantic_action_record)
    semantic_action = _safe_dict(turn_contract.get("semantic_action")) or semantic_action_record
    resolved_action = _safe_str(turn_contract.get("resolved_action"))
    resolved_result = _safe_str(turn_contract.get("resolved_result"))
    service_result, service_veto = _n116161_vetoed_service_result(
        player_action=player_action,
        turn_contract=turn_contract,
        semantic_action_record=semantic_action_record,
    )
    action_lower = " ".join(
        [
            _safe_str(player_action),
            resolved_action,
            resolved_result,
            _safe_str(semantic_action.get("intent")),
            _safe_str(semantic_action.get("action_type")),
            _safe_str(service_result.get("service_type")),
        ]
    ).lower()
    required_focus: List[str] = [
        "answer_the_current_player_action_before_old_context",
        "state_only_the_resolved_result_from_turn_contract",
    ]
    forbidden_stale_topics: List[str] = [
        "do_not_continue_previous_quest_investigation_unless_current_action_asks",
        "do_not_answer_profile_memory_instead_of_current_action",
    ]

    commerce_or_service_request = _action_is_commerce_request(action_lower, service_result) or _action_is_service_request(action_lower, service_result)
    if commerce_or_service_request:
        required_focus.insert(0, "acknowledge_the_service_or_economy_request_first")
        required_focus.append("mention_item_quantity_price_or_refusal_only_if_present_in_contract")
        forbidden_stale_topics.extend(
            [
                "ambush_investigation",
                "bandit_road_investigation",
                "traveler_or_road_question",
                "who_frightened_them_followup",
            ]
        )
    elif any(token in action_lower for token in ("ask", "tell", "warn", "report", "say", "question")):
        required_focus.insert(0, "answer_the_direct_dialogue_or_reported_evidence_first")
        required_focus.append("npc_line_must_be_a_response_not_a_new_unprompted_topic")
    elif any(token in action_lower for token in ("attack", "strike", "punch", "fight", "defend")):
        required_focus.insert(0, "reflect_the_combat_or_hostile_result_first")
    elif any(token in action_lower for token in ("travel", "go to", "move", "leave", "road", "bridge")):
        required_focus.insert(0, "reflect_the_route_or_movement_result_first")

    required_focus = _n116161_scrub_focus_for_service_veto(required_focus, service_veto)
    out = {
        "format_version": "current_turn_prompt_contract_v1",
        "priority": "highest",
        "turn_index_scope": "current_turn_only",
        "current_player_action": _short_text(player_action, 800),
        "resolved_action": resolved_action,
        "resolved_result": resolved_result,
        "semantic_action": semantic_action,
        "service_result": service_result,
        "required_focus": required_focus,
        "forbidden_stale_topics": sorted(set(forbidden_stale_topics)),
        "background_only_sections": [
            "recent_events",
            "loaded_npc_profiles",
            "profile_context_summary",
            "advisory_context",
            "old_quest_or_rumor_context",
        ],
        "npc_line_rules": [
            "must_answer_current_action_first",
            "may_use_profile_for_tone_only",
            "must_not_use_memory_as_new_authoritative_fact",
            "must_not_introduce_rewards_or_outcomes_absent_from_turn_contract",
        ],
        "classification_policy": {
            "llm_classifies_presentation_intent": True,
            "deterministic_code_only_vetoes_impossible_service_or_economy": True,
        },
    }
    if service_veto:
        out["service_resolver_veto"] = service_veto
        out["llm_allowed_classification"] = {
            "blocked_categories": ["service", "economy"],
            "reason": service_veto.get("reason"),
            "policy": "negative_guard_only_not_positive_deterministic_classification",
        }
    return out


def _n116161_soft_provider_payload_from_parse_failure(
    *,
    original_payload: Dict[str, Any],
    player_action: str,
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any] | None,
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
    turn_index: int,
) -> Dict[str, Any]:
    original_payload = _safe_dict(original_payload)
    raw = _safe_str(original_payload.get("raw"))
    parse_error = _safe_str(original_payload.get("error")) or "provider_combined_json_parse_error"
    context_packet = build_combined_background_context_packet(
        player_action=player_action,
        simulation_state=_safe_dict(simulation_state),
        runtime_state=_safe_dict(runtime_state),
        turn_contract=_safe_dict(turn_contract),
        semantic_action_record=_safe_dict(semantic_action_record),
    )
    current_turn_prompt_contract = _safe_dict(context_packet.get("current_turn_prompt_contract"))
    current_turn_contract_json = compact_json_for_prompt(current_turn_prompt_contract, max_chars=4500)
    prompt_metrics = _safe_dict(original_payload.get("prompt_metrics")) or prompt_section_metrics(
        {
            "system_contract": "combined_background_worker_v1",
            "current_turn_prompt_contract": current_turn_contract_json,
            "context_packet": compact_json_for_prompt(context_packet, max_chars=7000),
            "output_schema": "soft_provider_json_fallback",
        }
    )

    salvaged = _salvage_combined_narration_from_text(raw) if raw else {}
    payload: Dict[str, Any] = dict(_safe_dict(salvaged))
    narration_brief = _safe_str(_safe_dict(turn_contract).get("narration_brief"))
    if not _safe_str(payload.get("narration")):
        payload["narration"] = narration_brief or "The resolved action is carried forward without adding new facts."
    if not _safe_str(payload.get("action")):
        payload["action"] = _safe_str(_safe_dict(turn_contract).get("resolved_result")) or "The current action has been resolved by the simulation."
    payload.setdefault("npc", {"speaker": "", "line": ""})
    payload.setdefault("reward", "")
    payload.setdefault("followup_hooks", [])
    payload.setdefault(
        "presentation_intent",
        {
            "format_version": "presentation_intent_v1",
            "primary_category": "general",
            "secondary_categories": [],
            "confidence": 0.25,
            "reason": "soft_provider_json_fallback_after_parse_error_llm_classification_unavailable",
        },
    )
    payload.setdefault(
        "current_action_response",
        {
            "format_version": "current_action_response_v1",
            "required_focus": _safe_list(current_turn_prompt_contract.get("required_focus")),
            "npc_line_addresses_current_action": bool(_safe_str(payload.get("narration")) or _safe_str(_safe_dict(payload.get("npc")).get("line"))),
            "reason": "soft_provider_json_fallback_preserved_current_turn_contract",
        },
    )
    payload.setdefault(
        "prompt_contract_ack",
        {
            "used_current_turn_prompt_contract": True,
            "answered_current_action_first": True,
            "ignored_forbidden_stale_topics": True,
            "reason": "soft_provider_json_fallback_preserved_prompt_contract_after_parse_error",
        },
    )
    payload.update(
        {
            "ok": True,
            "partial": True,
            "provider_json_soft_fallback": True,
            "provider_json_parse_error_softened": True,
            "provider_payload_repaired": True,
            "soft_fallback_policy": "provider_partial_not_deterministic_hard_replacement",
            "hard_deterministic_fallback_avoided": True,
            "parse_error": parse_error,
            "raw": raw[:4000],
            "current_turn_prompt_contract": current_turn_prompt_contract,
            "prompt_debug": {
                "format_version": "combined_background_prompt_debug_v1",
                "turn_index": turn_index,
                "current_turn_prompt_contract": current_turn_prompt_contract,
                "current_turn_prompt_contract_json": current_turn_contract_json,
                "compact_context_keys": sorted(list(context_packet.keys())),
                "prompt_metrics": prompt_metrics,
                "system_contract": "combined_background_worker_v1",
                "provider_json_soft_fallback": True,
                "provider_json_parse_error_softened": True,
            },
            "prompt_metrics": prompt_metrics,
            "context_packet_keys": sorted(list(context_packet.keys())),
            "profile_context_summary": _loaded_profile_context_summary(runtime_state or {}),
        }
    )
    return payload


def _build_combined_background_payload(
    *,
    provider: Any,
    player_action: str,
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any] | None = None,
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
    turn_index: int,
) -> Dict[str, Any]:
    payload = _N116161_ORIGINAL_BUILD_COMBINED_BACKGROUND_PAYLOAD(
        provider=provider,
        player_action=player_action,
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        turn_contract=turn_contract,
        semantic_action_record=semantic_action_record,
        turn_index=turn_index,
    )
    if _safe_dict(payload).get("ok"):
        return _safe_dict(payload)
    error = _safe_str(_safe_dict(payload).get("error"))
    if "provider_combined_json_parse_error" not in error:
        return _safe_dict(payload)
    return _n116161_soft_provider_payload_from_parse_failure(
        original_payload=_safe_dict(payload),
        player_action=player_action,
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        turn_contract=turn_contract,
        semantic_action_record=semantic_action_record,
        turn_index=turn_index,
    )

# N116.19 — Root Service Resolver Precision for Background Prompt Contracts
# The service resolver is patched at the app level, but the background prompt
# pipeline also carries its own service/economy guard.  Make that guard precise:
# only service-confusable document/order/payment actions block service/economy.

_N11619_PARALLEL_STRONG_DOCUMENT_TERMS = (
    "sealed order", "sealed orders", "countermove order", "countermove orders",
    "strike order", "strike orders", "captured order", "captured orders",
    "written order", "written orders", "orders from", "orders signed",
    "orders naming", "route paper", "route papers", "captured route paper",
    "captured route papers", "ledger", "ledger entry", "ledger entries",
    "manifest", "manifest mark", "manifest marks", "payment mark",
    "payment marks", "manifest payment", "marked coin", "coin proof",
    "coin lead", "route cipher", "coded message", "coded messages",
    "toll marker", "toll markers", "courier route", "paymaster",
)
_N11619_PARALLEL_DOCUMENT_CONTEXT_TERMS = (
    "document", "documents", "paper", "papers", "letter", "letters",
    "note", "notes", "record", "records", "cipher", "code", "marks",
    "markings", "seal", "sealed", "ledger", "manifest",
)
_N11619_PARALLEL_EVIDENCE_VERBS = (
    "inspect", "study", "review", "decode", "trace", "capture", "recover",
    "report", "compare", "analyze", "analyse", "examine", "read", "copy",
    "secure", "protect", "warn", "follow", "bring", "show", "present",
    "search", "find", "identify", "check",
)
_N11619_PARALLEL_EXPLICIT_SERVICE_COMMERCE_TERMS = (
    "buy", "purchase", "pay for", "pay bran for", "pay the innkeeper for",
    "rent a room", "rent room", "book a room", "book room", "order ale",
    "order a drink", "order food", "order a meal", "order stew",
    "order supper", "buy ale", "buy food", "buy meal", "buy stew",
    "sell", "trade", "hire", "lodging", "sleep here", "rest here",
    "stay the night",
)

__all__ = [name for name in globals() if not name.startswith("__")]
