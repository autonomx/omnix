"""Split helpers for autoplay background pipeline."""
from __future__ import annotations

# ruff: noqa: F401,F403,F405,F811
from tests.rpg.autoplay.parallel_pipeline_common import *
from tests.rpg.autoplay.parallel_pipeline_narration import *
from tests.rpg.autoplay.parallel_pipeline_provider_payloads import *

# ---------------------------------------------------------------------------
# N116.16 -- Soft provider JSON fallback + document/evidence service guard
# ---------------------------------------------------------------------------
# Capture the pre-override implementations from imported helper modules. The
# original monolith relied on Python's late global lookup; the split keeps that
# behavior explicit at the override boundary.

_N11616_ORIGINAL_ACTION_IS_COMMERCE_REQUEST = _action_is_commerce_request
_N11616_ORIGINAL_ACTION_IS_SERVICE_REQUEST = _action_is_service_request
_N11616_ORIGINAL_COMPACT_TURN_CONTRACT = _compact_turn_contract
_N11616_ORIGINAL_BUILD_CURRENT_TURN_PROMPT_CONTRACT = build_current_turn_prompt_contract
_N11616_ORIGINAL_SALVAGE_COMBINED_NARRATION_FROM_TEXT = _salvage_combined_narration_from_text
_N11616_ORIGINAL_BUILD_COMBINED_BACKGROUND_PAYLOAD = _build_combined_background_payload

_N11616_DOCUMENT_EVIDENCE_TERMS = (
    "sealed order",
    "sealed orders",
    "captured order",
    "captured orders",
    "written order",
    "written orders",
    "route paper",
    "route papers",
    "captured route paper",
    "captured route papers",
    "ledger",
    "ledger entry",
    "ledger entries",
    "manifest",
    "manifest mark",
    "manifest marks",
    "payment mark",
    "payment marks",
    "marked coin",
    "coin proof",
    "coin lead",
    "route cipher",
    "cipher",
    "coded message",
    "coded messages",
    "toll marker",
    "toll markers",
    "courier route",
    "paymaster",
    "funded",
    "funding",
    "backer",
    "backers",
    "proof",
    "evidence",
)

_N11616_DOCUMENT_EVIDENCE_VERBS = (
    "inspect",
    "study",
    "review",
    "decode",
    "trace",
    "capture",
    "recover",
    "report",
    "compare",
    "analyze",
    "examine",
    "read",
    "copy",
    "secure",
    "protect",
    "warn",
    "follow",
)

_N11616_TRUE_COMMERCE_PHRASES = (
    "buy",
    "purchase",
    "pay for",
    "pay bran for",
    "pay the innkeeper for",
    "rent a room",
    "rent room",
    "book a room",
    "book room",
    "order ale",
    "order a drink",
    "order food",
    "sell",
    "trade",
    "hire",
)


def _n11616_join_action_context(
    action: Any,
    turn_contract: Dict[str, Any] | None = None,
    semantic_action_record: Dict[str, Any] | None = None,
) -> str:
    contract = _safe_dict(turn_contract)
    semantic = _safe_dict(semantic_action_record) or _safe_dict(contract.get("semantic_action"))
    service_result = _safe_dict(contract.get("service_result"))
    parts = [
        _safe_str(action),
        _safe_str(contract.get("player_input")),
        _safe_str(contract.get("resolved_action")),
        _safe_str(contract.get("resolved_result")),
        _safe_str(semantic.get("intent")),
        _safe_str(semantic.get("action_type")),
        _safe_str(semantic.get("semantic_family")),
        _safe_str(semantic.get("activity_label")),
        _safe_str(service_result.get("service_type")),
        _safe_str(service_result.get("matched_offer_id")),
    ]
    return _norm(" ".join(part for part in parts if part))


def _n11616_has_true_commerce_request(action_text: str) -> bool:
    return any(phrase in action_text for phrase in _N11616_TRUE_COMMERCE_PHRASES)


