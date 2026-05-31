"""Split helpers for RPG world scene narration."""
from __future__ import annotations

# ruff: noqa: F401,F403,F405
from app.rpg.ai.world_scene_narrator_common import *
from app.rpg.ai.world_scene_narrator_dialogue_grounding import *

def _travel_result_from_context(narration_context: Dict[str, Any]) -> Dict[str, Any]:
    narration_context = _safe_dict(narration_context)
    resolved = _safe_dict(narration_context.get("resolved_result"))
    travel = _safe_dict(resolved.get("travel_result"))
    if travel:
        return travel
    turn_contract = _safe_dict(narration_context.get("turn_contract"))
    resolved = _safe_dict(turn_contract.get("resolved_result") or turn_contract.get("resolved_action"))
    return _safe_dict(resolved.get("travel_result"))


def _grounded_travel_narration(narration_context: Dict[str, Any]) -> str:
    travel = _travel_result_from_context(narration_context)
    if not travel.get("matched"):
        return ""
    if not travel.get("applied"):
        exits = _safe_dict(travel.get("available_exits"))
        if exits:
            return "No clear route matches that destination from here."
        return "There is no available route from here."
    to_location = _safe_dict(travel.get("to_location"))
    name = _safe_str(to_location.get("name") or travel.get("to_location_id"))
    return f"You arrive at {name}."


def _grounded_travel_action(narration_context: Dict[str, Any]) -> str:
    travel = _travel_result_from_context(narration_context)
    if not travel.get("matched"):
        return ""
    if travel.get("applied"):
        to_location = _safe_dict(travel.get("to_location"))
        name = _safe_str(to_location.get("name") or travel.get("to_location_id"))
        return f"You travel to {name}."
    return "No available route matches that destination."


def _final_grounded_service_action_text(
    action_text: str,
    narration_context: Dict[str, Any],
) -> str:
    """Final authority pass for Result/action text.

    This runs after generic sanitization because phrases like
    "The attempt fails." can be introduced late by fallback cleanup. Service
    purchase failures must remain specific and deterministic.
    """
    service_result = _service_result_from_context(narration_context)
    if not service_result.get("matched"):
        return action_text

    if _safe_str(service_result.get("kind")) != "service_purchase":
        return action_text

    purchase = _safe_dict(service_result.get("purchase"))
    service_application = _safe_dict(narration_context.get("service_application"))
    status = _safe_str(service_result.get("status"))
    blocked_reason = _safe_str(
        service_application.get("blocked_reason")
        or purchase.get("blocked_reason")
    )

    if status == "blocked" or blocked_reason == "insufficient_funds":
        grounded = _service_grounded_action_result(narration_context)
        if grounded:
            return grounded

    if status == "purchase_offer_not_found" or blocked_reason == "offer_not_found":
        grounded = _service_grounded_action_result(narration_context)
        if grounded:
            return grounded

    generic = _safe_str(action_text).strip().lower()
    if generic in {
        "the attempt fails",
        "the attempt fails.",
        "you fail",
        "you fail.",
        "it fails",
        "it fails.",
    }:
        grounded = _service_grounded_action_result(narration_context)
        if grounded:
            return grounded

    return action_text


def _service_grounded_action_result(narration_context: Dict[str, Any]) -> str:
    service_result = _service_result_from_context(narration_context)
    if not service_result:
        return ""

    provider_name = _safe_str(service_result.get("provider_name") or "The provider").strip()
    kind = _safe_str(service_result.get("kind"))
    status = _safe_str(service_result.get("status"))

    if kind == "service_purchase":
        purchase = _safe_dict(service_result.get("purchase"))
        service_application = _safe_dict(narration_context.get("service_application"))
        blocked_reason = _safe_str(
            service_application.get("blocked_reason")
            or purchase.get("blocked_reason")
        )

        if status == "purchase_offer_not_found" or blocked_reason == "offer_not_found":
            if provider_name:
                return f"{provider_name} cannot find a matching available offer."
            return "No matching available offer is available."

        purchase_applied = (
            _safe_str(service_result.get("status")) == "purchased"
            or bool(purchase.get("applied"))
            or bool(service_application.get("applied"))
        )

        if purchase_applied:
            return f"{provider_name} completes the purchase."
        if status == "purchase_ready":
            return f"{provider_name} is ready to complete the purchase."
        if status == "blocked" or blocked_reason == "insufficient_funds":
            return f"{provider_name} names the price, but you do not have enough coin."

    if status == "offers_available":
        return f"{provider_name} checks the available options."

    if status == "no_registered_offers":
        return f"{provider_name} has no available offer for that request."

    return f"{provider_name} considers the service request."


