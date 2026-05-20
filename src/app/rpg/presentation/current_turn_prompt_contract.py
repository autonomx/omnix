from __future__ import annotations

"""Runtime current-turn presentation prompt contract.

N117.0 promotes the battle-tested autoplay prompt-contract shape into the RPG
runtime.  The contract is intentionally bounded: simulation/turn-contract data is
truth, NPC profile data is tone/continuity only, and deterministic code only
vetoes impossible service/economy framing rather than positively classifying the
whole turn.
"""

import json
import re
from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _short(value: Any, limit: int = 400) -> str:
    text = _safe_str(value).strip()
    if len(text) > limit:
        return text[:limit].rstrip() + "...[truncated]"
    return text


def _norm(value: Any) -> str:
    text = _safe_str(value).lower().strip()
    text = re.sub(r"[^a-z0-9_]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_DOCUMENT_EVIDENCE_TERMS = (
    "sealed order",
    "sealed orders",
    "captured order",
    "captured orders",
    "written order",
    "written orders",
    "route paper",
    "route papers",
    "ledger",
    "ledger entry",
    "ledger entries",
    "manifest",
    "manifest mark",
    "manifest marks",
    "payment mark",
    "payment marks",
    "marked coin",
    "marked coin proof",
    "coin proof",
    "route cipher",
    "coded message",
    "coded messages",
    "toll marker",
    "toll markers",
    "courier route",
    "paymaster",
    "proof",
    "evidence",
)

_EXPLICIT_SERVICE_TERMS = (
    "buy",
    "purchase",
    "pay for",
    "rent",
    "hire",
    "order a drink",
    "order ale",
    "order beer",
    "order wine",
    "order a meal",
    "book a room",
    "get a room",
    "sell",
    "trade",
    "repair my",
)


def is_document_evidence_without_explicit_service(action_text: Any) -> bool:
    text = _safe_str(action_text).lower()
    if not text:
        return False
    if any(term in text for term in _EXPLICIT_SERVICE_TERMS):
        return False
    return any(term in text for term in _DOCUMENT_EVIDENCE_TERMS)


def _turn_contract_from_context(narration_context: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(
        narration_context.get("turn_contract")
        or _safe_dict(narration_context.get("resolved_result")).get("turn_contract")
    )


def _player_action_from_context(narration_context: Dict[str, Any]) -> str:
    turn_contract = _turn_contract_from_context(narration_context)
    interpreted = _safe_dict(turn_contract.get("interpreted_action"))
    action = (
        narration_context.get("player_input")
        or narration_context.get("player_action")
        or interpreted.get("input")
        or interpreted.get("text")
        or interpreted.get("action")
        or _safe_dict(narration_context.get("resolved_result")).get("player_input")
    )
    return _short(action, 600)


def _service_result_from_context(narration_context: Dict[str, Any]) -> Dict[str, Any]:
    resolved = _safe_dict(narration_context.get("resolved_result"))
    turn_contract = _turn_contract_from_context(narration_context)
    candidates = (
        narration_context.get("service_result"),
        resolved.get("service_result"),
        resolved.get("service"),
        turn_contract.get("service_result"),
        _safe_dict(turn_contract.get("mechanics")).get("service_result"),
    )
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}


def _compact_service_result(service_result: Dict[str, Any], *, action_text: str) -> Dict[str, Any]:
    service_result = _safe_dict(service_result)
    if not service_result:
        return {}

    compact = {
        "matched": bool(service_result.get("matched")),
        "kind": _safe_str(service_result.get("kind")),
        "status": _safe_str(service_result.get("status")),
        "service_kind": _safe_str(service_result.get("service_kind") or service_result.get("kind")),
        "provider_name": _safe_str(
            _safe_dict(service_result.get("provider")).get("name")
            or service_result.get("provider_name")
        ),
        "reason": _safe_str(service_result.get("reason")),
    }
    if is_document_evidence_without_explicit_service(action_text) and compact["matched"]:
        return {
            "matched": False,
            "kind": "not_service",
            "status": "service_false_positive_vetoed",
            "reason": "document_evidence_without_explicit_service_request",
            "original_service_result": compact,
            "veto_only": True,
            "forced_positive_classification": False,
        }
    return compact


def _required_focus_for_action(
    *,
    action_text: str,
    turn_contract: Dict[str, Any],
    service_result: Dict[str, Any],
) -> List[str]:
    action_n = _norm(action_text)
    resolved_n = _norm(
        _safe_dict(turn_contract.get("resolved_result")).get("summary")
        or turn_contract.get("narration_brief")
        or turn_contract.get("action_result")
    )
    focus: List[str] = []

    def add(item: str) -> None:
        if item and item not in focus:
            focus.append(item)

    document_evidence = is_document_evidence_without_explicit_service(action_text)
    service_matched = bool(_safe_dict(service_result).get("matched"))

    if document_evidence:
        add("answer_current_evidence_document_or_route_context_first")
        add("do_not_treat_document_order_words_as_shop_or_drink_orders")
        add("llm_classifies_presentation_intent")
        add("deterministic_code_only_vetoes_impossible_service_or_economy")
    elif service_matched:
        add("acknowledge_the_service_or_economy_request_first")
        add("mention_item_quantity_price_or_refusal_only_if_present_in_contract")

    if any(term in action_n for term in ("ask", "question", "tell", "report", "warn", "explain")):
        add("answer_current_question")
    if any(term in action_n for term in ("look", "inspect", "search", "scout", "examine", "listen", "study", "review", "decode", "trace")):
        add("observed_evidence_or_limits")
    if any(term in action_n for term in ("travel", "follow", "leave", "go to", "road", "route", "courier")) or "travel" in resolved_n:
        add("current_travel_or_route_action")
    if any(term in action_n for term in ("attack", "strike", "fight", "combat", "defend")):
        add("combat_claims_must_match_authoritative_combat_facts")

    return focus[:10]


