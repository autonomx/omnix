"""Split helpers for autoplay background pipeline."""
from __future__ import annotations

# ruff: noqa: F401,F403,F405,F811
from tests.rpg.autoplay.parallel_pipeline_common import *
from tests.rpg.autoplay.parallel_pipeline_narration import *
from tests.rpg.autoplay.parallel_pipeline_provider_payloads import *
from tests.rpg.autoplay.parallel_pipeline_n11616 import *
from tests.rpg.autoplay.parallel_pipeline_n116161 import *

def _n11619_parallel_is_document_service_false_positive_action(action: Any) -> bool:
    action_norm = _norm(action)
    if not action_norm:
        return False
    if any(term in action_norm for term in _N11619_PARALLEL_EXPLICIT_SERVICE_COMMERCE_TERMS):
        return False
    if any(term in action_norm for term in _N11619_PARALLEL_STRONG_DOCUMENT_TERMS):
        return True
    has_context = any(term in action_norm for term in _N11619_PARALLEL_DOCUMENT_CONTEXT_TERMS)
    has_verb = any(verb in action_norm for verb in _N11619_PARALLEL_EVIDENCE_VERBS)
    return bool(has_context and has_verb)


def _n116161_is_document_evidence_action(action: str) -> bool:
    return _n11619_parallel_is_document_service_false_positive_action(action)


def _n116161_service_veto_reason(action: str, service_result: Dict[str, Any]) -> str:
    action_norm = _norm(action)
    service_result = _safe_dict(service_result)
    if not _n11619_parallel_is_document_service_false_positive_action(action_norm):
        return ""
    if _n116161_has_explicit_commerce_request(action_norm) or _n116161_has_explicit_service_request(action_norm):
        return ""
    if any(service_result.get(key) for key in ("matched", "service", "purchase", "sale", "offers_available")):
        return "document_evidence_without_explicit_service_request"
    status = _safe_str(service_result.get("status") or service_result.get("service_status")).lower()
    kind = _safe_str(service_result.get("service_kind") or service_result.get("kind") or service_result.get("item_kind")).lower()
    if status in {"offers_available", "available", "service_available", "purchase_available"}:
        return "document_evidence_without_explicit_service_request"
    if kind in {"drink", "lodging", "meal", "shop_goods", "paid_information", "service_inquiry"}:
        return "document_evidence_without_explicit_service_request"
    return ""

# N116.20 — Provider Metadata Repair Reduction + Unsupported Combat Claim Cleanup
# Keep simulation authoritative and keep LLM classification authority for
# presentation metadata.  This layer only normalizes provider payload shape before
# attachment/report repair and suppresses provider text that claims unsupported
# combat outcomes.

_N11620_PREVIOUS_BUILD_CURRENT_TURN_PROMPT_CONTRACT = build_current_turn_prompt_contract
_N11620_PREVIOUS_BUILD_COMBINED_BACKGROUND_PAYLOAD = _build_combined_background_payload

_N11620_COMBAT_CLAIM_TERMS = (
    " hit ", " hits ", " struck ", " wound", " wounded", " injur", " damage",
    " blood", " bleeding", " kill", " killed", " slain", " dead", " defeat",
    " defeated", " victory", " wins ", " win the fight", " drops ", " falls dead",
)


def _n11620_text_has_unsupported_combat_claim(value: Any) -> bool:
    text = f" {_safe_str(value).lower()} "
    if not text.strip():
        return False
    return any(term in text for term in _N11620_COMBAT_CLAIM_TERMS)


def _n11620_turn_contract_supports_combat(turn_contract: Dict[str, Any]) -> bool:
    contract = _safe_dict(turn_contract)
    if not contract:
        return False
    for key in (
        "combat_result",
        "combat_state",
        "combat_narration_contract",
        "combat_lifecycle_events",
        "combat_consequence_events",
    ):
        value = contract.get(key)
        if value not in (None, "", {}, []):
            return True
    resolved = " ".join(
        _safe_str(contract.get(key))
        for key in ("resolved_action", "resolved_result", "narration_brief")
    ).lower()
    return any(term in resolved for term in ("damage", "wound", "hit", "defeat", "combat"))


