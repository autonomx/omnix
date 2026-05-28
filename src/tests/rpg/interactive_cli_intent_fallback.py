"""CB/CB.2/CB.3 — LLM intent routing for interactive CLI turns.

CB originally called the provider only when deterministic classification looked
ambiguous.  CB.3 makes the interactive CLI use the provider as the first-class
semantic intent router on every player turn by default.  Deterministic parsing is
still recorded as diagnostic context, but it no longer decides whether the LLM is
called.  The LLM remains advisory: inventory, prices, mutation, and success/fail
outcomes still come only from deterministic runtime/service state.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Mapping

from app.providers.base import ChatMessage
from app.shared import get_provider, load_settings
from rpg.interactive_cli_commerce_followup import (
    infer_requested_service_kind,
    is_commerce_followup_question,
    is_purchase_intent,
)

LLM_INTENT_SOURCE = "interactive_cli_llm_intent_router_v2"
_VALID_SERVICE_KINDS = {"meal", "drink", "lodging", "supplies", "commerce", "unknown", ""}
_VALID_ACTION_TYPES = {"service_inquiry", "service_purchase", "commerce_inquiry", "talk", "observe", "travel", "combat", "unknown", ""}


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


def _provider_metadata(provider: Any = None) -> Dict[str, Any]:
    try:
        settings = load_settings()
    except Exception:
        settings = {}
    configured = _safe_str(_safe_dict(settings).get("provider") or "lmstudio")
    config = getattr(provider, "config", None)
    model = _safe_str(getattr(config, "model", "") or _safe_dict(_safe_dict(settings).get(configured)).get("model"))
    base_url = _safe_str(getattr(config, "base_url", "") or _safe_dict(_safe_dict(settings).get(configured)).get("base_url"))
    return {
        "provider_name": _safe_str(getattr(provider, "provider_name", "") or configured),
        "provider_display_name": _safe_str(getattr(provider, "provider_display_name", "")),
        "model": model,
        "base_url": base_url,
    }


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
    action_type = _safe_str(payload.get("action_type") or payload.get("intent") or "unknown").strip().lower()
    service_kind = _safe_str(payload.get("service_kind") or "unknown").strip().lower()
    if action_type not in _VALID_ACTION_TYPES:
        action_type = "unknown"
    if service_kind not in _VALID_SERVICE_KINDS:
        service_kind = "unknown"
    requested_terms = [_safe_str(item).strip().lower() for item in _safe_list(payload.get("requested_terms")) if _safe_str(item).strip()]
    if not requested_terms and payload.get("requested_offer"):
        requested_terms = [_safe_str(payload.get("requested_offer")).strip().lower()]
    return {
        "action_type": action_type,
        "service_kind": service_kind,
        "target_npc": _safe_str(payload.get("target_npc") or payload.get("provider") or "").strip(),
        "requested_terms": requested_terms[:12],
        "confidence": max(0.0, min(1.0, _safe_float(payload.get("confidence"), 0.0))),
        "source": LLM_INTENT_SOURCE,
    }


def build_deterministic_intent_classification(
    *,
    player_input: str,
    current_offer_context: Mapping[str, Any] | None = None,
    last_offer_context: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    requested_kind = infer_requested_service_kind(player_input)
    commerce_question = is_commerce_followup_question(player_input)
    purchase_intent = is_purchase_intent(player_input)
    current_kind = _safe_str(_safe_dict(current_offer_context).get("service_kind")).strip().lower()
    last_kind = _safe_str(_safe_dict(last_offer_context).get("service_kind")).strip().lower()
    context_kind = current_kind or last_kind
    mismatch = bool(requested_kind and current_kind and requested_kind != current_kind)
    has_offer_context = bool(_safe_dict(current_offer_context) or _safe_dict(last_offer_context))
    action_type = "service_purchase" if purchase_intent else ("service_inquiry" if commerce_question or requested_kind else "unknown")
    confidence = 0.0
    reasons: list[str] = []
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
    needs_llm = bool((commerce_question or purchase_intent or requested_kind) and (not requested_kind or mismatch or low_confidence))
    if commerce_question and not has_offer_context:
        needs_llm = True
        reasons.append("no_authoritative_offer_context_yet")
    if purchase_intent and has_offer_context and low_confidence:
        needs_llm = True
        reasons.append("purchase_intent_low_confidence_with_offer_context")
    return {
        "action_type": action_type,
        "service_kind": requested_kind or context_kind or "unknown",
        "requested_service_kind": requested_kind,
        "current_context_service_kind": current_kind,
        "last_context_service_kind": last_kind,
        "confidence": round(min(1.0, confidence), 3),
        "commerce_question": commerce_question,
        "purchase_intent": purchase_intent,
        "service_kind_mismatch": mismatch,
        "needs_llm": needs_llm,
        "reasons": reasons,
        "source": "deterministic_commerce_classifier_v1",
    }


def _build_prompt(
    *,
    player_input: str,
    deterministic: Mapping[str, Any],
    current_offer_context: Mapping[str, Any] | None,
    last_offer_context: Mapping[str, Any] | None,
) -> str:
    payload = {
        "player_input": player_input,
        "deterministic_classification": _safe_dict(deterministic),
        "current_authoritative_service_context": _safe_dict(current_offer_context),
        "last_authoritative_service_context": _safe_dict(last_offer_context),
    }
    return (
        "You are an RPG intent router. Return only strict JSON.\n"
        "Classify the player's intent; do not invent inventory, prices, success, failure, rewards, or state mutation.\n"
        "Use action_type service_purchase for buy/pay/give-me purchase attempts.\n"
        "Use action_type service_inquiry or commerce_inquiry for questions about prices, menus, stock, food, drink, rooms, or supplies.\n"
        "Use service_kind meal for food/bread/stew/provisions, drink for ale/water, lodging for rooms/beds.\n"
        "Schema: {\"action_type\": \"service_inquiry|service_purchase|commerce_inquiry|talk|observe|travel|combat|unknown\", "
        "\"service_kind\": \"meal|drink|lodging|supplies|commerce|unknown\", "
        "\"target_npc\": string, \"requested_terms\": [string], \"confidence\": number}.\n"
        f"Input payload:\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
    )


def call_llm_intent_classifier(
    *,
    player_input: str,
    deterministic: Mapping[str, Any],
    current_offer_context: Mapping[str, Any] | None = None,
    last_offer_context: Mapping[str, Any] | None = None,
    provider_factory: Callable[[], Any] | None = None,
) -> Dict[str, Any]:
    diagnostics: Dict[str, Any] = {
        "provider_requested": True,
        "provider_called": False,
        "provider_name": "",
        "model": "",
        "base_url": "",
        "raw_text_excerpt": "",
        "parse_ok": False,
        "error": "",
        "source": LLM_INTENT_SOURCE,
    }
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
        response = provider.chat_completion(
            [
                ChatMessage(role="system", content="Return only JSON. You classify intent; simulation remains authoritative."),
                ChatMessage(role="user", content=_build_prompt(player_input=player_input, deterministic=deterministic, current_offer_context=current_offer_context, last_offer_context=last_offer_context)),
            ],
            stream=False,
            temperature=0,
            max_tokens=220,
        )
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
    context = _safe_dict(last_offer_context)
    context_kind = _safe_str(context.get("service_kind")).strip().lower()
    ok = True
    reason = "accepted"
    if not intent or _safe_str(intent.get("action_type")) == "unknown":
        ok = False
        reason = "unknown_or_empty_intent"
    elif service_kind and service_kind not in _VALID_SERVICE_KINDS:
        ok = False
        reason = "invalid_service_kind"
    elif context_kind and service_kind in {"meal", "drink", "lodging"} and context_kind != service_kind:
        reason = f"accepted_but_context_kind_differs:{service_kind}!={context_kind}"
    return {"ok": ok, "reason": reason, "source": LLM_INTENT_SOURCE}


def classify_service_intent_with_fallback(
    *,
    player_input: str,
    current_offer_context: Mapping[str, Any] | None = None,
    last_offer_context: Mapping[str, Any] | None = None,
    enable_llm: bool = True,
    provider_factory: Callable[[], Any] | None = None,
    force_llm: bool = True,
) -> Dict[str, Any]:
    deterministic = build_deterministic_intent_classification(player_input=player_input, current_offer_context=current_offer_context, last_offer_context=last_offer_context)
    llm_intent: Dict[str, Any] = {}
    llm_diag: Dict[str, Any] = {"provider_requested": False, "provider_called": False, "why_provider_not_called": "llm_intent_router_disabled", "source": LLM_INTENT_SOURCE}
    validation = {"ok": False, "reason": "not_run", "source": LLM_INTENT_SOURCE}
    final = {"action_type": deterministic.get("action_type"), "service_kind": deterministic.get("service_kind"), "confidence": deterministic.get("confidence"), "source": deterministic.get("source")}
    should_call_llm = bool(enable_llm and (force_llm or deterministic.get("needs_llm")))
    if should_call_llm:
        result = call_llm_intent_classifier(player_input=player_input, deterministic=deterministic, current_offer_context=current_offer_context, last_offer_context=last_offer_context, provider_factory=provider_factory)
        llm_intent = _safe_dict(result.get("intent"))
        llm_diag = _safe_dict(result.get("diagnostics"))
        validation = validate_llm_intent_against_context(llm_intent, last_offer_context)
        if validation.get("ok") and llm_intent:
            final = {
                "action_type": llm_intent.get("action_type") or deterministic.get("action_type"),
                "service_kind": llm_intent.get("service_kind") or deterministic.get("service_kind"),
                "target_npc": llm_intent.get("target_npc", ""),
                "requested_terms": llm_intent.get("requested_terms", []),
                "confidence": llm_intent.get("confidence", 0.0),
                "source": LLM_INTENT_SOURCE,
            }
        else:
            final["source"] = deterministic.get("source")
    elif not enable_llm:
        llm_diag["why_provider_not_called"] = "llm_intent_router_disabled"
    else:
        llm_diag["why_provider_not_called"] = "fallback_mode_deterministic_not_ambiguous"
    return {
        "format_version": "interactive_cli_intent_diagnostics_v2",
        "intent_router_mode": "always" if force_llm else "fallback",
        "deterministic_classification": deterministic,
        "llm_classification": llm_intent,
        "llm_validation": validation,
        "final_classification": final,
        "provider_requested": bool(llm_diag.get("provider_requested")),
        "provider_called": bool(llm_diag.get("provider_called")),
        "provider_name": _safe_str(llm_diag.get("provider_name")),
        "model": _safe_str(llm_diag.get("model")),
        "base_url": _safe_str(llm_diag.get("base_url")),
        "why_provider_not_called": _safe_str(llm_diag.get("why_provider_not_called") or ("" if llm_diag.get("provider_called") else llm_diag.get("error"))),
        "provider_error": _safe_str(llm_diag.get("error")),
        "provider_parse_ok": bool(llm_diag.get("parse_ok")),
        "raw_text_excerpt": _safe_str(llm_diag.get("raw_text_excerpt")),
        "source": LLM_INTENT_SOURCE,
    }


def narration_source_for_turn(turn_summary: Mapping[str, Any]) -> str:
    turn_summary = _safe_dict(turn_summary)
    if _safe_dict(turn_summary.get("interactive_cli_commerce_followup")).get("applied"):
        return "repaired"
    diagnostics = _safe_dict(turn_summary.get("interactive_cli_intent_diagnostics"))
    if diagnostics.get("provider_called"):
        return "provider_intent_classifier"
    raw = _safe_dict(turn_summary.get("raw_result") or turn_summary.get("result"))
    if raw.get("grounding_fallback") or raw.get("fallback"):
        return "fallback"
    if raw.get("narration") or turn_summary.get("raw_narration"):
        return "deterministic_or_runtime"
    return "unknown"