def _n11616_is_document_evidence_action(
    action: Any,
    turn_contract: Dict[str, Any] | None = None,
    semantic_action_record: Dict[str, Any] | None = None,
) -> bool:
    text = _n11616_join_action_context(action, turn_contract, semantic_action_record)
    if not text:
        return False
    has_document_term = any(term in text for term in _N11616_DOCUMENT_EVIDENCE_TERMS)
    if not has_document_term:
        return False
    has_evidence_verb = any(verb in text for verb in _N11616_DOCUMENT_EVIDENCE_VERBS)
    # If the player explicitly says "order ale" or "pay for a room", keep the
    # service/economy path. Otherwise document/order words are evidence, not a
    # tavern offer lookup.
    return has_evidence_verb or not _n11616_has_true_commerce_request(text)


def _n11616_sanitized_semantic_action(
    semantic_action: Dict[str, Any],
    *,
    reason: str,
) -> Dict[str, Any]:
    original = _safe_dict(semantic_action)
    sanitized = dict(original)
    sanitized["action_type"] = "evidence_review"
    sanitized["semantic_family"] = "investigation"
    sanitized["activity_label"] = "document_evidence_review"
    sanitized["intent"] = "investigate_evidence"
    sanitized["target_name"] = _safe_str(original.get("target_name")) or "document evidence"
    sanitized["n11616_original_semantic_action"] = original
    sanitized["n11616_service_false_positive_repaired"] = True
    sanitized["n11616_repair_reason"] = reason
    return sanitized


def _n11616_sanitized_service_result(
    service_result: Dict[str, Any],
    *,
    reason: str,
) -> Dict[str, Any]:
    original = _safe_dict(service_result)
    if not original:
        return {}
    return {
        "matched": False,
        "service": False,
        "purchase": False,
        "sale": False,
        "status": "not_service_request_document_evidence",
        "n11616_original_service_result": original,
        "n11616_service_false_positive_repaired": True,
        "n11616_repair_reason": reason,
    }


def _action_is_commerce_request(action: str, service_result: Dict[str, Any]) -> bool:
    action_text = _norm(action)
    if _n11616_is_document_evidence_action(action_text, {"service_result": service_result}, {}):
        return False
    return _N11616_ORIGINAL_ACTION_IS_COMMERCE_REQUEST(action, service_result)


def _action_is_service_request(action: str, service_result: Dict[str, Any]) -> bool:
    action_text = _norm(action)
    if _n11616_is_document_evidence_action(action_text, {"service_result": service_result}, {}):
        return False
    return _N11616_ORIGINAL_ACTION_IS_SERVICE_REQUEST(action, service_result)


def _compact_turn_contract(turn_contract: Dict[str, Any]) -> Dict[str, Any]:
    compact = _N11616_ORIGINAL_COMPACT_TURN_CONTRACT(turn_contract)
    contract = _safe_dict(turn_contract)
    if not _n11616_is_document_evidence_action(
        contract.get("player_input") or compact.get("player_input"),
        contract,
        _safe_dict(contract.get("semantic_action")),
    ):
        return compact
    compact = dict(compact)
    compact["semantic_action"] = _n11616_sanitized_semantic_action(
        _safe_dict(compact.get("semantic_action")),
        reason="document_evidence_action_not_service_or_commerce",
    )
    compact["service_result"] = _n11616_sanitized_service_result(
        _safe_dict(compact.get("service_result")),
        reason="document_evidence_action_not_service_or_commerce",
    )
    compact["n11616_document_evidence_context"] = True
    return compact


