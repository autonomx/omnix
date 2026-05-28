from __future__ import annotations

import json

from app.rpg.interactions.interaction_runtime import resolve_general_interaction
from app.rpg.interactions.merchant_runtime import apply_merchant_interaction
from app.rpg.interactions.survival_action_runtime import resolve_survival_action


def _survival_state():
    return {
        "enabled": True,
        "hunger": 60,
        "thirst": 70,
        "fatigue": 80,
        "events": [],
    }


def _simulation_state(*, currency=None, items=None):
    return {
        "session_id": "test-session",
        "survival": _survival_state(),
        "player_state": {
            "currency": currency or {"gold": 0, "silver": 1, "copper": 0},
            "inventory": {
                "items": list(items or []),
                "equipment": {},
                "carry_capacity": 50,
            },
        },
    }


def test_bundle_bc_buy_water_uses_merchant_runtime_and_mutates_currency_inventory_and_stock() -> None:
    simulation_state = _simulation_state(currency={"gold": 0, "silver": 0, "copper": 20})

    result = resolve_general_interaction(
        simulation_state,
        player_input="buy water",
        tick=10,
    )

    survival_result = result["survival_result"]
    merchant_result = survival_result["merchant_result"]
    assert result["handled"] is True
    assert survival_result["ok"] is True
    assert survival_result["action"] == "buy_water"
    assert survival_result["effects"] == {}
    assert survival_result["inventory_delta"] == {"water": 1}
    assert merchant_result["resolved"] is True
    assert merchant_result["item_definition_id"] == "def:water"
    assert merchant_result["price"] == {"gold": 0, "silver": 0, "copper": 3}
    assert simulation_state["player_state"]["currency"] == {"gold": 0, "silver": 0, "copper": 17}
    player_items = simulation_state["player_state"]["inventory"]["items"]
    assert player_items[0]["definition_id"] == "def:water"
    assert player_items[0]["quantity"] == 1
    merchant_items = simulation_state["merchant_state"]["merchants"]["npc:Elara"]["inventory"]["items"]
    water_stock = [item for item in merchant_items if item["definition_id"] == "def:water"][0]
    assert water_stock["quantity"] == 11
    assert survival_result["survival_event"]["source"] == "runtime_action_resolver"
    json.dumps(result)
    json.dumps(simulation_state)


def test_bundle_bc_buy_rations_can_then_be_eaten_from_real_inventory() -> None:
    simulation_state = _simulation_state(currency={"gold": 0, "silver": 0, "copper": 20})

    buy_result = resolve_survival_action(
        simulation_state,
        player_input="buy rations",
        tick=11,
    )
    assert buy_result["ok"] is True
    assert buy_result["action"] == "buy_rations"
    assert buy_result["inventory_delta"] == {"rations": 1}

    eat_result = resolve_survival_action(
        simulation_state,
        player_input="eat rations",
        tick=12,
    )
    assert eat_result["ok"] is True
    assert eat_result["action"] == "eat_rations"
    assert eat_result["effects"] == {"hunger_delta": -30}
    assert eat_result["inventory_delta"] == {"rations": -1}
    assert simulation_state["survival"]["hunger"] == 30
    assert simulation_state["player_state"]["inventory"]["items"] == []


def test_bundle_bc_buy_waterskin_preserves_charges_and_drink_uses_charge() -> None:
    simulation_state = _simulation_state(currency={"gold": 0, "silver": 2, "copper": 0})

    merchant_result = apply_merchant_interaction(
        simulation_state,
        semantic_action_v2={
            "resolved": True,
            "kind": "buy",
            "actor_id": "player",
            "target_ref": "waterskin",
            "item_ref": "waterskin",
            "quantity": 1,
            "merchant_id": "npc:Elara",
        },
        tick=13,
    )
    assert merchant_result["resolved"] is True
    waterskin = simulation_state["player_state"]["inventory"]["items"][0]
    assert waterskin["definition_id"] == "def:waterskin"
    assert waterskin["metadata"]["water_charges"] == 3

    drink_result = resolve_survival_action(
        simulation_state,
        player_input="drink from waterskin",
        tick=14,
    )
    assert drink_result["ok"] is True
    assert drink_result["inventory_delta"] == {"waterskin_water_charges": -1}
    assert simulation_state["player_state"]["inventory"]["items"][0]["metadata"]["water_charges"] == 2
    assert simulation_state["survival"]["thirst"] == 40


def test_bundle_bc_survival_purchase_blocks_on_insufficient_currency_without_inventory_mutation() -> None:
    simulation_state = _simulation_state(currency={"gold": 0, "silver": 0, "copper": 0})

    result = resolve_general_interaction(
        simulation_state,
        player_input="buy rations",
        tick=15,
    )

    survival_result = result["survival_result"]
    assert result["handled"] is False
    assert survival_result["ok"] is False
    assert survival_result["action"] == "buy_rations"
    assert survival_result["blocked_reason"] == "insufficient_currency"
    assert survival_result["merchant_result"]["reason"] == "insufficient_currency"
    assert simulation_state["player_state"]["inventory"]["items"] == []