def _service_grounded_npc_line(narration_context: Dict[str, Any]) -> str:
    service_result = _service_result_from_context(narration_context)
    if not service_result:
        return ""

    kind = _safe_str(service_result.get("kind"))
    status = _safe_str(service_result.get("status"))
    offers = [_safe_dict(offer) for offer in _safe_list(service_result.get("offers"))]

    if kind == "service_purchase":
        purchase = _safe_dict(service_result.get("purchase"))
        service_application = _safe_dict(narration_context.get("service_application"))
        blocked_reason = _safe_str(
            service_application.get("blocked_reason")
            or purchase.get("blocked_reason")
        )

        if status == "purchase_offer_not_found" or blocked_reason == "offer_not_found":
            return "I do not have that listed among my available offers."

        purchase_applied = (
            _safe_str(service_result.get("status")) == "purchased"
            or bool(purchase.get("applied"))
            or bool(service_application.get("applied"))
        )
        selected_offer_id = _safe_str(service_result.get("selected_offer_id"))
        selected = {}
        for offer in offers:
            if _safe_str(offer.get("offer_id")) == selected_offer_id:
                selected = offer
                break

        selected_label = _safe_str(selected.get("label") or selected_offer_id or "that").strip()

        if purchase_applied:
            if selected_label and selected_label != "that":
                return f"Done. {selected_label} is settled."
            return "Done. The purchase is settled."

        if status == "purchase_ready":
            return f"I can settle {selected_label} once you confirm the purchase."

        if status == "blocked":
            price = _safe_dict(purchase.get("price"))
            price_text = _service_offer_label_with_price({"label": selected_label, "price": price})
            return f"{price_text} is the price, but you do not have enough coin."

    if status == "offers_available" and offers:
        offer_texts = [_service_offer_label_with_price(offer) for offer in offers]
        joined = _join_natural(offer_texts)
        if joined:
            return f"I can offer {joined}."

    if status == "no_registered_offers":
        return "I do not have an available offer for that right now."

    return "Let me check what I can offer before we settle the details."


def _normalized_text_for_compare(value: Any) -> str:
    text = _safe_str(value).strip().lower()
    return " ".join(text.split())


def _fallback_non_service_narration(narration_context: Dict[str, Any]) -> str:
    narration_context = _safe_dict(narration_context)
    player_input = _safe_str(narration_context.get("player_input"))
    turn_contract = _safe_dict(narration_context.get("turn_contract"))
    resolved = _safe_dict(
        narration_context.get("resolved_result")
        or turn_contract.get("resolved_result")
        or turn_contract.get("resolved_action")
    )
    action_type = _safe_str(resolved.get("action_type") or _safe_dict(turn_contract.get("action")).get("action_type"))
    target_name = _safe_str(resolved.get("target_name") or _safe_dict(turn_contract.get("action")).get("target_name"))
    outcome = _safe_str(resolved.get("outcome"))

    if target_name and action_type in {"social_activity", "persuade", "investigate"}:
        if outcome == "success":
            return f"{target_name} gives the request their attention and responds."
        if outcome == "partial":
            return f"{target_name} considers the request, but the answer comes with some uncertainty."
        return f"{target_name} considers the request."

    if action_type:
        return "The action resolves against the current situation."

    if player_input:
        return "The moment shifts in response to your action."

    return "The scene continues."


def _sanitize_repeated_player_input_narration(
    payload: Dict[str, Any],
    narration_context: Dict[str, Any],
) -> None:
    narration = _safe_str(payload.get("narration"))
    player_input = _safe_str(narration_context.get("player_input"))
    if not narration or not player_input:
        return

    if _normalized_text_for_compare(narration) == _normalized_text_for_compare(player_input):
        payload["narration"] = _fallback_non_service_narration(narration_context)


