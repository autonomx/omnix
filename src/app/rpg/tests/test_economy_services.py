from app.rpg.economy.currency import (
    add_currency,
    can_afford,
    currency_delta,
    currency_to_copper,
    format_currency,
    get_player_currency,
    normalize_currency,
    subtract_currency,
    subtract_currency_cost,
)
from app.rpg.economy.service_registry import get_provider_offers
from app.rpg.economy.service_resolver import (
    resolve_service_intent,
    resolve_service_turn,
)
from app.rpg.economy.service_stock import (
    annotate_offer_availability,
    filter_available_offers,
)


def test_currency_helpers_normalize_and_compare_values():
    assert normalize_currency({"gold": 1, "silver": 2, "copper": 3}) == {
        "gold": 1,
        "silver": 2,
        "copper": 3,
    }
    assert currency_to_copper({"gold": 1, "silver": 2, "copper": 3}) == 123
    assert can_afford(
        {"gold": 0, "silver": 5, "copper": 0},
        {"gold": 0, "silver": 3, "copper": 0},
    )
    assert not can_afford(
        {"gold": 0, "silver": 1, "copper": 0},
        {"gold": 0, "silver": 3, "copper": 0},
    )


def test_currency_helpers_add_subtract_and_format():
    assert add_currency(
        {"gold": 0, "silver": 1, "copper": 5},
        {"gold": 0, "silver": 1, "copper": 7},
    ) == {"gold": 0, "silver": 3, "copper": 2}

    assert subtract_currency(
        {"gold": 1, "silver": 0, "copper": 0},
        {"gold": 0, "silver": 5, "copper": 0},
    ) == {"gold": 0, "silver": 5, "copper": 0}

    assert format_currency({"gold": 0, "silver": 5, "copper": 0}) == "5 silver"
    assert format_currency({"gold": 1, "silver": 2, "copper": 3}) == "1 gold, 2 silver, 3 copper"


def test_currency_compatibility_helpers_preserve_old_behavior():
    assert currency_delta(
        {"gold": 1, "silver": 0, "copper": 0},
        {"gold": 0, "silver": 5, "copper": 0},
    ) == {"gold": 0, "silver": -5, "copper": 0}

    assert subtract_currency_cost(
        {"gold": 1, "silver": 0, "copper": 0},
        {"gold": 0, "silver": 5, "copper": 0},
    ) == {"gold": 0, "silver": 5, "copper": 0}

    try:
        subtract_currency_cost(
            {"gold": 0, "silver": 1, "copper": 0},
            {"gold": 0, "silver": 5, "copper": 0},
        )
    except ValueError as exc:
        assert "insufficient currency" in str(exc)
    else:
        raise AssertionError("Expected insufficient currency error")


def test_player_currency_falls_back_to_visible_wallet_when_inventory_wallet_empty():
    state = {
        "player_state": {
            "currency": {"gold": 50, "silver": 0, "copper": 0},
            "inventory_state": {
                "currency": {"gold": 0, "silver": 0, "copper": 0},
            },
        },
    }

    assert get_player_currency(state) == {"gold": 50, "silver": 0, "copper": 0}


def test_service_registry_has_lodging_meal_info_and_goods():
    bran_lodging = get_provider_offers("npc:Bran", "lodging")
    bran_meals = get_provider_offers("npc:Bran", "meal")
    elara_goods = get_provider_offers("npc:Elara", "shop_goods")

    assert any(offer["offer_id"] == "bran_lodging_common_cot" for offer in bran_lodging)
    assert any(offer["offer_id"] == "bran_meal_stew" for offer in bran_meals)
    assert any(offer["offer_id"] == "bran_dried_rations" for offer in bran_meals)
    assert any(offer["offer_id"] == "elara_torch" for offer in elara_goods)


def test_service_stock_annotates_out_of_stock_offer():
    offer = {
        "offer_id": "test_offer",
        "label": "Test Offer",
        "stock": 1,
        "availability": "available",
    }
    state = {
        "service_offer_state": {
            "offers": {
                "test_offer": {
                    "stock_remaining": 0,
                    "stock_initial": 1,
                }
            }
        }
    }

    annotated = annotate_offer_availability(state, offer)

    assert annotated["availability"] == "unavailable"
    assert annotated["unavailable_reason"] == "out_of_stock"
    assert annotated["stock_remaining"] == 0