def _compact_turn_contract(turn_contract: Dict[str, Any]) -> Dict[str, Any]:
    turn_contract = _safe_dict(turn_contract)
    interpreted = _safe_dict(turn_contract.get("interpreted_action"))
    return {
        "format_version": _safe_str(turn_contract.get("format_version")) or "runtime_turn_contract_compact_v1",
        "narration_brief": _short(turn_contract.get("narration_brief"), 800),
        "interpreted_action": {
            "intent": _safe_str(interpreted.get("intent")),
            "target_id": _safe_str(interpreted.get("target_id")),
            "target_name": _safe_str(interpreted.get("target_name")),
        },
        "state_delta": _safe_dict(turn_contract.get("state_delta")),
        "combat_result": _safe_dict(turn_contract.get("combat_result")),
        "reward": turn_contract.get("reward"),
    }


def _compact_loaded_npc_profiles(narration_context: Dict[str, Any], limit: int = 6) -> Dict[str, Any]:
    runtime_state = _safe_dict(narration_context.get("runtime_state"))
    npc_evolution = _safe_dict(runtime_state.get("npc_evolution"))
    loaded = _safe_dict(npc_evolution.get("loaded_profiles"))

    # Runtime narration paths may provide a direct summary instead of the
    # autoplay-style loaded profile map.
    direct_profile = _safe_dict(narration_context.get("npc_profile_summary"))
    if direct_profile and not loaded:
        key = _safe_str(direct_profile.get("npc_id") or direct_profile.get("id") or direct_profile.get("name") or "target_npc")
        loaded = {key: {"profile": direct_profile}}

    out: Dict[str, Any] = {}
    for npc_id, row_any in list(loaded.items())[:limit]:
        row = _safe_dict(row_any)
        profile = _safe_dict(row.get("profile") or row)
        out[str(npc_id)] = {
            "name": _safe_str(profile.get("name") or profile.get("display_name") or npc_id),
            "role": _safe_str(profile.get("role") or profile.get("occupation")),
            "arc_stage": _safe_str(profile.get("arc_stage") or "stable"),
            "persona": _safe_dict(profile.get("persona") or profile.get("personality")),
            "axes": _safe_dict(profile.get("axes")),
            "memories": _safe_list(profile.get("memories"))[-4:],
            "milestones": _safe_list(profile.get("milestones"))[-3:],
            "future_hooks": _safe_list(profile.get("future_hooks"))[-3:],
            "world_signals": _safe_list(profile.get("world_signals"))[-3:],
        }
    return out


def build_runtime_current_turn_prompt_contract(
    *,
    scene: Dict[str, Any] | None = None,
    narration_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    scene = _safe_dict(scene)
    narration_context = _safe_dict(narration_context)
    turn_contract = _turn_contract_from_context(narration_context)
    action_text = _player_action_from_context(narration_context)
    service_result = _compact_service_result(
        _service_result_from_context(narration_context),
        action_text=action_text,
    )
    required_focus = _required_focus_for_action(
        action_text=action_text,
        turn_contract=turn_contract,
        service_result=service_result,
    )
    document_service_veto = is_document_evidence_without_explicit_service(action_text)

    return {
        "format_version": "runtime_current_turn_prompt_contract_v1",
        "source": "runtime_presentation_pipeline",
        "player_action": action_text,
        "scene": {
            "title": _safe_str(scene.get("title")),
            "location": _safe_str(scene.get("location_name") or scene.get("location_id")),
            "present_actors": _safe_list(scene.get("actors"))[:8],
        },
        "turn_contract": _compact_turn_contract(turn_contract),
        "service_result": service_result,
        "required_focus": required_focus,
        "classification_policy": {
            "llm_classifies_presentation_intent": True,
            "deterministic_code_only_vetoes_impossible_service_or_economy": True,
            "service_economy_categories_blocked_without_authoritative_contract_support": True,
            "veto_only_no_forced_positive_classification": True,
        },
        "forbidden_stale_topics": [
            "do_not_repeat_old_investigation_threads_as_the_current_answer",
            "do_not_treat_profile_memory_as_new_current_turn_outcome",
            "do_not_offer_drinks_rooms_or_prices_unless_current_action_explicitly_buys_or_rents",
        ],
        "service_resolver_veto": {
            "service_false_positive_vetoed": bool(document_service_veto and _safe_dict(service_result).get("status") == "service_false_positive_vetoed"),
            "reason": "document_evidence_without_explicit_service_request" if document_service_veto else "",
            "veto_only": True,
            "forced_positive_classification": False,
        },
        "npc_profile_context": {
            "usage": "tone_and_continuity_only",
            "loaded_npc_profiles": _compact_loaded_npc_profiles(narration_context),
        },
    }


def format_runtime_prompt_contract_block(contract: Dict[str, Any], max_chars: int = 7000) -> str:
    text = json.dumps(_safe_dict(contract), ensure_ascii=False, indent=2, default=str)
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n...[truncated]"
    return text
