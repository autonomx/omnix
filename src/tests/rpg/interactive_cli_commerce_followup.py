"""CA.1 — deterministic commerce follow-up repair for interactive CLI runs.

The runtime can correctly surface a service inquiry such as Bran's meal offer,
but a later vague follow-up like "what provisions do you have?" may be routed as
plain talk/observe and lose the offer list.  For interactive playtests, keep a
bounded in-process memory of the most recent authoritative service offers and use
it to answer immediate commerce follow-up questions without inventing stock.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping

COMMERCE_FOLLOWUP_SOURCE = "interactive_cli_commerce_followup_v1"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _walk(value: Any, *, depth: int = 0, max_depth: int = 8) -> Iterable[Dict[str, Any]]:
    if depth > max_depth:
        return
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk(nested, depth=depth + 1, max_depth=max_depth)
    elif isinstance(value, list):
        for item in value[:200]:
            yield from _walk(item, depth=depth + 1, max_depth=max_depth)


def _coin_label(price: Mapping[str, Any]) -> str:
    price = _safe_dict(price)
    parts: List[str] = []
    for key, suffix in (("gold", "gold"), ("silver", "silver"), ("copper", "copper")):
        amount = _safe_int(price.get(key), 0)
        if amount:
            parts.append(f"{amount} {suffix}")
    return ", ".join(parts) if parts else "free"


def _offer_label(offer: Mapping[str, Any]) -> str:
    offer = _safe_dict(offer)
    label = _safe_str(offer.get("label") or offer.get("name") or offer.get("offer_id") or "offer").strip()
    description = _safe_str(offer.get("description")).strip()
    price = _coin_label(_safe_dict(offer.get("price")))
    if description:
        return f"{label} ({description}) — {price}"
    return f"{label} — {price}"


def _normalize_offer(offer: Mapping[str, Any]) -> Dict[str, Any]:
    offer = deepcopy(_safe_dict(offer))
    return {
        "offer_id": _safe_str(offer.get("offer_id")),
        "label": _safe_str(offer.get("label") or offer.get("name") or offer.get("offer_id") or "offer"),
        "description": _safe_str(offer.get("description")),
        "service_kind": _safe_str(offer.get("service_kind")),
        "provider_id": _safe_str(offer.get("provider_id")),
        "provider_name": _safe_str(offer.get("provider_name")),
        "price": _safe_dict(offer.get("price")),
        "availability": _safe_str(offer.get("availability") or "available"),
    }


def extract_service_offer_context(raw_result: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the most specific authoritative service offers found in a turn result."""
    candidates: List[Dict[str, Any]] = []
    for item in _walk(raw_result):
        service_result = _safe_dict(item.get("service_result"))
        if not service_result:
            continue
        offers = [_normalize_offer(row) for row in _safe_list(service_result.get("offers"))]
        offers = [row for row in offers if row.get("label") or row.get("offer_id")]
        if not offers:
            continue
        candidates.append({
            "provider_id": _safe_str(service_result.get("provider_id")),
            "provider_name": _safe_str(service_result.get("provider_name")) or _safe_str(offers[0].get("provider_name")),
            "service_kind": _safe_str(service_result.get("service_kind")) or _safe_str(offers[0].get("service_kind")),
            "status": _safe_str(service_result.get("status")),
            "offers": offers[:8],
            "source": COMMERCE_FOLLOWUP_SOURCE,
        })
    if not candidates:
        return {}
    candidates.sort(key=lambda row: (len(_safe_list(row.get("offers"))), bool(row.get("provider_name"))), reverse=True)
    return candidates[0]


def is_commerce_followup_question(player_input: str) -> bool:
    text = _safe_str(player_input).strip().lower()
    if not text:
        return False
    commerce_terms = (
        "what do you have",
        "what have you got",
        "what kind of provisions",
        "what provisions",
        "what food",
        "food for sale",
        "anything to eat",
        "menu",
        "serve",
        "served",
        "sell",
        "for sale",
    )
    if any(term in text for term in commerce_terms):
        return True
    # Covers terse follow-ups after an established service inquiry.
    if text in {"well?", "what?", "and?"}:
        return True
    if text.startswith("i ask") and "what" in text and "have" in text:
        return True
    return False


def format_service_offer_answer(context: Mapping[str, Any]) -> Dict[str, Any]:
    context = _safe_dict(context)
    offers = _safe_list(context.get("offers"))
    provider = _safe_str(context.get("provider_name") or "The merchant").strip() or "The merchant"
    if not offers:
        line = f"{provider} has no listed services available right now."
        return {
            "narration": line,
            "action": "No authoritative service offers are available to list.",
            "npc": {"speaker": provider, "line": "I do not have anything listed for sale right now."},
        }
    labels = [_offer_label(_safe_dict(row)) for row in offers]
    offer_sentence = "; ".join(labels)
    line = f"I can offer {offer_sentence}."
    return {
        "narration": f"{provider} lists the available provisions: {offer_sentence}.",
        "action": "Service inquiry answered from authoritative service offers.",
        "npc": {"speaker": provider, "line": line},
    }


def apply_commerce_followup_repair(
    turn_summary: Mapping[str, Any],
    *,
    player_input: str,
    last_offer_context: Mapping[str, Any],
) -> Dict[str, Any]:
    """Patch an interactive turn summary if it is a vague commerce follow-up."""
    out = deepcopy(_safe_dict(turn_summary))
    context = _safe_dict(last_offer_context)
    if not context or not is_commerce_followup_question(player_input):
        return out
    raw_result = _safe_dict(out.get("raw_result") or out.get("result"))
    current_context = extract_service_offer_context(raw_result)
    if current_context:
        return out

    answer = format_service_offer_answer(context)
    raw_result = deepcopy(raw_result)
    raw_result["narration"] = answer["narration"]
    raw_result["visible_interaction_reason"] = answer["action"]
    raw_result["npc"] = answer["npc"]
    raw_result["interactive_cli_commerce_followup"] = {
        "applied": True,
        "source": COMMERCE_FOLLOWUP_SOURCE,
        "offer_context": context,
    }
    contract = deepcopy(_safe_dict(raw_result.get("turn_contract")))
    contract["service_inquiry_followup"] = {
        "answered": True,
        "source": COMMERCE_FOLLOWUP_SOURCE,
        "service_result": context,
        "available_actions": [
            {
                "label": _offer_label(_safe_dict(offer)),
                "offer_id": _safe_str(_safe_dict(offer).get("offer_id")),
                "service_kind": _safe_str(_safe_dict(offer).get("service_kind")),
                "price": _safe_dict(_safe_dict(offer).get("price")),
            }
            for offer in _safe_list(context.get("offers"))
        ],
    }
    raw_result["turn_contract"] = contract

    out["raw_result"] = raw_result
    out["raw_narration"] = answer["narration"]
    out["raw_npc"] = answer["npc"]
    extracted = deepcopy(_safe_dict(out.get("extracted")))
    extracted["narration"] = answer["narration"]
    extracted["action"] = answer["action"]
    extracted["npc_speaker"] = _safe_str(answer["npc"].get("speaker"))
    extracted["npc_line"] = _safe_str(answer["npc"].get("line"))
    out["extracted"] = extracted
    out["narration_preview"] = answer["narration"]
    out["interactive_cli_commerce_followup"] = raw_result["interactive_cli_commerce_followup"]
    warnings = list(_safe_list(out.get("scenario_warnings")))
    warning = "interactive_cli_commerce_followup_answered_from_last_authoritative_service_offers"
    if warning not in warnings:
        warnings.append(warning)
    out["scenario_warnings"] = warnings
    return out
