"""CA.1/CA.2/CB.2 — deterministic commerce repair for interactive CLI runs.

The runtime can correctly surface a service inquiry such as Bran's meal offer,
but player-facing narration may omit the concrete offer list, or later follow-ups
like "how much for bread?" may be routed as plain talk/observe and lose the
service context.  CB.2 also covers purchase attempts like "I'll buy a hot stew"
when the runtime fails to match the authoritative offer.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping

from app.rpg.economy.currency import can_afford, get_player_currency, negative_currency, normalize_currency
from app.rpg.session.survival_actions import resolve_survival_action

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


def infer_requested_service_kind(player_input: str) -> str:
    text = _safe_str(player_input).strip().lower()
    food_terms = ("food", "meal", "bread", "stew", "strew", "provision", "provisions", "eat", "supper", "dinner", "breakfast")
    drink_terms = ("drink", "ale", "beer", "wine", "water", "mug")
    lodging_terms = ("room", "bed", "lodging", "sleep", "stay", "rent")
    if any(term in text for term in food_terms):
        return "meal"
    if any(term in text for term in drink_terms):
        return "drink"
    if any(term in text for term in lodging_terms):
        return "lodging"
    return ""


def is_purchase_intent(player_input: str) -> bool:
    text = _safe_str(player_input).strip().lower()
    purchase_terms = (
        "i'll buy",
        "ill buy",
        "i will buy",
        "i buy",
        "buy a",
        "buy the",
        "buy hot",
        "purchase",
        "pay for",
        "give me",
        "get me",
        "i want to buy",
        "i'd like to buy",
        "id like to buy",
        "take my coin",
    )
    return any(term in text for term in purchase_terms)


def is_purchase_confirmation(player_input: str) -> bool:
    text = _safe_str(player_input).strip().lower()
    confirmation_terms = (
        "confirm",
        "confirmed",
        "here you go",
        "take my coin",
        "take the coin",
        "i pay",
        "paid",
        "payment",
        "yes",
        "ok, give it",
        "okay, give it",
    )
    if any(term in text for term in confirmation_terms):
        return True
    return bool(("silver" in text or "copper" in text or "gold" in text) and "purchase" in text)


def _context_matches_request(context: Mapping[str, Any], requested_kind: str) -> bool:
    context = _safe_dict(context)
    if not context:
        return False
    if not requested_kind:
        return True
    service_kind = _safe_str(context.get("service_kind")).strip().lower()
    if service_kind == requested_kind:
        return True
    for offer in _safe_list(context.get("offers")):
        offer = _safe_dict(offer)
        if _safe_str(offer.get("service_kind")).strip().lower() == requested_kind:
            return True
    return False


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
        "bread for sale",
        "anything to eat",
        "how much",
        "cost",
        "price",
        "prices",
        "menu",
        "serve",
        "served",
        "sell",
        "for sale",
    )
    if any(term in text for term in commerce_terms):
        return True
    if is_purchase_intent(text):
        return True
    if is_purchase_confirmation(text):
        return True
    if infer_requested_service_kind(text) and any(term in text for term in ("have", "got", "available", "offer")):
        return True
    if text in {"well?", "what?", "and?"}:
        return True
    if text.startswith("i ask") and "what" in text and "have" in text:
        return True
    return False


def format_service_offer_answer(context: Mapping[str, Any], *, purchase: bool = False) -> Dict[str, Any]:
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
    if purchase:
        line = f"I can sell you {offer_sentence}. Confirm the purchase and I will take the listed price."
        return {
            "narration": f"{provider} matches your purchase request to the available offer: {offer_sentence}.",
            "action": "Purchase intent matched to authoritative service offer; awaiting/confirming deterministic purchase resolution.",
            "npc": {"speaker": provider, "line": line},
        }
    line = f"I can offer {offer_sentence}."
    return {
        "narration": f"{provider} lists the available provisions: {offer_sentence}.",
        "action": "Service inquiry answered from authoritative service offers.",
        "npc": {"speaker": provider, "line": line},
    }


def _select_offer_for_purchase(context: Mapping[str, Any], player_input: str) -> Dict[str, Any]:
    offers = [_safe_dict(row) for row in _safe_list(_safe_dict(context).get("offers"))]
    if not offers:
        return {}
    text = _safe_str(player_input).lower()
    for offer in offers:
        haystack = " ".join(
            _safe_str(value).lower()
            for value in (
                offer.get("offer_id"),
                offer.get("label"),
                offer.get("name"),
                offer.get("description"),
                offer.get("service_kind"),
            )
            if _safe_str(value)
        )
        parts = [
            part
            for part in haystack.split()
            if len(part) > 2 and part not in {"the", "and", "for", "with"}
        ]
        if parts and any(part in text for part in parts):
            return offer
    if len(offers) == 1:
        return offers[0]
    return {}


def _extract_simulation_state(raw_result: Mapping[str, Any]) -> Dict[str, Any]:
    raw_result = _safe_dict(raw_result)
    candidates = [
        raw_result.get("simulation_state"),
        _safe_dict(raw_result.get("result")).get("simulation_state"),
        _safe_dict(raw_result.get("session")).get("simulation_state"),
        _safe_dict(_safe_dict(raw_result.get("session")).get("state")).get("simulation_state"),
        _safe_dict(_safe_dict(_safe_dict(raw_result.get("session")).get("setup_payload")).get("metadata")).get("simulation_state"),
    ]
    for candidate in candidates:
        candidate = _safe_dict(candidate)
        if candidate:
            return candidate
    return {}


def _sync_simulation_state(raw_result: Dict[str, Any], simulation_state: Mapping[str, Any]) -> None:
    simulation_state = _safe_dict(simulation_state)
    if not simulation_state:
        return
    raw_result["simulation_state"] = simulation_state
    session = _safe_dict(raw_result.get("session"))
    if session:
        session["simulation_state"] = simulation_state
        state = _safe_dict(session.get("state"))
        state["simulation_state"] = simulation_state
        state["player_state"] = deepcopy(_safe_dict(simulation_state.get("player_state")))
        state["climate_survival"] = deepcopy(_safe_dict(simulation_state.get("climate_survival")))
        session["state"] = state
        setup_payload = _safe_dict(session.get("setup_payload"))
        metadata = _safe_dict(setup_payload.get("metadata"))
        metadata["simulation_state"] = simulation_state
        metadata["player_state"] = deepcopy(_safe_dict(simulation_state.get("player_state")))
        metadata["climate_survival"] = deepcopy(_safe_dict(simulation_state.get("climate_survival")))
        setup_payload["metadata"] = metadata
        session["setup_payload"] = setup_payload
        raw_result["session"] = session


def _persist_session_from_result(raw_result: Mapping[str, Any], session_id: str) -> str:
    session_id = _safe_str(session_id).strip()
    session = deepcopy(_safe_dict(_safe_dict(raw_result).get("session")))
    if not session_id or not session:
        return ""
    session["id"] = session_id
    session["session_id"] = session_id
    manifest = _safe_dict(session.get("manifest"))
    manifest["id"] = session_id
    manifest["session_id"] = session_id
    session["manifest"] = manifest
    try:
        from app.rpg.session.service import save_session

        save_session(session)
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return ""


def _build_confirmed_purchase_result(
    *,
    context: Mapping[str, Any],
    offer: Mapping[str, Any],
    player_input: str,
    simulation_state: Dict[str, Any],
) -> Dict[str, Any]:
    context = _safe_dict(context)
    offer = deepcopy(_safe_dict(offer))
    price = normalize_currency(offer.get("price"))
    wallet = get_player_currency(simulation_state)
    afford = can_afford(wallet, price)
    service_result = {
        "matched": True,
        "kind": "service_purchase",
        "service_kind": _safe_str(offer.get("service_kind") or context.get("service_kind")),
        "provider_id": _safe_str(offer.get("provider_id") or context.get("provider_id")),
        "provider_name": _safe_str(offer.get("provider_name") or context.get("provider_name")),
        "status": "purchase_ready" if afford else "blocked",
        "offers": [offer],
        "selected_offer_id": _safe_str(offer.get("offer_id")),
        "player_currency": wallet,
        "available_actions": [],
        "source": COMMERCE_FOLLOWUP_SOURCE,
        "purchase": {
            "blocked": not afford,
            "blocked_reason": "" if afford else "insufficient_funds",
            "price": price,
            "can_afford": afford,
            "applied": False,
            "resource_changes": {"currency": negative_currency(price) if afford else {"gold": 0, "silver": 0, "copper": 0}},
            "effects": _safe_dict(offer.get("effects")) if afford else {},
            "note": "Purchase confirmation resolved from authoritative interactive service offer.",
        },
    }
    survival_result = {}
    if simulation_state:
        survival_result = resolve_survival_action(
            player_input=player_input,
            simulation_state=simulation_state,
            service_result=service_result,
        )
    applied = bool(_safe_dict(survival_result).get("applied"))
    if applied:
        service_result["status"] = "purchased"
        service_result["purchase"]["applied"] = True
        service_result["purchase"]["blocked"] = False
        service_result["purchase"]["blocked_reason"] = ""
        service_result["purchase"]["survival_action"] = survival_result
    else:
        blocked_reason = _safe_str(_safe_dict(survival_result).get("blocked_reason") or service_result["purchase"].get("blocked_reason") or "purchase_not_applied")
        service_result["status"] = "blocked"
        service_result["purchase"]["blocked"] = True
        service_result["purchase"]["blocked_reason"] = blocked_reason
        service_result["purchase"]["survival_action"] = survival_result
    return {"service_result": service_result, "survival_action": survival_result}


def _select_context_for_question(
    *,
    player_input: str,
    current_context: Mapping[str, Any],
    last_offer_context: Mapping[str, Any],
) -> Dict[str, Any]:
    requested_kind = infer_requested_service_kind(player_input)
    current_context = _safe_dict(current_context)
    last_offer_context = _safe_dict(last_offer_context)
    if _context_matches_request(current_context, requested_kind):
        return current_context
    if _context_matches_request(last_offer_context, requested_kind):
        return last_offer_context
    if current_context and not requested_kind:
        return current_context
    return last_offer_context or current_context


def apply_commerce_followup_repair(
    turn_summary: Mapping[str, Any],
    *,
    player_input: str,
    last_offer_context: Mapping[str, Any],
    persist_session_id: str = "",
) -> Dict[str, Any]:
    """Patch an interactive turn summary if it is a commerce/service question or purchase attempt."""
    out = deepcopy(_safe_dict(turn_summary))
    if not is_commerce_followup_question(player_input):
        return out
    raw_result = _safe_dict(out.get("raw_result") or out.get("result"))
    current_context = extract_service_offer_context(raw_result)
    context = _select_context_for_question(
        player_input=player_input,
        current_context=current_context,
        last_offer_context=last_offer_context,
    )
    if not context:
        return out

    confirmed_purchase = is_purchase_confirmation(player_input)
    purchase = is_purchase_intent(player_input) or confirmed_purchase
    selected_offer = _select_offer_for_purchase(context, player_input) if confirmed_purchase else {}
    purchase_resolution: Dict[str, Any] = {}
    answer = format_service_offer_answer(context, purchase=purchase)
    raw_result = deepcopy(raw_result)
    if confirmed_purchase and selected_offer:
        simulation_state = _extract_simulation_state(raw_result)
        purchase_resolution = _build_confirmed_purchase_result(
            context=context,
            offer=selected_offer,
            player_input=player_input,
            simulation_state=simulation_state,
        )
        service_result = _safe_dict(purchase_resolution.get("service_result"))
        purchase_payload = _safe_dict(service_result.get("purchase"))
        provider = _safe_str(context.get("provider_name") or "The merchant").strip() or "The merchant"
        offer_label = _offer_label(selected_offer)
        if purchase_payload.get("applied"):
            answer = {
                "narration": f"{provider} takes the listed price and serves {offer_label}.",
                "action": "Purchase confirmation resolved against authoritative service offer.",
                "npc": {"speaker": provider, "line": "Here you are. Hot and ready."},
            }
        else:
            reason = _safe_str(purchase_payload.get("blocked_reason") or "purchase_not_applied")
            answer = {
                "narration": f"{provider} cannot complete the purchase of {offer_label}: {reason}.",
                "action": "Purchase confirmation matched authoritative service offer but did not apply.",
                "npc": {"speaker": provider, "line": "I cannot complete that purchase yet."},
            }
        if simulation_state:
            _sync_simulation_state(raw_result, simulation_state)
        persist_error = _persist_session_from_result(raw_result, persist_session_id)
        if persist_error:
            purchase_resolution["persist_error"] = persist_error

    raw_result["narration"] = answer["narration"]
    raw_result["visible_interaction_reason"] = answer["action"]
    raw_result["npc"] = answer["npc"]
    raw_result["interactive_cli_commerce_followup"] = {
        "applied": True,
        "source": COMMERCE_FOLLOWUP_SOURCE,
        "offer_context": context,
        "requested_service_kind": infer_requested_service_kind(player_input),
        "current_context_service_kind": _safe_str(current_context.get("service_kind")),
        "purchase_intent": purchase,
        "purchase_confirmation": confirmed_purchase,
        "selected_offer_id": _safe_str(selected_offer.get("offer_id")),
    }
    contract = deepcopy(_safe_dict(raw_result.get("turn_contract")))
    if purchase_resolution:
        service_result = _safe_dict(purchase_resolution.get("service_result"))
        survival_action = _safe_dict(purchase_resolution.get("survival_action"))
        contract["service_result"] = service_result
        resolved_action = deepcopy(_safe_dict(contract.get("resolved_action")))
        resolved_action["service_result"] = service_result
        if survival_action:
            resolved_action["survival_action"] = survival_action
            contract["survival_action"] = survival_action
            contract["resource_changes"] = _safe_dict(survival_action.get("resource_changes"))
            contract["effect_result"] = _safe_dict(survival_action.get("effect_result"))
        contract["resolved_action"] = resolved_action
        raw_result["service_result"] = service_result
        raw_result["survival_action"] = survival_action
        raw_result["interactive_cli_purchase_resolution"] = purchase_resolution
    contract["service_inquiry_followup"] = {
        "answered": True,
        "purchase_intent": purchase,
        "purchase_confirmation": confirmed_purchase,
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
    warning = "interactive_cli_commerce_followup_answered_from_authoritative_service_offers"
    if purchase:
        warning = "interactive_cli_purchase_intent_matched_to_authoritative_service_offer"
    if warning not in warnings:
        warnings.append(warning)
    if confirmed_purchase:
        confirm_warning = "interactive_cli_purchase_confirmation_resolved_from_authoritative_service_offer"
        if confirm_warning not in warnings:
            warnings.append(confirm_warning)
    persist_error = _safe_str(purchase_resolution.get("persist_error"))
    if persist_error:
        warnings.append("interactive_cli_purchase_confirmation_persist_failed:" + persist_error)
    out["scenario_warnings"] = warnings
    return out