def test_service_stock_filters_unavailable_offer():
    state = {
        "service_offer_state": {
            "offers": {
                "elara_torch": {
                    "stock_remaining": 0,
                    "stock_initial": 1,
                }
            }
        }
    }
    offers = get_provider_offers("npc:Elara", "shop_goods")

    filtered = filter_available_offers(
        state,
        offers,
        provider={
            "provider_id": "npc:Elara",
            "provider_name": "Elara",
            "location_id": "loc_market",
        },
    )

    assert not any(offer["offer_id"] == "elara_torch" for offer in filtered)
    assert any(offer["offer_id"] == "elara_rope" for offer in filtered)


def test_service_intent_detects_lodging_inquiry():
    intent = resolve_service_intent("I ask Bran for a room to rent")

    assert intent["matched"] is True
    assert intent["kind"] == "service_inquiry"
    assert intent["service_kind"] == "lodging"
    assert intent["provider_id"] == "npc:Bran"
    assert intent["provider_name"] == "Bran"


def test_service_turn_matches_even_when_candidate_action_is_use_item():
    result = resolve_service_turn(
        player_input="I ask Bran for a room to rent",
        action={"action_type": "use_item", "target_id": "Bran", "target_name": "Bran"},
        resolved_action={"ok": False, "reason": "unknown_item", "action_type": "use_item"},
        simulation_state={
            "player_state": {
                "inventory_state": {
                    "currency": {"gold": 0, "silver": 0, "copper": 0}
                }
            }
        },
        runtime_state={},
    )

    assert result["matched"] is True
    assert result["kind"] == "service_inquiry"
    assert result["service_kind"] == "lodging"
    assert result["provider_id"] == "npc:Bran"
    assert result["status"] == "offers_available"


def test_service_intent_detects_meal_inquiry():
    intent = resolve_service_intent("I ask Bran for food")

    assert intent["matched"] is True
    assert intent["kind"] == "service_inquiry"
    assert intent["service_kind"] == "meal"
    assert intent["provider_id"] == "npc:Bran"


def test_service_intent_detects_food_for_sale_inquiry():
    intent = resolve_service_intent("i ask bran if he has food for sale")

    assert intent["matched"] is True
    assert intent["kind"] == "service_inquiry"
    assert intent["service_kind"] == "meal"
    assert intent["provider_id"] == "npc:Bran"


def test_service_intent_defaults_stew_purchase_to_bran_not_market_merchant():
    intent = resolve_service_intent("ill buy a hot stew")

    assert intent["matched"] is True
    assert intent["kind"] == "service_purchase"
    assert intent["service_kind"] == "meal"
    assert intent["provider_id"] == "npc:Bran"


def test_service_turn_matches_bran_dried_rations_purchase():
    result = resolve_service_turn(
        player_input="I buy dried rations from Bran",
        action={},
        resolved_action={},
        simulation_state={
            "player_state": {
                "currency": {"gold": 0, "silver": 10, "copper": 0},
                "inventory_state": {"items": [], "currency": {"gold": 0, "silver": 10, "copper": 0}},
            }
        },
        runtime_state={},
    )

    assert result["status"] == "purchase_ready"
    assert result["selected_offer_id"] == "bran_dried_rations"
    assert result["purchase"]["price"] == {"gold": 0, "silver": 5, "copper": 0}


def test_service_turn_treats_take_named_rations_as_purchase_not_pickup():
    inquiry = resolve_service_turn(
        player_input="I ask Bran if he has any food to sell",
        action={},
        resolved_action={},
        simulation_state={"player_state": {"currency": {"silver": 10}}},
        runtime_state={},
    )
    result = resolve_service_turn(
        player_input="ill take dried rations",
        action={"action_type": "pickup_item"},
        resolved_action={},
        simulation_state={"player_state": {"currency": {"silver": 10}}},
        runtime_state={"last_turn_contract": {"service_result": inquiry}},
    )

    assert result["matched"] is True
    assert result["kind"] == "service_purchase"
    assert result["status"] == "purchase_ready"
    assert result["selected_offer_id"] == "bran_dried_rations"