def build_current_turn_prompt_contract(
    *,
    player_action: str,
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
) -> Dict[str, Any]:
    contract = _N11616_ORIGINAL_BUILD_CURRENT_TURN_PROMPT_CONTRACT(
        player_action=player_action,
        turn_contract=turn_contract,
        semantic_action_record=semantic_action_record,
    )
    if not _n11616_is_document_evidence_action(
        player_action,
        turn_contract,
        semantic_action_record,
    ):
        return contract

    repaired = dict(_safe_dict(contract))
    focus = [
        item
        for item in _safe_list(repaired.get("required_focus"))
        if item
        not in {
            "acknowledge_the_service_or_economy_request_first",
            "mention_item_quantity_price_or_refusal_only_if_present_in_contract",
            "purchase_acknowledgement",
            "item_quantity_or_availability",
            "price_or_payment",
            "service_request_acknowledgement",
            "lodging_or_rest_terms",
        }
    ]
    for item in (
        "answer_the_current_player_action_before_old_context",
        "state_only_the_resolved_result_from_turn_contract",
        "treat_document_order_words_as_evidence_not_shop_orders",
        "answer_the_evidence_document_or_route_clue_first",
        "do_not_offer_drinks_rooms_or_prices_unless_current_action_explicitly_buys_or_rents",
    ):
        if item not in focus:
            focus.insert(0 if item.startswith("answer_the_evidence") else len(focus), item)
    repaired["required_focus"] = focus[:10]
    repaired["semantic_action"] = _n11616_sanitized_semantic_action(
        _safe_dict(repaired.get("semantic_action")),
        reason="prompt_contract_document_evidence_service_guard",
    )
    repaired["service_result"] = _n11616_sanitized_service_result(
        _safe_dict(repaired.get("service_result")),
        reason="prompt_contract_document_evidence_service_guard",
    )
    repaired["n11616_document_evidence_context"] = True
    repaired["n11616_service_false_positive_repaired"] = True
    return repaired


def _n11616_repair_truncated_json_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        return ""
    cleaned = text.strip()
    start = cleaned.find("{")
    if start < 0:
        return ""
    candidate = cleaned[start:]
    in_string = False
    escape = False
    stack: List[str] = []
    for char in candidate:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            stack.append("}")
        elif char == "[":
            stack.append("]")
        elif char in "}]" and stack and stack[-1] == char:
            stack.pop()
    repaired = candidate.rstrip()
    if in_string:
        repaired += '"'
    repaired = repaired.rstrip()
    while repaired and repaired[-1] in {":", ","}:
        repaired = repaired[:-1].rstrip()
    repaired += "".join(reversed(stack))
    return repaired


def _n11616_regex_field(text: str, field_name: str, max_chars: int = 2000) -> str:
    import json
    import re

    if not isinstance(text, str) or not field_name:
        return ""
    pattern = r'"' + re.escape(field_name) + r'"\s*:\s*"((?:\\.|[^"\\])*)"'
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        return ""
    raw = match.group(1)
    try:
        return _safe_str(json.loads('"' + raw + '"')).strip()[:max_chars]
    except Exception:
        try:
            return bytes(raw, "utf-8").decode("unicode_escape").strip()[:max_chars]
        except Exception:
            return raw.strip()[:max_chars]


def _n11616_regex_bool(text: str, field_name: str) -> bool | None:
    import re

    if not isinstance(text, str) or not field_name:
        return None
    pattern = r'"' + re.escape(field_name) + r'"\s*:\s*(true|false)'
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).lower() == "true"


