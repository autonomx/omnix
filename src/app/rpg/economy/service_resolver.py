from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.economy.currency import (
    can_afford,
    format_currency,
    get_player_currency,
    negative_currency,
    normalize_currency,
)
from app.rpg.economy.service_registry import (
    SERVICE_KIND_DRINK,
    SERVICE_KIND_LODGING,
    SERVICE_KIND_MEAL,
    SERVICE_KIND_PAID_INFORMATION,
    SERVICE_KIND_REPAIR,
    SERVICE_KIND_SHOP_GOODS,
    SERVICE_KIND_TRAINING,
    SERVICE_KIND_TRANSPORT,
    find_provider_by_text,
    get_provider_offers,
    get_service_provider,
)
from app.rpg.economy.service_stock import filter_available_offers
from app.rpg.session.ambient_intent import (
    is_ambient_wait_or_listen_intent,
    is_room_context_ambient_not_lodging,
)
from app.rpg.world.location_registry import (
    current_location_id,
    has_explicit_location,
    location_allows_service,
    provider_present_at_location,
)


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _contains_any(text_l: str, terms: List[str]) -> bool:
    return any(term in text_l for term in terms)


def _not_service_result(reason: str, *, player_input: str = "") -> Dict[str, Any]:
    return {
        "matched": False,
        "kind": "not_service",
        "status": "not_service",
        "reason": reason,
        "player_input": player_input,
        "source": "deterministic_service_resolver",
    }


def _should_skip_service_resolution(player_input: str) -> str:
    if is_ambient_wait_or_listen_intent(player_input):
        return "ambient_wait_or_listen"
    if is_room_context_ambient_not_lodging(player_input):
        return "ambient_room_context_not_lodging"
    return ""


def _detect_service_kind(text_l: str) -> str:
    if _contains_any(
        text_l,
        [
            "room",
            "rent a room",
            "lodging",
            "bed",
            "stay the night",
            "sleep",
            "inn",
            "accommodation",
            "accommodations",
        ],
    ):
        return SERVICE_KIND_LODGING

    if _contains_any(
        text_l,
        [
            "food",
            "meal",
            "eat",
            "stew",
            "supper",
            "dinner",
            "breakfast",
            "lunch",
        ],
    ):
        return SERVICE_KIND_MEAL

    if _contains_any(
        text_l,
        [
            "drink",
            "ale",
            "beer",
            "wine",
            "mug",
        ],
    ):
        return SERVICE_KIND_DRINK

    if _contains_any(
        text_l,
        [
            "rumor",
            "rumour",
            "information",
            "news",
            "heard anything",
            "heard any",
            "gossip",
            "tip",
        ],
    ):
        return SERVICE_KIND_PAID_INFORMATION

    if _contains_any(
        text_l,
        [
            "repair",
            "fix my gear",
            "mend",
        ],
    ):
        return SERVICE_KIND_REPAIR

    if _contains_any(
        text_l,
        [
            "train",
            "training",
            "teach me",
            "lesson",
        ],
    ):
        return SERVICE_KIND_TRAINING

    if _contains_any(
        text_l,
        [
            "transport",
            "ride",
            "carriage",
            "boat",
            "ferry",
            "travel to",
        ],
    ):
        return SERVICE_KIND_TRANSPORT

    if _contains_any(
        text_l,
        [
            "buy",
            "sell",
            "sells",
            "shop",
            "goods",
            "wares",
            "torch",
            "rope",
        ],
    ):
        return SERVICE_KIND_SHOP_GOODS

    return ""


def _detect_kind(text_l: str) -> str:
    purchase_words = [
        "i buy",
        "buy ",
        "purchase",
        "pay for",
        "i pay",
        "rent the",
        "take the",
        "i'll take",
        "ill take",
    ]
    if _contains_any(text_l, purchase_words):
        return "service_purchase"
    return "service_inquiry"