def _n11620_provider_payload_schema_requirements(
    *,
    turn_contract: Dict[str, Any],
) -> Dict[str, Any]:
    combat_supported = _n11620_turn_contract_supports_combat(turn_contract)
    return {
        "format_version": "provider_payload_schema_requirements_v1",
        "presentation_intent_required": True,
        "presentation_intent_allowed_primary_categories": sorted(PRESENTATION_INTENT_ALLOWED_CATEGORIES),
        "current_action_response_required": True,
        "prompt_contract_ack_required": True,
        "npc_shape_required": {"speaker": "string", "line": "string"},
        "unsupported_combat_claim_guard": {
            "combat_supported_by_turn_contract": combat_supported,
            "rule": (
                "Do not claim hits, wounds, damage, death, defeat, victory, "
                "or other combat outcomes unless the authoritative turn_contract "
                "contains combat_result/combat_state/combat_narration_contract."
            ),
        },
        "normalization_notes": [
            "Return one JSON object, not markdown.",
            "Use presentation_intent for metadata only; it never creates facts.",
            "Use current_action_response.required_focus to show the NPC line answers this turn first.",
        ],
    }


def build_current_turn_prompt_contract(
    *,
    player_action: str,
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
) -> Dict[str, Any]:
    contract = _N11620_PREVIOUS_BUILD_CURRENT_TURN_PROMPT_CONTRACT(
        player_action=player_action,
        turn_contract=turn_contract,
        semantic_action_record=semantic_action_record,
    )
    contract = _safe_dict(contract)
    requirements = _n11620_provider_payload_schema_requirements(turn_contract=turn_contract)
    contract["provider_payload_schema_requirements"] = requirements
    contract["presentation_intent_examples"] = [
        {
            "player_action": "I ask Bran who left through the side door.",
            "primary_category": "dialogue",
            "secondary_categories": ["investigation"],
        },
        {
            "player_action": "I review the sealed orders and route papers.",
            "primary_category": "evidence",
            "secondary_categories": ["investigation"],
        },
        {
            "player_action": "I follow the courier route to the warehouse.",
            "primary_category": "travel",
            "secondary_categories": ["investigation"],
        },
        {
            "player_action": "I defend myself after combat has started.",
            "primary_category": "combat",
            "secondary_categories": [],
            "requires_authoritative_combat_state": True,
        },
    ]
    if not _n11620_turn_contract_supports_combat(turn_contract):
        forbidden = list(_safe_list(contract.get("forbidden")))
        for item in (
            "do_not_claim_hits_wounds_damage_death_defeat_or_victory_without_authoritative_combat_result",
            "do_not_turn_tension_or_threats_into_resolved_combat_damage",
        ):
            if item not in forbidden:
                forbidden.append(item)
        contract["forbidden"] = forbidden
        rules = list(_safe_list(contract.get("npc_line_rules")))
        guard = "combat_claims_must_be_supported_by_turn_contract"
        if guard not in rules:
            rules.append(guard)
        contract["npc_line_rules"] = rules
    return contract


def _n11620_normalize_npc_shape(value: Any) -> Dict[str, Any]:
    npc = _safe_dict(value)
    if not npc:
        if isinstance(value, str) and value.strip():
            return {"speaker": "", "line": value.strip()[:600]}
        return {"speaker": "", "line": ""}
    return {
        "speaker": _safe_str(npc.get("speaker") or npc.get("name") or npc.get("npc") or npc.get("target"))[:120],
        "line": _safe_str(npc.get("line") or npc.get("dialogue") or npc.get("text") or npc.get("response"))[:800],
    }


def _n11620_suppress_unsupported_combat_text(
    text: Any,
    *,
    turn_contract: Dict[str, Any],
) -> tuple[str, bool]:
    value = _safe_str(text)
    if not value:
        return value, False
    if _n11620_turn_contract_supports_combat(turn_contract):
        return value, False
    if not _n11620_text_has_unsupported_combat_claim(value):
        return value, False
    return (
        "The result stays within the authoritative turn contract; no hit, injury, "
        "defeat, death, or victory is confirmed.",
        True,
    )


