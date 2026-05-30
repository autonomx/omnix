"""CB/CB.2/CB.3/CB.5/CE — LLM intent routing for interactive CLI turns."""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Mapping

from app.providers.base import ChatMessage
from app.shared import get_provider, load_settings
from rpg.interactive_cli_commerce_followup import infer_requested_service_kind, is_commerce_followup_question, is_purchase_intent

LLM_INTENT_SOURCE = "interactive_cli_llm_intent_router_v3"
FIRST_CALL_REUSE_SOURCE = "interactive_cli_first_call_intent_reuse_v1"
_VALID_SERVICE_KINDS = {"meal", "drink", "lodging", "supplies", "commerce", "quest", "rumor", "news", "work", "paid_information", "unknown", ""}
_VALID_ACTION_TYPES = {"service_inquiry", "service_purchase", "commerce_inquiry", "quest_inquiry", "rumor_inquiry", "work_inquiry", "talk", "observe", "travel", "combat", "unknown", ""}
_QUEST_TERMS = ("quest", "quests", "rumor", "rumors", "news", "work", "job", "jobs", "lead", "leads", "task", "errand")
_OWNED_SURVIVAL_PATTERNS = (
    r"\bmy\s+waterskin\b", r"\bfrom\s+my\s+waterskin\b", r"\bdrink\s+water\s+from\s+(?:my\s+)?waterskin\b",
    r"\bmy\s+ration(?:s)?\b", r"\ba\s+ration\b", r"\beat\s+(?:a\s+|my\s+)?ration(?:s)?\b", r"\bconsume\s+(?:a\s+|my\s+)?ration(?:s)?\b",
    r"\bhungry\b", r"\bthirsty\b", r"\bhunger\b", r"\bthirst\b",
)
_FIRST_CALL_CONTEXT: Dict[str, Any] = {}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _terms_from_text(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def set_first_call_context_for_next_intent(*, player_input: str, raw_result: Mapping[str, Any]) -> None:
    """Publish first-call runtime output so the outer CLI router can avoid a duplicate LLM call."""
    global _FIRST_CALL_CONTEXT
    raw_result = _safe_dict(raw_result)
    diagnostics = _extract_first_call_diagnostics(raw_result)
    if not diagnostics:
        _FIRST_CALL_CONTEXT = {}
        return
    _FIRST_CALL_CONTEXT = {
        "player_input": _safe_str(player_input),
        "raw_result": raw_result,
        "first_call_grounding_diagnostics": diagnostics,
    }


def _consume_first_call_context(player_input: str) -> Dict[str, Any]:
    global _FIRST_CALL_CONTEXT
    context = _FIRST_CALL_CONTEXT
    _FIRST_CALL_CONTEXT = {}
    if not context:
        return {}
    if _safe_str(context.get("player_input")).strip() != _safe_str(player_input).strip():
        return {}
    return context


def _extract_first_call_diagnostics(raw_result: Mapping[str, Any]) -> Dict[str, Any]:
    raw = _safe_dict(raw_result)
    nested = _safe_dict(raw.get("result"))
    diagnostics = _safe_dict(raw.get("first_call_grounding_diagnostics") or nested.get("first_call_grounding_diagnostics"))
    if diagnostics:
        return diagnostics
    for key in ("first_call_semantic_advisory", "first_call_action_advisory"):
        diagnostics = _safe_dict(_safe_dict(raw.get(key)).get("first_call_grounding_diagnostics"))
        if diagnostics:
            return diagnostics
    return {}


def _first_call_final_classification(player_input: str, raw_result: Mapping[str, Any], deterministic: Mapping[str, Any]) -> Dict[str, Any]:
    raw = _safe_dict(raw_result)
    nested = _safe_dict(raw.get("result"))
    action_adv = _safe_dict(raw.get("first_call_action_advisory"))
    semantic_adv = _safe_dict(raw.get("first_call_semantic_advisory"))
    advisory = semantic_adv or action_adv
    contract = _safe_dict(raw.get("turn_contract") or nested.get("turn_contract"))
    contract_action = _safe_dict(contract.get("action"))
    text = _safe_str(player_input).lower()
    raw_action = _safe_str(contract_action.get("action_type") or advisory.get("action_type")).strip().lower()

    final = {
        "action_type": deterministic.get("action_type") or "unknown",
        "service_kind": deterministic.get("service_kind") or "unknown",
        "target_npc": _safe_str(advisory.get("target_name") or advisory.get("target_id") or ""),
        "requested_terms": list(deterministic.get("requested_terms") or []),
        "confidence": max(_safe_float(deterministic.get("confidence"), 0.0), 0.70),
        "source": FIRST_CALL_REUSE_SOURCE,
    }

    if any(term in text for term in ("rumor", "rumors", "rumour", "rumours")):
        final.update({"action_type": "rumor_inquiry", "service_kind": "rumor", "requested_terms": _terms_from_text(text, ("rumor", "rumors", "news")), "confidence": 0.90})
    elif "news" in text:
        final.update({"action_type": "rumor_inquiry", "service_kind": "news", "requested_terms": ["news"], "confidence": 0.90})
    elif any(term in text for term in ("quest", "quests", "work", "job", "jobs", "task", "errand")):
        service_kind = "work" if any(term in text for term in ("work", "job", "jobs", "task", "errand")) else "quest"
        action_type = "work_inquiry" if service_kind == "work" else "quest_inquiry"
        terms = _terms_from_text(text, ("quest", "quests", "work", "job", "jobs", "task", "errand"))
        final.update({"action_type": action_type, "service_kind": service_kind, "requested_terms": terms, "confidence": 0.90})
    elif any(term in text for term in ("join my party", "join party", "companion", "stay close", "close as my companion")):
        terms = _terms_from_text(text, ("join my party", "join party", "companion", "stay close", "close"))
        final.update({"action_type": "talk", "service_kind": "unknown", "requested_terms": terms, "confidence": 0.90})
    elif raw.get("source") == "first_call_dialogue_safe_fallback_v1" or nested.get("source") == "first_call_dialogue_safe_fallback_v1":
        final.update({"action_type": "talk", "service_kind": "unknown", "confidence": 0.90})
    elif raw_action in {"combat", "attack_melee", "attack_ranged", "attack_unarmed"} or "attack" in text or "bandit" in text:
        final.update({"action_type": "combat", "service_kind": "unknown", "confidence": 0.90})
    elif raw_action == "travel" or "travel" in text or "old mill" in text or ("road" in text and "continue" in text):
        terms = _terms_from_text(text, ("old mill", "north", "road"))
        final.update({"action_type": "travel", "service_kind": "unknown", "requested_terms": terms, "confidence": 0.88})
    elif raw_action in {"social_activity", "observe", "investigate", "talk"} and (
        _safe_dict(raw.get("npc") or nested.get("npc")).get("speaker") or "bran" in text
    ):
        final.update({"action_type": "talk", "service_kind": "unknown", "confidence": 0.86})

    if "bran" in text and (not final.get("target_npc") or final.get("target_npc") in {"Local Environment/NPCs", "The Tavern"}):
        final["target_npc"] = "Bran"
    if not final.get("requested_terms"):
        final["requested_terms"] = _terms_from_text(text, ("attack", "old mill", "north", "road", "who are you", "this place", "companion", "join party", "join my party", "stay close", "close"))
    return final


def _is_quest_text(player_input: str) -> bool:
    return any(term in _safe_str(player_input).lower() for term in _QUEST_TERMS)


def _is_owned_survival_text(player_input: str) -> bool:
    text = _safe_str(player_input).lower()
    return any(re.search(pattern, text) for pattern in _OWNED_SURVIVAL_PATTERNS)


def _provider_metadata(provider: Any = None) -> Dict[str, Any]:
    try:
        settings = load_settings()
    except Exception:
        settings = {}
    configured = _safe_str(_safe_dict(settings).get("provider") or "lmstudio")
    config = getattr(provider, "config", None)
    model = _safe_str(getattr(config, "model", "") or _safe_dict(_safe_dict(settings).get(configured)).get("model"))
    base_url = _safe_str(getattr(config, "base_url", "") or _safe_dict(_safe_dict(settings).get(configured)).get("base_url"))
    return {"provider_name": _safe_str(getattr(provider, "provider_name", "") or configured), "provider_display_name": _safe_str(getattr(provider, "provider_display_name", "")), "model": model, "base_url": base_url}


def _extract_json_object(text: str) -> Dict[str, Any]:
    text = _safe_str(text).strip()
    if not text:
        return {}
    try:
        return _safe_dict(json.loads(text))
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        return _safe_dict(json.loads(match.group(0)))
    except Exception:
        return {}


def _sanitize_llm_intent(payload: Mapping[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    raw_action_type = _safe_str(payload.get("action_type") or payload.get("intent") or "unknown").strip().lower()
    raw_service_kind = _safe_str(payload.get("service_kind") or "unknown").strip().lower()
    requested_terms = [_safe_str(item).strip().lower() for item in _safe_list(payload.get("requested_terms")) if _safe_str(item).strip()]
    if not requested_terms and payload.get("requested_offer"):
        requested_terms = [_safe_str(payload.get("requested_offer")).strip().lower()]
    term_blob = " ".join(requested_terms + [raw_service_kind, raw_action_type])
    if any(term in term_blob for term in _QUEST_TERMS):
        if "rumor" in term_blob:
            action_type, service_kind = "rumor_inquiry", "rumor"
        elif "news" in term_blob:
            action_type, service_kind = "rumor_inquiry", "news"
        elif any(term in term_blob for term in ("work", "job", "task", "errand")):
            action_type, service_kind = "work_inquiry", "work"
        else:
            action_type, service_kind = "quest_inquiry", "quest"
    else:
        action_type = raw_action_type if raw_action_type in _VALID_ACTION_TYPES else "unknown"
        service_kind = raw_service_kind if raw_service_kind in _VALID_SERVICE_KINDS else "unknown"
    return {"action_type": action_type, "service_kind": service_kind, "target_npc": _safe_str(payload.get("target_npc") or payload.get("provider") or "").strip(), "requested_terms": requested_terms[:12], "confidence": max(0.0, min(1.0, _safe_float(payload.get("confidence"), 0.0))), "source": LLM_INTENT_SOURCE}


def build_deterministic_intent_classification(*, player_input: str, current_offer_context: Mapping[str, Any] | None = None, last_offer_context: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    owned_survival = _is_owned_survival_text(player_input)
    requested_kind = "" if owned_survival else infer_requested_service_kind(player_input)
    commerce_question = False if owned_survival else is_commerce_followup_question(player_input)
    purchase_intent = False if owned_survival else is_purchase_intent(player_input)
    quest_inquiry = _is_quest_text(player_input)
    current_kind = _safe_str(_safe_dict(current_offer_context).get("service_kind")).strip().lower()
    last_kind = _safe_str(_safe_dict(last_offer_context).get("service_kind")).strip().lower()
    context_kind = current_kind or last_kind
    mismatch = bool(requested_kind and current_kind and requested_kind != current_kind)
    has_offer_context = bool(_safe_dict(current_offer_context) or _safe_dict(last_offer_context))
    if owned_survival:
        action_type, service_kind = "observe", "unknown"
    elif quest_inquiry:
        action_type, service_kind = "quest_inquiry", "quest"
    else:
        action_type = "service_purchase" if purchase_intent else ("service_inquiry" if commerce_question or requested_kind else "unknown")
        service_kind = requested_kind or context_kind or "unknown"
    confidence = 0.0
    reasons: list[str] = []
    if owned_survival:
        confidence += 0.80
        reasons.append("owned_survival_or_inventory_self_use")
    if quest_inquiry:
        confidence += 0.60
        reasons.append("quest_terms_detected")
    if commerce_question:
        confidence += 0.45
        reasons.append("commerce_terms_detected")
    if purchase_intent:
        confidence += 0.20
        reasons.append("purchase_terms_detected")
    if requested_kind:
        confidence += 0.35
        reasons.append(f"requested_service_kind:{requested_kind}")
    if has_offer_context:
        confidence += 0.10
        reasons.append("authoritative_offer_context_available")
    if mismatch:
        confidence = min(confidence, 0.40)
        reasons.append(f"service_kind_mismatch:{requested_kind}!={current_kind}")
    low_confidence = confidence < 0.70
    needs_llm = bool(quest_inquiry or owned_survival or ((commerce_question or purchase_intent or requested_kind) and (not requested_kind or mismatch or low_confidence)))
    if commerce_question and not has_offer_context:
        needs_llm = True
        reasons.append("no_authoritative_offer_context_yet")
    if purchase_intent and has_offer_context and low_confidence:
        needs_llm = True
        reasons.append("purchase_intent_low_confidence_with_offer_context")
    return {"action_type": action_type, "service_kind": service_kind, "requested_service_kind": requested_kind, "current_context_service_kind": current_kind, "last_context_service_kind": last_kind, "confidence": round(min(1.0, confidence), 3), "commerce_question": commerce_question, "purchase_intent": purchase_intent, "quest_inquiry": quest_inquiry, "owned_survival_or_inventory_self_use": owned_survival, "service_kind_mismatch": mismatch, "needs_llm": needs_llm, "reasons": reasons, "source": "deterministic_interactive_intent_hints_v3"}


def _build_prompt(*, player_input: str, deterministic: Mapping[str, Any], current_offer_context: Mapping[str, Any] | None, last_offer_context: Mapping[str, Any] | None) -> str:
    payload = {"player_input": player_input, "deterministic_classification": _safe_dict(deterministic), "current_authoritative_service_context": _safe_dict(current_offer_context), "last_authoritative_service_context": _safe_dict(last_offer_context)}
    return (
        "You are an RPG intent router. Return only strict JSON.\n"
        "Classify the player's intent; do not invent inventory, quests, prices, rewards, success, failure, or state mutation.\n"
        "Use service_purchase for buy/pay/give-me attempts directed at an NPC merchant/service. Use service_inquiry or commerce_inquiry for NPC prices, menus, stock, food, drink, rooms, or supplies.\n"
        "Use quest_inquiry for asking an NPC for quests/work/jobs/tasks/errands. Use rumor_inquiry for rumors/news.\n"
        "Use observe and service_kind unknown for self-use/survival commands such as checking hunger/thirst, drinking from my waterskin, or eating my/a ration.\n"
        "Schema: {\"action_type\": \"service_inquiry|service_purchase|commerce_inquiry|quest_inquiry|rumor_inquiry|work_inquiry|talk|observe|travel|combat|unknown\", "
        "\"service_kind\": \"meal|drink|lodging|supplies|commerce|quest|rumor|news|work|paid_information|unknown\", \"target_npc\": string, \"requested_terms\": [string], \"confidence\": number}.\n"
        f"Input payload:\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
    )


def call_llm_intent_classifier(*, player_input: str, deterministic: Mapping[str, Any], current_offer_context: Mapping[str, Any] | None = None, last_offer_context: Mapping[str, Any] | None = None, provider_factory: Callable[[], Any] | None = None) -> Dict[str, Any]:
    diagnostics: Dict[str, Any] = {"provider_requested": True, "provider_called": False, "provider_name": "", "model": "", "base_url": "", "raw_text_excerpt": "", "parse_ok": False, "error": "", "source": LLM_INTENT_SOURCE}
    provider_factory = provider_factory or get_provider
    try:
        provider = provider_factory()
    except Exception as exc:
        diagnostics["error"] = f"provider_factory_error:{type(exc).__name__}:{exc}"
        return {"intent": {}, "diagnostics": diagnostics}
    diagnostics.update(_provider_metadata(provider))
    if provider is None:
        diagnostics["error"] = "provider_unavailable"
        return {"intent": {}, "diagnostics": diagnostics}
    try:
        diagnostics["provider_called"] = True
        response = provider.chat_completion([ChatMessage(role="system", content="Return only JSON. You classify intent; simulation remains authoritative."), ChatMessage(role="user", content=_build_prompt(player_input=player_input, deterministic=deterministic, current_offer_context=current_offer_context, last_offer_context=last_offer_context))], stream=False, temperature=0, max_tokens=220)
        raw_text = _safe_str(getattr(response, "content", response))
        diagnostics["raw_text_excerpt"] = raw_text[:600]
        if not diagnostics.get("model"):
            diagnostics["model"] = _safe_str(getattr(response, "model", ""))
        intent = _sanitize_llm_intent(_extract_json_object(raw_text))
        diagnostics["parse_ok"] = bool(intent and intent.get("action_type") != "unknown")
        return {"intent": intent, "diagnostics": diagnostics}
    except Exception as exc:
        diagnostics["error"] = f"provider_call_error:{type(exc).__name__}:{exc}"
        return {"intent": {}, "diagnostics": diagnostics}


def validate_llm_intent_against_context(intent: Mapping[str, Any], last_offer_context: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    intent = _safe_dict(intent)
    service_kind = _safe_str(intent.get("service_kind")).strip().lower()
    context_kind = _safe_str(_safe_dict(last_offer_context).get("service_kind")).strip().lower()
    ok, reason = True, "accepted"
    if not intent or _safe_str(intent.get("action_type")) == "unknown":
        ok, reason = False, "unknown_or_empty_intent"
    elif service_kind and service_kind not in _VALID_SERVICE_KINDS:
        ok, reason = False, "invalid_service_kind"
    elif context_kind and service_kind in {"meal", "drink", "lodging"} and context_kind != service_kind:
        reason = f"accepted_but_context_kind_differs:{service_kind}!={context_kind}"
    return {"ok": ok, "reason": reason, "source": LLM_INTENT_SOURCE}


def _normalize_final_intent_for_authority(player_input: str, final: Mapping[str, Any], deterministic: Mapping[str, Any]) -> Dict[str, Any]:
    normalized = dict(_safe_dict(final))
    if _is_owned_survival_text(player_input):
        normalized.update({"action_type": "observe", "service_kind": "unknown", "target_npc": "", "requested_terms": ["survival"], "confidence": max(_safe_float(normalized.get("confidence"), 0.0), _safe_float(deterministic.get("confidence"), 0.8)), "source": "deterministic_owned_survival_authority_override", "authority_override_reason": "owned_survival_or_inventory_self_use_not_service"})
    return normalized


def _diagnostics_payload(*, deterministic: Mapping[str, Any], llm_intent: Mapping[str, Any], validation: Mapping[str, Any], final: Mapping[str, Any], llm_diag: Mapping[str, Any], force_llm: bool) -> Dict[str, Any]:
    llm_diag = _safe_dict(llm_diag)
    provider_reused = bool(llm_diag.get("provider_reused_first_call"))
    provider_called = bool(llm_diag.get("provider_called") or provider_reused)
    return {"format_version": "interactive_cli_intent_diagnostics_v3", "intent_router_mode": "always" if force_llm else "fallback", "deterministic_classification": deterministic, "llm_classification": llm_intent, "llm_validation": validation, "final_classification": final, "provider_requested": bool(llm_diag.get("provider_requested") or provider_reused), "provider_called": provider_called, "outer_provider_called": bool(llm_diag.get("provider_called")), "provider_reused_first_call": provider_reused, "provider_name": _safe_str(llm_diag.get("provider_name")), "model": _safe_str(llm_diag.get("model")), "base_url": _safe_str(llm_diag.get("base_url")), "why_provider_not_called": _safe_str(llm_diag.get("why_provider_not_called") or ("" if provider_called else llm_diag.get("error"))), "provider_error": _safe_str(llm_diag.get("error")), "provider_parse_ok": bool(llm_diag.get("parse_ok")), "raw_text_excerpt": _safe_str(llm_diag.get("raw_text_excerpt")), "source": _safe_str(llm_diag.get("source") or LLM_INTENT_SOURCE)}


def classify_service_intent_with_fallback(*, player_input: str, current_offer_context: Mapping[str, Any] | None = None, last_offer_context: Mapping[str, Any] | None = None, enable_llm: bool = True, provider_factory: Callable[[], Any] | None = None, force_llm: bool = True) -> Dict[str, Any]:
    deterministic = build_deterministic_intent_classification(player_input=player_input, current_offer_context=current_offer_context, last_offer_context=last_offer_context)
    first_call_context = _consume_first_call_context(player_input)
    if first_call_context:
        first_call_diag = _safe_dict(first_call_context.get("first_call_grounding_diagnostics"))
        raw_result = _safe_dict(first_call_context.get("raw_result"))
        final = _first_call_final_classification(player_input, raw_result, deterministic)
        final = _normalize_final_intent_for_authority(player_input, final, deterministic)
        return _diagnostics_payload(
            deterministic=deterministic,
            llm_intent={},
            validation={"ok": True, "reason": "reused_first_call_router", "source": FIRST_CALL_REUSE_SOURCE},
            final=final,
            llm_diag={
                "provider_requested": False,
                "provider_called": False,
                "provider_reused_first_call": True,
                "why_provider_not_called": "first_call_router_already_called_provider",
                "parse_ok": bool(first_call_diag.get("provider_parse_ok")),
                "raw_text_excerpt": _safe_str(first_call_diag.get("raw_text"))[:600],
                "source": FIRST_CALL_REUSE_SOURCE,
            },
            force_llm=force_llm,
        )
    llm_intent: Dict[str, Any] = {}
    llm_diag: Dict[str, Any] = {"provider_requested": False, "provider_called": False, "why_provider_not_called": "llm_intent_router_disabled", "source": LLM_INTENT_SOURCE}
    validation = {"ok": False, "reason": "not_run", "source": LLM_INTENT_SOURCE}
    final = {"action_type": deterministic.get("action_type"), "service_kind": deterministic.get("service_kind"), "confidence": deterministic.get("confidence"), "source": deterministic.get("source")}
    if bool(enable_llm and (force_llm or deterministic.get("needs_llm"))):
        result = call_llm_intent_classifier(player_input=player_input, deterministic=deterministic, current_offer_context=current_offer_context, last_offer_context=last_offer_context, provider_factory=provider_factory)
        llm_intent = _safe_dict(result.get("intent"))
        llm_diag = _safe_dict(result.get("diagnostics"))
        validation = validate_llm_intent_against_context(llm_intent, last_offer_context)
        if validation.get("ok") and llm_intent:
            final = {"action_type": llm_intent.get("action_type") or deterministic.get("action_type"), "service_kind": llm_intent.get("service_kind") or deterministic.get("service_kind"), "target_npc": llm_intent.get("target_npc", ""), "requested_terms": llm_intent.get("requested_terms", []), "confidence": llm_intent.get("confidence", 0.0), "source": LLM_INTENT_SOURCE}
        else:
            final["source"] = deterministic.get("source")
    elif not enable_llm:
        llm_diag["why_provider_not_called"] = "llm_intent_router_disabled"
    else:
        llm_diag["why_provider_not_called"] = "fallback_mode_deterministic_not_ambiguous"
    final = _normalize_final_intent_for_authority(player_input, final, deterministic)
    return _diagnostics_payload(deterministic=deterministic, llm_intent=llm_intent, validation=validation, final=final, llm_diag=llm_diag, force_llm=force_llm)


def narration_source_for_turn(turn_summary: Mapping[str, Any]) -> str:
    turn_summary = _safe_dict(turn_summary)
    if _safe_dict(turn_summary.get("interactive_cli_commerce_followup")).get("applied"):
        return "repaired"
    if _safe_dict(turn_summary.get("interactive_cli_survival_repair")).get("applied"):
        return "survival_repaired"
    quest_followup = _safe_dict(turn_summary.get("interactive_cli_quest_followup"))
    if quest_followup.get("applied"):
        kind = _safe_str(quest_followup.get("inquiry_kind"))
        if kind == "rumor":
            return "rumor_repaired"
        if kind == "dialogue":
            return "dialogue_repaired"
        return "quest_repaired"
    raw = _safe_dict(turn_summary.get("raw_result") or turn_summary.get("result"))
    if _safe_str(raw.get("source")) == "first_call_dialogue_safe_fallback_v1":
        return "dialogue_repaired"
    presentation_source = _safe_str(_safe_dict(raw.get("presentation_narration_selection")).get("source"))
    if presentation_source:
        return presentation_source
    diagnostics = _safe_dict(turn_summary.get("interactive_cli_intent_diagnostics"))
    if diagnostics.get("provider_reused_first_call"):
        return "first_call_router_reused"
    if diagnostics.get("provider_called"):
        return "provider_intent_classifier"
    if raw.get("grounding_fallback") or raw.get("fallback"):
        return "fallback"
    if raw.get("narration") or turn_summary.get("raw_narration"):
        return "deterministic_or_runtime"
    return "unknown"
