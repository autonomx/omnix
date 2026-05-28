from __future__ import annotations

import json

from app.rpg.interactions.interaction_runtime import resolve_general_interaction
from app.rpg.interactions.survival_action_runtime import detect_survival_action


def _simulation_state(*, items=None, currency=None):
    return {
        "session_id": "test-session-br",
        "survival": {
            "enabled": True,
            "hunger": 70,
            "thirst": 80,
            "fatigue": 85,
            "events": [],
        },
        "player_state": {
            "currency": currency or {"gold": 0, "silver": 2, "copper": 0},
            "inventory": {
                "items": list(items or []),
                "equipment": {},
                "carry_capacity": 50,
            },
        },
    }


def test_bundle_br_detects_expanded_survival_services_without_llm() -> None:
    assert detect_survival_action("order a tavern meal")["action"] == "tavern_meal"
    assert detect_survival_action("rent a room at the inn")["action"] == "inn_lodging"
    assert detect_survival_action("buy a ration pack")["action"] == "ration_pack"
    assert detect_survival_action("fill my waterskin at the well")["action"] == "fill_waterskin"
    assert detect_survival_action("drink from the stream")["action"] == "drink_from_stream"
    assert detect_survival_action("drink from the well")["action"] == "drink_from_well"


def test_bundle_br_tavern_meal_is_service_backed_and_reduces_hunger() -> None:
    simulation_state = _simulation_state(currency={"silver": 1})

    result = resolve_general_interaction(simulation_state, player_input="order a tavern meal", tick=20)

    survival_result = result["survival_result"]
    assert result["handled"] is True
    assert survival_result["ok"] is True
    assert survival_result["action"] == "tavern_meal"
    assert survival_result["effects"] == {"hunger_delta": -35}
    assert survival_result["service_result"]["service_type"] == "tavern_meal"
    assert survival_result["service_result"]["cost_copper"] == 5
    assert simulation_state["survival"]["hunger"] == 35
    assert simulation_state["player_state"]["currency"] == {"gold": 0, "silver": 0, "copper": 5}
    assert survival_result["turn_contract_fragment"]["survival_event"]["service_result"]["service_type"] == "tavern_meal"
    json.dumps(result)


def test_bundle_br_inn_lodging_is_service_backed_and_reduces_fatigue() -> None:
    simulation_state = _simulation_state(currency={"silver": 2})

    result = resolve_general_interaction(simulation_state, player_input="rent a room at the inn", tick=21)

    survival_result = result["survival_result"]
    assert survival_result["ok"] is True
    assert survival_result["action"] == "inn_lodging"
    assert survival_result["effects"] == {"fatigue_delta": -55}
    assert survival_result["service_result"]["service_type"] == "inn_lodging"
    assert simulation_state["survival"]["fatigue"] == 30
    assert simulation_state["player_state"]["currency"] == {"gold": 0, "silver": 1, "copper": 0}


def test_bundle_br_ration_pack_adds_multiple_real_inventory_rations() -> None:
    simulation_state = _simulation_state(currency={"silver": 1})

    result = resolve_general_interaction(simulation_state, player_input="buy a ration pack", tick=22)

    survival_result = result["survival_result"]
    assert survival_result["ok"] is True
    assert survival_result["action"] == "ration_pack"
    assert survival_result["inventory_delta"] == {"rations": 3}
    assert survival_result["service_result"]["service_type"] == "ration_pack"
    items = simulation_state["player_state"]["inventory"]["items"]
    assert items[0]["definition_id"] == "def:rations"
    assert items[0]["quantity"] == 3
    assert simulation_state["player_state"]["currency"] == {"gold": 0, "silver": 0, "copper": 2}


def test_bundle_br_fill_waterskin_requires_waterskin_and_restores_charges() -> None:
    simulation_state = _simulation_state(
        items=[
            {
                "item_id": "item:waterskin",
                "definition_id": "def:waterskin",
                "name": "Waterskin",
                "kind": "supply",
                "quantity": 1,
                "stackable": False,
                "tags": ["waterskin", "water", "survival"],
                "metadata": {"water_charges": 0},
            }
        ],
        currency={"silver": 0},
    )

    result = resolve_general_interaction(simulation_state, player_input="fill my waterskin at the well", tick=23)

    survival_result = result["survival_result"]
    assert survival_result["ok"] is True
    assert survival_result["action"] == "fill_waterskin"
    assert survival_result["inventory_delta"] == {"waterskin_water_charges": 3}
    assert survival_result["service_result"]["service_type"] == "water_source"
    assert simulation_state["player_state"]["inventory"]["items"][0]["metadata"]["water_charges"] == 3


def test_bundle_br_fill_waterskin_blocks_without_container() -> None:
    simulation_state = _simulation_state(items=[], currency={"silver": 0})

    result = resolve_general_interaction(simulation_state, player_input="fill my waterskin at the well", tick=24)

    survival_result = result["survival_result"]
    assert result["handled"] is False
    assert survival_result["ok"] is False
    assert survival_result["action"] == "fill_waterskin"
    assert survival_result["blocked_reason"] == "no_waterskin_available"


def test_bundle_br_drink_from_well_or_stream_reduces_thirst_without_inventory() -> None:
    simulation_state = _simulation_state(items=[], currency={"silver": 0})

    result = resolve_general_interaction(simulation_state, player_input="drink from the well", tick=25)

    survival_result = result["survival_result"]
    assert survival_result["ok"] is True
    assert survival_result["action"] == "drink_from_well"
    assert survival_result["effects"] == {"thirst_delta": -35}
    assert survival_result["inventory_delta"] == {}
    assert simulation_state["survival"]["thirst"] == 45


def test_bundle_br_service_blocks_on_insufficient_currency_without_mutation() -> None:
    simulation_state = _simulation_state(currency={"silver": 0, "copper": 4})
    before = dict(simulation_state["survival"])

    result = resolve_general_interaction(simulation_state, player_input="order a tavern meal", tick=26)

    survival_result = result["survival_result"]
    assert result["handled"] is False
    assert survival_result["ok"] is False
    assert survival_result["blocked_reason"] == "insufficient_currency"
    assert simulation_state["survival"]["hunger"] == before["hunger"]
    assert simulation_state["player_state"]["currency"] == {"gold": 0, "silver": 0, "copper": 4}
