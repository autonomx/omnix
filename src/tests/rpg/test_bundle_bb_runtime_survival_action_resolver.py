from __future__ import annotations

import json

from app.rpg.interactions.interaction_runtime import resolve_general_interaction
from app.rpg.interactions.survival_action_runtime import (
    detect_survival_action,
    resolve_survival_action,
)


def _simulation_state_with_items(items):
    return {
        "session_id": "test-session",
        "survival": {
            "enabled": True,
            "hunger": 60,
            "thirst": 70,
            "fatigue": 80,
            "events": [],
        },
        "player_state": {
            "currency": {"gold": 0, "silver": 1, "copper": 0},
            "inventory": {
                "items": items,
                "equipment": {},
                "carry_capacity": 50,
            }
        },
    }


def test_bundle_bb_detects_concrete_survival_actions_without_llm() -> None:
    assert detect_survival_action("drink water")["action"] == "drink_water"
    assert detect_survival_action("drink from waterskin")["action"] == "drink_from_waterskin"
    assert detect_survival_action("eat rations")["action"] == "eat_rations"
    assert detect_survival_action("make camp")["action"] == "make_camp"
    assert detect_survival_action("buy water")["action"] == "buy_water"


def test_bundle_bb_drink_water_consumes_inventory_and_emits_authoritative_contract_fragment() -> None:
    simulation_state = _simulation_state_with_items(
        [
            {
                "item_id": "item:water",
                "definition_id": "def:water",
                "name": "Water",
                "kind": "supply",
                "quantity": 2,
                "stackable": True,
                "max_stack": 10,
                "unit_weight": 1.0,
                "tags": ["water", "survival"],
            }
        ]
    )

    result = resolve_general_interaction(
        simulation_state,
        player_input="I drink water",
        tick=4,
    )

    survival_result = result["survival_result"]
    assert result["handled"] is True
    assert survival_result["ok"] is True
    assert survival_result["action_category"] == "survival"
    assert survival_result["action"] == "drink_water"
    assert survival_result["effects"] == {"thirst_delta": -30}
    assert survival_result["inventory_delta"] == {"water": -1}
    assert survival_result["survival_event"]["source"] == "runtime_action_resolver"
    assert survival_result["turn_contract_fragment"] == {
        "action_category": "survival",
        "action": "drink_water",
        "ok": True,
        "effects": {"thirst_delta": -30},
        "inventory_delta": {"water": -1},
        "survival_event": survival_result["survival_event"],
    }
    assert simulation_state["survival"]["thirst"] == 40
    assert simulation_state["survival"]["last_water_turn"] == 4
    assert simulation_state["player_state"]["inventory"]["items"][0]["quantity"] == 1
    json.dumps(result)
    json.dumps(simulation_state)


def test_bundle_bb_eat_rations_consumes_ration_and_reduces_hunger() -> None:
    simulation_state = _simulation_state_with_items(
        [
            {
                "item_id": "item:rations",
                "definition_id": "def:rations",
                "name": "Trail Rations",
                "kind": "supply",
                "quantity": 3,
                "stackable": True,
                "max_stack": 10,
                "unit_weight": 0.5,
                "tags": ["rations", "food", "survival"],
            }
        ]
    )

    result = resolve_survival_action(
        simulation_state,
        player_input="eat rations",
        tick=5,
    )

    assert result["ok"] is True
    assert result["action"] == "eat_rations"
    assert result["effects"] == {"hunger_delta": -30}
    assert result["inventory_delta"] == {"rations": -1}
    assert simulation_state["survival"]["hunger"] == 30
    assert simulation_state["survival"]["last_food_turn"] == 5
    assert simulation_state["player_state"]["inventory"]["items"][0]["quantity"] == 2


def test_bundle_bb_waterskin_charge_is_authoritative_inventory_delta() -> None:
    simulation_state = _simulation_state_with_items(
        [
            {
                "item_id": "item:waterskin",
                "definition_id": "def:waterskin",
                "name": "Waterskin",
                "kind": "supply",
                "quantity": 1,
                "stackable": False,
                "unit_weight": 1.0,
                "tags": ["waterskin", "water", "survival"],
                "metadata": {"water_charges": 2},
            }
        ]
    )

    result = resolve_general_interaction(
        simulation_state,
        player_input="drink from waterskin",
        tick=6,
    )

    survival_result = result["survival_result"]
    assert survival_result["ok"] is True
    assert survival_result["action"] == "drink_from_waterskin"
    assert survival_result["effects"] == {"thirst_delta": -30}
    assert survival_result["inventory_delta"] == {"waterskin_water_charges": -1}
    assert simulation_state["player_state"]["inventory"]["items"][0]["metadata"]["water_charges"] == 1


def test_bundle_bb_blocks_drinking_without_water_or_waterskin() -> None:
    simulation_state = _simulation_state_with_items([])

    result = resolve_general_interaction(
        simulation_state,
        player_input="drink water",
        tick=7,
    )

    survival_result = result["survival_result"]
    assert result["handled"] is False
    assert survival_result["ok"] is False
    assert survival_result["action_category"] == "survival"
    assert survival_result["action"] == "drink_water"
    assert survival_result["blocked_reason"] == "no_water_available"
    assert simulation_state["survival"]["thirst"] == 70


def test_bundle_bb_rest_resolves_without_inventory_mutation() -> None:
    simulation_state = _simulation_state_with_items([])

    result = resolve_general_interaction(
        simulation_state,
        player_input="rest for an hour",
        tick=8,
    )

    survival_result = result["survival_result"]
    assert result["handled"] is True
    assert survival_result["ok"] is True
    assert survival_result["action"] == "rest"
    assert survival_result["effects"] == {"fatigue_delta": -35}
    assert survival_result["inventory_delta"] == {}
    assert simulation_state["survival"]["fatigue"] == 45
    assert simulation_state["survival"]["last_rest_turn"] == 8


def test_bundle_bb_survival_purchase_now_routes_to_runtime_economy() -> None:
    simulation_state = _simulation_state_with_items([])

    result = resolve_general_interaction(
        simulation_state,
        player_input="buy water",
        tick=9,
    )

    survival_result = result["survival_result"]
    assert result["handled"] is True
    assert survival_result["ok"] is True
    assert survival_result["action"] == "buy_water"
    assert survival_result["inventory_delta"] == {"water": 1}
    assert survival_result["merchant_result"]["source"] == "deterministic_merchant_runtime"
    assert simulation_state["player_state"]["inventory"]["items"][0]["definition_id"] == "def:water"
