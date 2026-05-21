from __future__ import annotations

from app.rpg.session.survival_actions import resolve_survival_action
from app.rpg.session.turn_contract import build_turn_contract


def _state_with_needs(*, hunger: int = 50, thirst: int = 50, fatigue: int = 50):
    return {
        "tick": 1,
        "climate_survival": {
            "tick": 1,
            "runtime_enforced": True,
            "survival": {
                "hunger": hunger,
                "thirst": thirst,
                "fatigue": fatigue,
                "action_count": 1,
            },
        },
        "player_state": {
            "resources": {
                "hunger": hunger,
                "thirst": thirst,
                "fatigue": fatigue,
            },
            "inventory_state": {
                "currency": {"gold": 2, "silver": 10, "copper": 10},
                "items": [],
            },
        },
    }


def test_n1232_eat_food_consumes_one_inventory_item_and_reduces_hunger() -> None:
    state = _state_with_needs(hunger=60, thirst=20, fatigue=20)
    state["player_state"]["inventory_state"]["items"] = [
        {"item_id": "ration", "name": "Trail ration", "quantity": 2, "tags": ["food"]},
        {"item_id": "torch", "name": "Torch", "quantity": 1},
    ]

    result = resolve_survival_action(player_input="I eat a ration", simulation_state=state)

    assert result["matched"] is True
    assert result["applied"] is True
    assert result["action_kind"] == "eat_food"
    assert result["resource_changes"]["hunger_delta"] == -30
    assert state["player_state"]["resources"]["hunger"] == 30
    items = state["player_state"]["inventory_state"]["items"]
    ration = next(item for item in items if item.get("item_id") == "ration")
    assert ration["quantity"] == 1


def test_n1232_drink_water_consumes_inventory_item_and_reduces_thirst() -> None:
    state = _state_with_needs(hunger=10, thirst=55, fatigue=10)
    state["player_state"]["inventory_state"]["items"] = [
        {"item_id": "waterskin", "name": "Waterskin", "quantity": 1, "tags": ["drink", "water"]},
    ]

    result = resolve_survival_action(player_input="I drink water from my waterskin", simulation_state=state)

    assert result["matched"] is True
    assert result["applied"] is True
    assert result["action_kind"] == "drink_water"
    assert result["resource_changes"]["thirst_delta"] == -30
    assert state["player_state"]["resources"]["thirst"] == 25
    assert state["player_state"]["inventory_state"]["items"] == []


def test_n1232_eat_without_food_is_blocked_and_does_not_change_needs() -> None:
    state = _state_with_needs(hunger=50, thirst=20, fatigue=20)

    result = resolve_survival_action(player_input="I eat food", simulation_state=state)

    assert result["matched"] is True
    assert result["applied"] is False
    assert result["blocked"] is True
    assert result["blocked_reason"] == "no_food_item"
    assert state["player_state"]["resources"]["hunger"] == 50


def test_n1232_rest_reduces_fatigue_without_inventory_consumption() -> None:
    state = _state_with_needs(hunger=10, thirst=10, fatigue=80)

    result = resolve_survival_action(player_input="I rest by the fire", simulation_state=state)

    assert result["matched"] is True
    assert result["applied"] is True
    assert result["action_kind"] == "rest"
    assert result["resource_changes"]["fatigue_delta"] == -25
    assert state["player_state"]["resources"]["fatigue"] == 55


def test_n1232_turn_contract_eat_applies_pressure_then_relief_and_removes_inventory() -> None:
    before = _state_with_needs(hunger=60, thirst=20, fatigue=20)
    after = _state_with_needs(hunger=60, thirst=20, fatigue=20)
    after["player_state"]["inventory_state"]["items"] = [
        {"item_id": "ration", "name": "Trail ration", "quantity": 1, "tags": ["food"]},
    ]

    contract = build_turn_contract(
        player_input="I eat a ration",
        action={"action_type": "use_item"},
        resolved_action={"summary": "You eat."},
        simulation_state_before=before,
        simulation_state_after=after,
        runtime_state={"tick": 1},
    )

    assert contract["survival_action"]["action_kind"] == "eat_food"
    assert contract["resource_changes"]["survival_action"]["hunger_delta"] == -30
    assert contract["resource_changes"]["climate_survival"]["hunger_delta"] == 1
    assert after["player_state"]["resources"]["hunger"] == 31
    assert after["player_state"]["inventory_state"]["items"] == []
    assert contract["resolved_action"]["survival_action"]["applied"] is True


def test_n1232_buy_meal_applies_currency_cost_and_hunger_relief() -> None:
    state = _state_with_needs(hunger=70, thirst=20, fatigue=20)
    service_result = {
        "matched": True,
        "service_kind": "meal",
        "selected_offer_id": "bran_meal_stew",
        "offers": [
            {
                "offer_id": "bran_meal_stew",
                "service_kind": "meal",
                "label": "Hot stew",
                "price": {"gold": 0, "silver": 1, "copper": 5},
                "effects": {"meal_consumed": True},
            }
        ],
        "purchase": {
            "blocked": False,
            "price": {"gold": 0, "silver": 1, "copper": 5},
            "can_afford": True,
        },
    }

    result = resolve_survival_action(
        player_input="I buy hot stew from Bran",
        simulation_state=state,
        service_result=service_result,
    )

    assert result["matched"] is True
    assert result["applied"] is True
    assert result["action_kind"] == "buy_meal"
    assert state["player_state"]["resources"]["hunger"] == 35
    assert state["player_state"]["inventory_state"]["currency"] == {"gold": 2, "silver": 9, "copper": 5}


def test_n1232_buy_lodging_reduces_fatigue() -> None:
    state = _state_with_needs(hunger=20, thirst=20, fatigue=85)
    service_result = {
        "matched": True,
        "service_kind": "lodging",
        "selected_offer_id": "bran_lodging_private_room",
        "offers": [
            {
                "offer_id": "bran_lodging_private_room",
                "service_kind": "lodging",
                "label": "Private room",
                "price": {"gold": 1, "silver": 0, "copper": 0},
                "effects": {"lodging_reserved": True, "rest_quality": "good"},
            }
        ],
        "purchase": {
            "blocked": False,
            "price": {"gold": 1, "silver": 0, "copper": 0},
            "can_afford": True,
        },
    }

    result = resolve_survival_action(
        player_input="I rent the private room from Bran",
        simulation_state=state,
        service_result=service_result,
    )

    assert result["matched"] is True
    assert result["applied"] is True
    assert result["action_kind"] == "buy_lodging"
    assert state["player_state"]["resources"]["fatigue"] == 30
    # Currency is canonicalized by the shared currency helper: 2g 10s 10c - 1g = 210c = 2g 1s 0c.
    assert state["player_state"]["inventory_state"]["currency"] == {"gold": 2, "silver": 1, "copper": 0}