def test_service_turn_resolves_payment_confirmation_from_prior_rations_offer():
    inquiry = resolve_service_turn(
        player_input="Dried rations. How much would that be?",
        action={},
        resolved_action={},
        simulation_state={"player_state": {"currency": {"silver": 10}}},
        runtime_state={},
    )
    result = resolve_service_turn(
        player_input="I'll take it. I pay Bran 5 silver coins",
        action={},
        resolved_action={},
        simulation_state={"player_state": {"currency": {"silver": 10}}},
        runtime_state={"last_turn_contract": {"service_result": inquiry}},
    )

    assert len(inquiry["available_actions"]) == 1
    assert inquiry["available_actions"][0]["offer_id"] == "bran_dried_rations"
    assert result["status"] == "purchase_ready"
    assert result["selected_offer_id"] == "bran_dried_rations"


def test_service_intent_detects_paid_information_inquiry():
    intent = resolve_service_intent("I ask Bran if he has heard any rumors")

    assert intent["matched"] is True
    assert intent["kind"] == "service_inquiry"
    assert intent["service_kind"] == "paid_information"
    assert intent["provider_id"] == "npc:Bran"


def test_service_intent_detects_shop_inquiry():
    intent = resolve_service_intent("I ask Elara what she sells")

    assert intent["matched"] is True
    assert intent["kind"] == "service_inquiry"
    assert intent["service_kind"] == "shop_goods"
    assert intent["provider_id"] == "npc:Elara"


def test_service_turn_returns_available_actions_for_lodging():
    result = resolve_service_turn(
        player_input="I ask Bran for a room to rent",
        action={},
        resolved_action={},
        simulation_state={
            "player_state": {
                "inventory_state": {
                    "currency": {"gold": 1, "silver": 0, "copper": 0}
                }
            }
        },
        runtime_state={},
    )

    assert result["matched"] is True
    assert result["status"] == "offers_available"
    assert result["service_kind"] == "lodging"
    assert any(offer["offer_id"] == "bran_lodging_common_cot" for offer in result["offers"])
    assert any(action["action_id"] == "service:purchase:bran_lodging_common_cot" for action in result["available_actions"])


def test_service_turn_uses_visible_player_currency_for_lodging_purchase():
    result = resolve_service_turn(
        player_input="I buy Private room from Bran",
        action={},
        resolved_action={},
        simulation_state={
            "player_state": {
                "currency": {"gold": 50, "silver": 0, "copper": 0},
                "inventory_state": {
                    "currency": {"gold": 0, "silver": 0, "copper": 0},
                },
            },
        },
        runtime_state={},
    )

    assert result["matched"] is True
    assert result["kind"] == "service_purchase"
    assert result["service_kind"] == "lodging"
    assert result["selected_offer_id"] == "bran_lodging_private_room"
    assert result["player_currency"] == {"gold": 50, "silver": 0, "copper": 0}
    assert result["status"] == "purchase_ready"
    assert result["purchase"]["can_afford"] is True
    assert result["purchase"]["blocked"] is False


def test_service_turn_detects_purchase_without_mutating_state():
    result = resolve_service_turn(
        player_input="I buy a torch from Elara",
        action={},
        resolved_action={},
        simulation_state={
            "player_state": {
                "inventory_state": {
                    "currency": {"gold": 0, "silver": 2, "copper": 0}
                }
            }
        },
        runtime_state={},
    )

    assert result["matched"] is True
    assert result["kind"] == "service_purchase"
    assert result["service_kind"] == "shop_goods"
    assert result["provider_id"] == "npc:Elara"
    assert result["selected_offer_id"] == "elara_torch"
    assert result["status"] == "purchase_ready"
    assert result["purchase"]["can_afford"] is True
    assert result["purchase"]["resource_changes"]["currency"] == {
        "gold": 0,
        "silver": -1,
        "copper": 0,
    }
    assert result["purchase"]["applied"] is False
    assert "runtime applies mutation" in result["purchase"]["note"]


def test_service_turn_blocks_purchase_when_insufficient_funds():
    result = resolve_service_turn(
        player_input="I buy rope from Elara",
        action={},
        resolved_action={},
        simulation_state={
            "player_state": {
                "inventory_state": {
                    "currency": {"gold": 0, "silver": 1, "copper": 0}
                }
            }
        },
        runtime_state={},
    )

    assert result["matched"] is True
    assert result["kind"] == "service_purchase"
    assert result["selected_offer_id"] == "elara_rope"
    assert result["status"] == "blocked"
    assert result["purchase"]["blocked"] is True
    assert result["purchase"]["blocked_reason"] == "insufficient_funds"
    assert result["purchase"]["effects"] == {}