def _offer_matches_purchase_text(offer: Dict[str, Any], text_l: str) -> bool:
    offer_id = _safe_str(offer.get("offer_id")).lower()
    label = _safe_str(offer.get("label")).lower()
    description = _safe_str(offer.get("description")).lower()

    if offer_id and offer_id in text_l:
        return True
    if label and label in text_l:
        return True

    # Friendly aliases for early starter-world items/services.
    aliases = {
        "bran_lodging_common_cot": ["common cot", "cot", "common room"],
        "bran_lodging_private_room": ["private room", "room"],
        "bran_meal_stew": ["stew", "food", "meal"],
        "bran_drink_ale": ["ale", "drink", "mug"],
        "bran_paid_rumor": ["rumor", "rumour", "information", "gossip"],
        "elara_torch": ["torch"],
        "elara_rope": ["rope"],
        "elara_paid_information": ["information", "rumor", "rumour"],
        "elara_basic_repair": ["repair", "fix"],
    }.get(offer_id, [])

    if any(alias in text_l for alias in aliases):
        return True

    return bool(description and description in text_l)


def _offer_location_allowed(offer: Dict[str, Any], simulation_state: Dict[str, Any]) -> bool:
    # Skip location filtering when no explicit location is set in the simulation state.
    if not has_explicit_location(simulation_state):
        return True

    availability_rules = _safe_dict(offer.get("availability_rules"))
    required_location = _safe_str(
        availability_rules.get("requires_location")
        or offer.get("location_id")
    )
    if required_location and current_location_id(simulation_state) != required_location:
        return False

    service_kind = _safe_str(offer.get("service_kind"))
    if service_kind and not location_allows_service(simulation_state, service_kind):
        return False

    provider_id = _safe_str(offer.get("provider_id"))
    provider_name = _safe_str(offer.get("provider_name"))
    if provider_id or provider_name:
        return provider_present_at_location(
            simulation_state,
            provider_id=provider_id,
            provider_name=provider_name,
        )

    return True