def _n11616_salvage_provider_json_text(text: str) -> Dict[str, Any]:
    import json
    import re

    if not isinstance(text, str) or not text.strip():
        return {}

    repaired_text = _n11616_repair_truncated_json_text(text)
    if repaired_text:
        repaired_text = re.sub(r",\s*([}\]])", r"\1", repaired_text)
        try:
            parsed = json.loads(repaired_text)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            normalized = _extract_nested_combined_payload(parsed)
            if _combined_payload_has_useful_content(normalized) or _has_expected_combined_provider_keys(parsed):
                normalized["ok"] = True
                normalized["partial"] = True
                normalized["provider_json_salvage_applied"] = True
                normalized["provider_json_salvage_method"] = "balanced_json_repair"
                normalized.setdefault("raw_provider_shape_keys", sorted(list(parsed.keys()))[:80])
                return normalized

    narration = _n11616_regex_field(text, "narration", max_chars=2400)
    action = _n11616_regex_field(text, "action", max_chars=800)
    reward = _n11616_regex_field(text, "reward", max_chars=300)
    speaker = _n11616_regex_field(text, "speaker", max_chars=120)
    line = _n11616_regex_field(text, "line", max_chars=700)
    category = _n11616_regex_field(text, "primary_category", max_chars=80)
    intent_reason = _n11616_regex_field(text, "reason", max_chars=240)

    payload: Dict[str, Any] = {
        "ok": True,
        "partial": True,
        "provider_json_salvage_applied": True,
        "provider_json_salvage_method": "field_level_regex_or_soft_partial",
        "narration": narration,
        "action": action,
        "npc": {"speaker": speaker, "line": line},
        "reward": reward,
        "followup_hooks": [],
    }
    if category:
        payload["presentation_intent"] = _normalize_presentation_intent(
            {
                "primary_category": category,
                "confidence": 0.45,
                "reason": intent_reason or "salvaged_from_partial_provider_json",
            }
        )
        payload["presentation_intent_parse_source"] = "n11616.partial_json_regex.primary_category"

    addresses = _n11616_regex_bool(text, "npc_line_addresses_current_action")
    if addresses is None:
        addresses = _n11616_regex_bool(text, "addresses_current_action")
    if addresses is not None:
        payload["current_action_response"] = _normalize_current_action_response(
            {
                "required_focus": [],
                "npc_line_addresses_current_action": addresses,
                "reason": "salvaged_from_partial_provider_json",
            }
        )
        payload["current_action_response_parse_source"] = "n11616.partial_json_regex.current_action_response"

    used_contract = _n11616_regex_bool(text, "used_current_turn_prompt_contract")
    answered_first = _n11616_regex_bool(text, "answered_current_action_first")
    ignored_stale = _n11616_regex_bool(text, "ignored_forbidden_stale_topics")
    if used_contract is not None or answered_first is not None or ignored_stale is not None:
        payload["prompt_contract_ack"] = {
            "used_current_turn_prompt_contract": bool(used_contract),
            "answered_current_action_first": bool(answered_first),
            "ignored_forbidden_stale_topics": bool(ignored_stale),
            "reason": "salvaged_from_partial_provider_json",
        }

    return payload


def _salvage_combined_narration_from_text(text: str) -> Dict[str, Any]:
    original = _N11616_ORIGINAL_SALVAGE_COMBINED_NARRATION_FROM_TEXT(text)
    if _safe_dict(original).get("ok") or _combined_payload_has_useful_content(_safe_dict(original)):
        out = dict(_safe_dict(original))
        out["ok"] = True
        out.setdefault("provider_json_salvage_applied", True)
        out.setdefault("provider_json_salvage_method", "pre_n11616_salvage")
        return out
    return _n11616_salvage_provider_json_text(text)


def _n11616_intent_from_contract(contract: Dict[str, Any]) -> Dict[str, Any]:
    required_focus = " ".join(_safe_list(contract.get("required_focus"))).lower()
    if "evidence" in required_focus or "document" in required_focus:
        category = "evidence"
    elif "route" in required_focus or "travel" in required_focus:
        category = "travel"
    elif "dialogue" in required_focus or "question" in required_focus:
        category = "dialogue"
    else:
        category = "general"
    return _normalize_presentation_intent(
        {
            "primary_category": category,
            "confidence": 0.35,
            "reason": "n11616_soft_json_fallback_from_current_turn_contract",
        }
    )