def _n11620_normalize_provider_payload_pre_attach(
    payload: Dict[str, Any],
    *,
    player_action: str,
    turn_contract: Dict[str, Any],
    current_turn_prompt_contract: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = dict(_safe_dict(payload))
    if not payload:
        return payload

    changed = False
    contract = _safe_dict(current_turn_prompt_contract or payload.get("current_turn_prompt_contract"))
    if not contract:
        contract = build_current_turn_prompt_contract(
            player_action=player_action,
            turn_contract=turn_contract,
            semantic_action_record=_safe_dict(turn_contract).get("semantic_action") or {},
        )
        payload["current_turn_prompt_contract"] = contract
        changed = True

    if not _safe_dict(payload.get("presentation_intent")):
        candidate, source = _find_presentation_intent_candidate(payload)
        payload["presentation_intent"] = _normalize_presentation_intent(candidate)
        payload["presentation_intent_parse_source"] = source or "n11620.default"
        changed = True
    else:
        normalized_intent = _normalize_presentation_intent(payload.get("presentation_intent"))
        if normalized_intent != payload.get("presentation_intent"):
            payload["presentation_intent"] = normalized_intent
            changed = True

    response_candidate, response_source = _find_current_action_response_candidate(payload)
    if response_candidate:
        normalized_response = _normalize_current_action_response(response_candidate)
    else:
        required_focus = _safe_list(contract.get("required_focus"))
        npc_line = _safe_str(_safe_dict(payload.get("npc")).get("line"))
        normalized_response = {
            "format_version": "current_action_response_v1",
            "required_focus": required_focus[:6],
            "npc_line_addresses_current_action": bool(npc_line or _safe_str(payload.get("narration"))),
            "reason": "n11620_provider_metadata_defaulted_from_prompt_contract",
        }
    if normalized_response != payload.get("current_action_response"):
        payload["current_action_response"] = normalized_response
        payload["current_action_response_parse_source"] = response_source or "n11620.default_from_prompt_contract"
        changed = True

    npc_shape = _n11620_normalize_npc_shape(payload.get("npc"))
    if npc_shape != payload.get("npc"):
        payload["npc"] = npc_shape
        changed = True

    suppressed = False
    narration, narration_suppressed = _n11620_suppress_unsupported_combat_text(
        payload.get("narration"),
        turn_contract=turn_contract,
    )
    if narration_suppressed:
        payload["narration"] = narration
        suppressed = True
        changed = True
    npc_line, npc_suppressed = _n11620_suppress_unsupported_combat_text(
        _safe_dict(payload.get("npc")).get("line"),
        turn_contract=turn_contract,
    )
    if npc_suppressed:
        npc = _safe_dict(payload.get("npc"))
        npc["line"] = npc_line
        payload["npc"] = npc
        suppressed = True
        changed = True

    if not _safe_dict(payload.get("prompt_contract_ack")):
        payload["prompt_contract_ack"] = {
            "used_current_turn_prompt_contract": True,
            "answered_current_action_first": bool(
                _safe_dict(payload.get("current_action_response")).get("npc_line_addresses_current_action")
            ),
            "ignored_forbidden_stale_topics": True,
            "reason": "n11620_provider_metadata_normalized_pre_attach",
        }
        changed = True

    if suppressed:
        payload["unsupported_combat_claim_suppressed"] = True
        payload["unsupported_combat_claim_guard"] = {
            "format_version": "unsupported_combat_claim_guard_v1",
            "suppressed": True,
            "reason": "provider_claimed_combat_outcome_without_authoritative_turn_contract",
        }

    if changed:
        payload["provider_metadata_normalized_pre_attach"] = True
        diagnostics = dict(_safe_dict(payload.get("diagnostics")))
        diagnostics["provider_metadata_normalized_pre_attach"] = True
        if suppressed:
            diagnostics["unsupported_combat_claim_suppressed"] = True
        payload["diagnostics"] = diagnostics
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
    payload = _N11620_PREVIOUS_BUILD_COMBINED_BACKGROUND_PAYLOAD(
        provider=provider,
        player_action=player_action,
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        turn_contract=turn_contract,
        semantic_action_record=semantic_action_record,
        turn_index=turn_index,
    )
    current_contract = _safe_dict(payload.get("current_turn_prompt_contract"))
    if not current_contract:
        current_contract = build_current_turn_prompt_contract(
            player_action=player_action,
            turn_contract=turn_contract,
            semantic_action_record=semantic_action_record,
        )
    return _n11620_normalize_provider_payload_pre_attach(
        payload,
        player_action=player_action,
        turn_contract=turn_contract,
        current_turn_prompt_contract=current_contract,
    )

__all__ = [name for name in globals() if not name.startswith("__")]