def _filter_offers_for_current_location(
    offers: List[Dict[str, Any]],
    simulation_state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return [
        offer
        for offer in offers
        if _offer_location_allowed(_safe_dict(offer), simulation_state)
    ]


def resolve_service_intent(
    player_input: str,
    action: Dict[str, Any] | None = None,
    simulation_state: Dict[str, Any] | None = None,
    runtime_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    text = _safe_str(player_input)
    text_l = text.lower()
    action = _safe_dict(action)

    service_kind = _detect_service_kind(text_l)
    if not service_kind:
        return {
            "matched": False,
            "kind": "",
            "service_kind": "",
            "provider_id": "",
            "provider_name": "",
            "confidence": 0.0,
            "source": "deterministic_service_resolver",
        }

    provider = find_provider_by_text(text_l)
    if not provider:
        return {
            "matched": False,
            "kind": "",
            "service_kind": service_kind,
            "provider_id": "",
            "provider_name": "",
            "confidence": 0.0,
            "source": "deterministic_service_resolver",
        }

    provider_id = _safe_str(provider.get("provider_id"))
    provider_name = _safe_str(provider.get("provider_name") or provider_id)
    kind = _detect_kind(text_l)

    return {
        "matched": True,
        "kind": kind,
        "service_kind": service_kind,
        "provider_id": provider_id,
        "provider_name": provider_name,
        "location_id": _safe_str(provider.get("location_id")),
        "confidence": 0.95,
        "source": "deterministic_service_resolver",
    }


def _build_available_actions(service_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    provider_name = _safe_str(service_result.get("provider_name"))

    for offer in _safe_list(service_result.get("offers")):
        offer = _safe_dict(offer)
        offer_id = _safe_str(offer.get("offer_id"))
        label = _safe_str(offer.get("label") or offer_id)
        price = normalize_currency(offer.get("price"))
        actions.append(
            {
                "action_id": f"service:purchase:{offer_id}",
                "label": f"{label} — {format_currency(price)}",
                "command": f"I buy {label} from {provider_name}".strip(),
                "service_kind": _safe_str(offer.get("service_kind")),
                "provider_id": _safe_str(service_result.get("provider_id")),
                "offer_id": offer_id,
                "price": price,
            }
        )

    return actions


def resolve_service_turn(
    *,
    player_input: str,
    action: Dict[str, Any] | None,
    resolved_action: Dict[str, Any] | None,
    simulation_state: Dict[str, Any] | None,
    runtime_state: Dict[str, Any] | None,
) -> Dict[str, Any]:
    skip_reason = _should_skip_service_resolution(player_input)
    if skip_reason:
        return _not_service_result(skip_reason, player_input=player_input)

    simulation_state = _safe_dict(simulation_state)
    intent = resolve_service_intent(
        player_input=player_input,
        action=_safe_dict(action),
        simulation_state=simulation_state,
        runtime_state=_safe_dict(runtime_state),
    )
    if not intent.get("matched"):
        return {
            "matched": False,
            "kind": "",
            "service_kind": _safe_str(intent.get("service_kind")),
            "provider_id": "",
            "provider_name": "",
            "status": "not_service",
            "offers": [],
            "selected_offer_id": "",
            "purchase": None,
            "available_actions": [],
            "source": "deterministic_service_resolver",
        }

    provider_id = _safe_str(intent.get("provider_id"))
    service_kind = _safe_str(intent.get("service_kind"))
    kind = _safe_str(intent.get("kind"))
    provider = get_service_provider(provider_id)
    offers = filter_available_offers(
        simulation_state,
        get_provider_offers(provider_id, service_kind),
        provider=provider,
    )
    offers = _filter_offers_for_current_location(offers, simulation_state)

    # If all offers were removed by location filtering, the service is not available here.
    if not offers and provider_id and has_explicit_location(simulation_state):
        all_provider_offers = get_provider_offers(provider_id, service_kind)
        if all_provider_offers:
            # The provider has offers but none are available at the current location.
            return {
                "matched": False,
                "kind": kind,
                "service_kind": service_kind,
                "provider_id": provider_id,
                "provider_name": _safe_str(intent.get("provider_name")),
                "location_id": _safe_str(intent.get("location_id")),
                "current_location_id": current_location_id(simulation_state),
                "status": "provider_not_at_current_location",
                "offers": [],
                "selected_offer_id": "",
                "purchase": None,
                "available_actions": [],
                "source": "deterministic_service_resolver",
            }

    player_currency = get_player_currency(simulation_state)

    result: Dict[str, Any] = {
        "matched": True,
        "kind": kind,
        "service_kind": service_kind,
        "provider_id": provider_id,
        "provider_name": _safe_str(intent.get("provider_name")),
        "location_id": _safe_str(intent.get("location_id")),
        "current_location_id": current_location_id(simulation_state),
        "status": "offers_available" if offers else "no_registered_offers",
        "offers": offers,
        "selected_offer_id": "",
        "purchase": None,
        "player_currency": player_currency,
        "available_actions": [],
        "source": "deterministic_service_resolver",
    }

    if kind == "service_purchase":
        text_l = _safe_str(player_input).lower()
        selected = {}
        for offer in offers:
            if _offer_matches_purchase_text(_safe_dict(offer), text_l):
                selected = _safe_dict(offer)
                break

        if selected:
            price = normalize_currency(selected.get("price"))
            afford = can_afford(player_currency, price)
            result["selected_offer_id"] = _safe_str(selected.get("offer_id"))
            result["status"] = "purchase_ready" if afford else "blocked"
            result["purchase"] = {
                "blocked": not afford,
                "blocked_reason": "" if afford else "insufficient_funds",
                "price": price,
                "can_afford": afford,
                "applied": False,
                "resource_changes": {
                    "currency": negative_currency(price) if afford else {"gold": 0, "silver": 0, "copper": 0}
                },
                "effects": _safe_dict(selected.get("effects")) if afford else {},
                "note": "Purchase intent resolved deterministically; runtime applies mutation.",
            }
        else:
            result["status"] = "purchase_offer_not_found"
            result["purchase"] = {
                "blocked": True,
                "blocked_reason": "offer_not_found",
                "price": {"gold": 0, "silver": 0, "copper": 0},
                "can_afford": False,
                "applied": False,
                "resource_changes": {"currency": {"gold": 0, "silver": 0, "copper": 0}},
                "effects": {},
                "note": "No matching deterministic offer was found.",
            }

    result["available_actions"] = _build_available_actions(result)
    return result

# N116.19 — Root Service Resolver Precision
# The deterministic service resolver must not treat document/order/payment
# evidence as tavern services.  This is a negative guard only: it returns
# ``not_service`` for service-confusable evidence phrases unless the player
# explicitly asks to buy/rent/order/pay for a real service.

_N11619_PREVIOUS_RESOLVE_SERVICE_INTENT = resolve_service_intent
_N11619_PREVIOUS_RESOLVE_SERVICE_TURN = resolve_service_turn

_N11619_STRONG_DOCUMENT_SERVICE_FALSE_POSITIVE_TERMS = (
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
_N11619_DOCUMENT_CONTEXT_TERMS = (
    "document", "documents", "paper", "papers", "letter", "letters",
    "note", "notes", "record", "records", "file", "files", "cipher",
    "code", "marks", "markings", "seal", "sealed", "ledger", "manifest",
)
_N11619_EVIDENCE_VERBS = (
    "inspect", "study", "review", "decode", "trace", "capture", "recover",
    "report", "compare", "analyze", "analyse", "examine", "read", "copy",
    "secure", "protect", "warn", "follow", "bring", "show", "present",
    "search", "find", "identify", "check",
)
_N11619_EXPLICIT_SERVICE_COMMERCE_TERMS = (
    "buy", "purchase", "pay for", "pay bran for", "pay the innkeeper for",
    "rent a room", "rent room", "book a room", "book room", "order ale",
    "order a drink", "order food", "order a meal", "order stew",
    "order supper", "buy ale", "buy food", "buy meal", "buy stew",
    "sell", "trade", "hire", "lodging", "sleep here", "rest here",
    "stay the night",
)


def _n11619_norm_service_text(value: Any) -> str:
    return " ".join(_safe_str(value).lower().replace("-", " ").replace("_", " ").split())


def _n11619_has_explicit_service_or_commerce(text_l: str) -> bool:
    text_l = _n11619_norm_service_text(text_l)
    if not text_l:
        return False
    return any(term in text_l for term in _N11619_EXPLICIT_SERVICE_COMMERCE_TERMS)


def _n11619_is_document_service_false_positive_text(text_l: str) -> bool:
    text_l = _n11619_norm_service_text(text_l)
    if not text_l:
        return False
    if _n11619_has_explicit_service_or_commerce(text_l):
        return False
    if any(term in text_l for term in _N11619_STRONG_DOCUMENT_SERVICE_FALSE_POSITIVE_TERMS):
        return True
    has_context = any(term in text_l for term in _N11619_DOCUMENT_CONTEXT_TERMS)
    has_verb = any(verb in text_l for verb in _N11619_EVIDENCE_VERBS)
    return bool(has_context and has_verb)


def _n11619_not_service_precision_result(player_input: str, *, service_kind: str = "") -> Dict[str, Any]:
    return {
        "matched": False,
        "kind": "not_service",
        "service_kind": service_kind,
        "provider_id": "",
        "provider_name": "",
        "status": "not_service",
        "offers": [],
        "selected_offer_id": "",
        "purchase": None,
        "available_actions": [],
        "confidence": 0.0,
        "reason": "document_evidence_without_explicit_service_request",
        "player_input": player_input,
        "source": "deterministic_service_resolver",
        "n11619_root_service_precision_guard": True,
        "veto_only": True,
    }


def resolve_service_intent(
    player_input: str,
    action: Dict[str, Any] | None = None,
    simulation_state: Dict[str, Any] | None = None,
    runtime_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    text = _safe_str(player_input)
    text_l = _n11619_norm_service_text(text)
    if _n11619_is_document_service_false_positive_text(text_l):
        return _n11619_not_service_precision_result(text)
    return _N11619_PREVIOUS_RESOLVE_SERVICE_INTENT(
        player_input=player_input,
        action=action,
        simulation_state=simulation_state,
        runtime_state=runtime_state,
    )


def resolve_service_turn(
    *,
    player_input: str,
    action: Dict[str, Any] | None,
    resolved_action: Dict[str, Any] | None,
    simulation_state: Dict[str, Any] | None,
    runtime_state: Dict[str, Any] | None,
) -> Dict[str, Any]:
    text = _safe_str(player_input)
    if _n11619_is_document_service_false_positive_text(text):
        return _n11619_not_service_precision_result(text)
    return _N11619_PREVIOUS_RESOLVE_SERVICE_TURN(
        player_input=player_input,
        action=action,
        resolved_action=resolved_action,
        simulation_state=simulation_state,
        runtime_state=runtime_state,
    )