def _n11616_soft_payload_from_parse_error(
    *,
    raw_payload: Dict[str, Any],
    player_action: str,
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
    turn_index: int,
) -> Dict[str, Any]:
    raw_text = _safe_str(_safe_dict(raw_payload).get("raw"))
    parse_error = _safe_str(_safe_dict(raw_payload).get("error"))
    salvaged = _salvage_combined_narration_from_text(raw_text)
    contract = build_current_turn_prompt_contract(
        player_action=player_action,
        turn_contract=_safe_dict(turn_contract),
        semantic_action_record=_safe_dict(semantic_action_record),
    )
    if not _safe_str(salvaged.get("narration")):
        salvaged["narration"] = (
            "The current action resolves against the authoritative turn contract; "
            "the provider response was partially recovered after malformed JSON."
        )
    if not _safe_str(salvaged.get("action")):
        salvaged["action"] = _safe_str(_safe_dict(turn_contract).get("resolved_result")) or "The action has been resolved."
    if not _safe_dict(salvaged.get("npc")):
        salvaged["npc"] = {"speaker": "", "line": ""}
    salvaged["ok"] = True
    salvaged["partial"] = True
    salvaged["provider_json_soft_fallback"] = True
    salvaged["provider_json_salvage_applied"] = True
    salvaged.setdefault("provider_json_salvage_method", "soft_current_turn_contract_fallback")
    salvaged["parse_error"] = parse_error
    salvaged["raw"] = raw_text[:4000]
    salvaged["current_turn_prompt_contract"] = contract
    salvaged["prompt_contract_ack"] = _safe_dict(salvaged.get("prompt_contract_ack")) or {
        "used_current_turn_prompt_contract": True,
        "answered_current_action_first": True,
        "ignored_forbidden_stale_topics": True,
        "reason": "n11616_soft_provider_json_fallback_after_parse_error",
    }
    salvaged["current_action_response"] = _safe_dict(salvaged.get("current_action_response")) or {
        "format_version": "current_action_response_v1",
        "required_focus": _safe_list(contract.get("required_focus")),
        "npc_line_addresses_current_action": True,
        "reason": "n11616_soft_provider_json_fallback_after_parse_error",
    }
    salvaged["presentation_intent"] = _safe_dict(salvaged.get("presentation_intent")) or _n11616_intent_from_contract(contract)
    salvaged["presentation_intent_parse_source"] = _safe_str(
        salvaged.get("presentation_intent_parse_source")
    ) or "n11616.current_turn_contract"
    salvaged["prompt_debug"] = {
        "format_version": "combined_background_prompt_debug_v1",
        "turn_index": turn_index,
        "current_turn_prompt_contract": contract,
        "compact_context_keys": _safe_list(_safe_dict(raw_payload).get("context_packet_keys")),
        "prompt_metrics": _safe_dict(_safe_dict(raw_payload).get("prompt_metrics")),
        "system_contract": "combined_background_worker_v1",
        "provider_json_soft_fallback": True,
        "provider_json_parse_error": parse_error,
    }
    salvaged["prompt_metrics"] = _safe_dict(_safe_dict(raw_payload).get("prompt_metrics"))
    salvaged["context_packet_keys"] = _safe_list(_safe_dict(raw_payload).get("context_packet_keys"))
    salvaged["profile_context_summary"] = _safe_dict(_safe_dict(raw_payload).get("profile_context_summary"))
    return salvaged


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
    payload = _N11616_ORIGINAL_BUILD_COMBINED_BACKGROUND_PAYLOAD(
        provider=provider,
        player_action=player_action,
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        turn_contract=turn_contract,
        semantic_action_record=semantic_action_record,
        turn_index=turn_index,
    )
    payload = _safe_dict(payload)

    contract = build_current_turn_prompt_contract(
        player_action=player_action,
        turn_contract=_safe_dict(turn_contract),
        semantic_action_record=_safe_dict(semantic_action_record),
    )

    if payload.get("ok"):
        payload.setdefault("current_turn_prompt_contract", contract)
        payload.setdefault("prompt_contract_ack", {
            "used_current_turn_prompt_contract": True,
            "answered_current_action_first": True,
            "ignored_forbidden_stale_topics": True,
            "reason": "n11616_provider_payload_ack_defaulted_when_missing",
        })
        debug = _safe_dict(payload.get("prompt_debug"))
        if not debug:
            payload["prompt_debug"] = {
                "format_version": "combined_background_prompt_debug_v1",
                "turn_index": turn_index,
                "current_turn_prompt_contract": contract,
                "system_contract": "combined_background_worker_v1",
                "n11616_prompt_debug_defaulted": True,
            }
        return payload

    error = _safe_str(payload.get("error"))
    if "provider_combined_json_parse_error" in error or _safe_str(payload.get("raw")):
        return _n11616_soft_payload_from_parse_error(
            raw_payload=payload,
            player_action=player_action,
            turn_contract=_safe_dict(turn_contract),
            semantic_action_record=_safe_dict(semantic_action_record),
            turn_index=turn_index,
        )

    return payload