def _naturalize_service_debug_language(text: str) -> str:
    text = _safe_str(text)
    if not text:
        return text
    replacements = {
        "registered shop goods options": "available goods",
        "registered lodging options": "available lodging options",
        "registered meal options": "available meal options",
        "registered paid information options": "available information options",
        "registered repair options": "available repair options",
        "registered offers": "available offers",
        "registered offer": "available offer",
        "Registered shop goods options": "available goods",
        "Registered lodging options": "available lodging options",
        "Registered meal options": "available meal options",
        "Registered paid information options": "available information options",
        "Registered repair options": "available repair options",
        "Registered offers": "available offers",
        "Registered offer": "available offer",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _service_grounded_narration_text(narration_context: Dict[str, Any]) -> str:
    service_result = _service_result_from_context(narration_context)
    if not service_result:
        return ""

    provider_name = _safe_str(service_result.get("provider_name") or "The provider").strip()
    service_kind = _safe_str(service_result.get("service_kind")).replace("_", " ").strip()
    status = _safe_str(service_result.get("status"))
    purchase = _safe_dict(service_result.get("purchase"))
    service_application = _safe_dict(narration_context.get("service_application"))
    blocked_reason = _safe_str(
        service_application.get("blocked_reason")
        or purchase.get("blocked_reason")
    )

    if (
        _safe_str(service_result.get("kind")) == "service_purchase"
        and (
            status == "purchase_offer_not_found"
            or blocked_reason == "offer_not_found"
        )
    ):
        return f"{provider_name} checks the available offers and finds no matching item or service."

    if status == "offers_available":
        if service_kind:
            return f"{provider_name} looks over the available {service_kind} options."
        return f"{provider_name} looks over the available options."

    if status == "offers_available":
        if service_kind:
            return f"{provider_name} looks over the registered {service_kind} options."
        return f"{provider_name} looks over the registered service options."

    if status == "blocked":
        return f"{provider_name} checks the available offer and current coin, then finds the purchase cannot be completed."

    if status == "purchased":
        return f"{provider_name} completes the registered service purchase."

    if status == "purchase_ready":
        return f"{provider_name} confirms the selected available offer."

    return f"{provider_name} considers the service request."


def _service_narration_needs_grounding(text: str) -> bool:
    lower = _safe_str(text).lower()
    if not lower:
        return False

    repeated_action_phrases = (
        "as you ask",
        "you ask",
        "you asked",
        "you inquire",
        "you inquired",
        "about a room",
        "room to rent",
        "what she sells",
        "heard any rumors",
        "buy a torch",
        "from elara",
        "from bran",
        "request for lodging",
        "seeking shelter",
        "seeking lodging",
        "as you address",
        "address bran",
        "travelers seeking shelter",
    )
    return any(phrase in lower for phrase in repeated_action_phrases)


def _service_claim_needs_grounding(text: str) -> bool:
    lower = _safe_str(text).lower()
    if not lower:
        return False

    claim_terms = (
        "i have",
        "i've got",
        "ive got",
        "we have",
        "we've got",
        "rooms",
        "room",
        "cheap",
        "not cheap",
        "price",
        "cost",
        "available",
        "offer",
        "offers",
        "buy",
        "sell",
        "sells",
        "food",
        "meal",
        "stew",
        "ale",
        "drink",
        "rumor",
        "rumour",
        "repair",
        "torch",
        "rope",
        "done",
        "yours",
        "settled",
        "complete",
        "completed",
        "purchase",
        "paid",
        "settle",
        "can settle",
        "once you confirm",
        "confirm the purchase",
        "complete the purchase",
        "ready to complete",
        "ready to settle",
    )
    return any(term in lower for term in claim_terms)


def _ground_action_result_text(action_text: str, narration_context: Dict[str, Any]) -> str:
    text = _safe_str(action_text).strip()
    if not text:
        return text

    lower_text = text.lower()

    service_result = _service_result_from_context(narration_context)
    if service_result.get("matched"):
        if lower_text in {
            "the attempt fails.",
            "the attempt fails",
            "you fail.",
            "you fail",
            "it fails.",
            "it fails",
        }:
            grounded = _service_grounded_action_result(narration_context)
            if grounded:
                return grounded

        purchase = _safe_dict(service_result.get("purchase"))
        service_application = _safe_dict(narration_context.get("service_application"))
        service_status = _safe_str(service_result.get("status"))
        blocked_reason = _safe_str(
            service_application.get("blocked_reason")
            or purchase.get("blocked_reason")
        )

        if (
            _safe_str(service_result.get("kind")) == "service_purchase"
            and (
                service_status == "blocked"
                or blocked_reason == "insufficient_funds"
            )
        ):
            grounded = _service_grounded_action_result(narration_context)
            if grounded:
                return grounded

        if (
            _safe_str(service_result.get("kind")) == "service_purchase"
            and (
                service_status == "purchase_offer_not_found"
                or blocked_reason == "offer_not_found"
            )
        ):
            grounded = _service_grounded_action_result(narration_context)
            if grounded:
                return grounded

        if (
            _safe_str(service_result.get("kind")) == "service_purchase"
            and (
                _safe_str(service_result.get("status")) == "purchased"
                or bool(purchase.get("applied"))
                or bool(service_application.get("applied"))
            )
        ):
            grounded = _service_grounded_action_result(narration_context)
            if grounded:
                return grounded

        lower_service_text = text.lower()
        repeats_service_action = (
            lower_service_text.startswith("you ")
            or "you ask" in lower_service_text
            or "you inquire" in lower_service_text
            or "you request" in lower_service_text
            or "renting a room" in lower_service_text
            or "from bran" in lower_service_text
            or "from elara" in lower_service_text
            or "what she sells" in lower_service_text
            or "heard any rumors" in lower_service_text
        )
        if repeats_service_action:
            grounded = _service_grounded_action_result(narration_context)
            if grounded:
                return grounded

    lower = text.lower()

    repeats_player_action = any(
        phrase in lower
        for phrase in (
            "you approach",
            "you ask",
            "you inquire",
            "you request",
            "with a hopeful glint",
            "if he has a room",
            "if they have a room",
            "has a room to rent",
        )
    )

    if repeats_player_action and _is_accommodation_request(narration_context):
        return "Bran considers your request."

    return text


def _player_input_action_text(narration_context: Dict[str, Any]) -> str:
    """Return the visible authoritative player-action text."""
    narration_context = _safe_dict(narration_context)
    turn_contract = _safe_dict(narration_context.get("turn_contract"))
    narration_brief = _safe_dict(turn_contract.get("narration_brief"))
    semantic_action = _safe_dict(turn_contract.get("semantic_action"))

    text = _first_nonempty(
        narration_context.get("player_input"),
        turn_contract.get("player_input"),
        narration_brief.get("summary"),
        semantic_action.get("player_input"),
        _safe_dict(narration_context.get("last_player_action")).get("text"),
    )
    text = _strip_basic_markdown(text)
    if not text:
        return ""

    lowered = text.lower()
    replacements = (
        ("i am ", "you are "),
        ("i'm ", "you are "),
        ("i ask ", "you ask "),
        ("i tell ", "you tell "),
        ("i say ", "you say "),
        ("i want ", "you want "),
        ("i try ", "you try "),
        ("i attempt ", "you attempt "),
        ("i punch ", "you punch "),
        ("i attack ", "you attack "),
        ("i ", "you "),
    )
    for prefix, replacement in replacements:
        if lowered.startswith(prefix):
            text = replacement + text[len(prefix):]
            break
    else:
        if not lowered.startswith("you "):
            text = "you " + text

    text = " ".join(text.split()).strip()
    return text[:1].upper() + text[1:]


def _build_authoritative_action_line(narration_context: Dict[str, Any]) -> str:
    action = _player_input_action_text(narration_context)
    if not action:
        return ""
    return f"Action: {action}"


def _titleize_action(action_type: str) -> str:
    value = _safe_str(action_type).strip().replace("_", " ")
    return value[:1].upper() + value[1:] if value else "Action"


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = _safe_str(value).strip()
        if text:
            return text
    return ""

__all__ = [name for name in globals() if not name.startswith("__")]