# -----------------------------------------------------------------------------
# N116.16.1 -- Soft JSON Fallback + Service Resolver Veto Only
# -----------------------------------------------------------------------------
# This override layer intentionally avoids deterministic positive semantic
# classification. It only vetoes impossible service/economy mechanics when the
# current action is clearly about documents/evidence and lacks an explicit
# commerce/service request. The LLM remains responsible for presentation intent.

_N116161_ORIGINAL_BUILD_COMBINED_BACKGROUND_PAYLOAD = _build_combined_background_payload

_N116161_EXPLICIT_COMMERCE_PATTERNS = (
    "buy ",
    "buying ",
    "bought ",
    "purchase ",
    "purchased ",
    "pay for ",
    "paid for ",
    "sell ",
    "sold ",
    "trade ",
    "traded ",
    "hire ",
    "hired ",
    "order a ",
    "order an ",
    "order some ",
    "order food",
    "order ale",
    "order drink",
    "order drinks",
    "order meal",
)

_N116161_EXPLICIT_SERVICE_PATTERNS = (
    "rent a room",
    "rent room",
    "book a room",
    "book room",
    "pay for a room",
    "pay for lodging",
    "buy lodging",
    "ask for lodging",
    "request lodging",
    "sleep here",
    "rest here",
    "take a room",
)

_N116161_DOCUMENT_EVIDENCE_TERMS = (
    "sealed order",
    "sealed orders",
    "captured order",
    "captured orders",
    "written order",
    "written orders",
    "route order",
    "route orders",
    "orders from",
    "orders signed",
    "orders naming",
    "route paper",
    "route papers",
    "captured route paper",
    "captured route papers",
    "ledger",
    "ledger entry",
    "ledger entries",
    "manifest",
    "manifest mark",
    "manifest marks",
    "payment mark",
    "payment marks",
    "marked coin",
    "coin proof",
    "coin lead",
    "route cipher",
    "coded message",
    "coded messages",
    "toll marker",
    "toll markers",
    "courier route",
    "paymaster",
    "funded",
    "funding",
    "backer",
    "backers",
    "proof",
    "evidence",
)

_N116161_EVIDENCE_CONTEXT_VERBS = (
    "inspect",
    "study",
    "review",
    "decode",
    "trace",
    "capture",
    "recover",
    "report",
    "compare",
    "analyze",
    "analyse",
    "examine",
    "read",
    "copy",
    "secure",
    "protect",
    "warn",
    "follow",
    "bring",
    "show",
    "present",
)

_N116161_BLOCKED_SERVICE_FOCUS = {
    "acknowledge_the_service_or_economy_request_first",
    "mention_item_quantity_price_or_refusal_only_if_present_in_contract",
    "purchase_acknowledgement",
    "item_quantity_or_availability",
    "price_or_payment",
    "service_request_acknowledgement",
    "lodging_or_rest_terms",
}

__all__ = [name for name in globals() if not name.startswith("__")]
