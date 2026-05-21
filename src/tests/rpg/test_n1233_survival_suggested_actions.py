from __future__ import annotations

from app.rpg.session.survival_actions import build_survival_suggested_actions
from app.rpg.session.turn_contract import build_turn_contract


def _state(*, hunger: int = 0, thirst: int = 0, fatigue: int = 0, location_id: str = ""):
    player_state = {
        "resources": {"hunger": hunger, "thirst": thirst, "fatigue": fatigue},
        "inventory_state": {
            "currency": {"gold": 2, "silver": 10, "copper": 10},
            "items": [],
        },
    }
    if location_id:
        player_state["location_id"] = location_id
        player_state["current_location_id"] = location_id
    return {
        "tick": 1,
        "player_state": player_state,
        "climate_survival": {
            "tick": 1,
            "runtime_enforced": True,
            "survival": {
                "hunger": hunger,
                "thirst": thirst,
                "fatigue": fatigue,
                "action_count": 1,
                "warnings": [],
            },
        },
    }


def _kinds(suggestions):
    return {item.get("action_kind") for item in suggestions}


def test_n1233_food_and_drink_suggestions_require_inventory_items() -> None:
    state = _state(hunger=80, thirst=80, fatigue=10)
    state["player_state"]["inventory_state"]["items"] = [
        {"item_id": "ration", "name": "Trail ration", "quantity": 1, "tags": ["food"]},
        {"item_id": "waterskin", "name": "Waterskin", "quantity": 1, "tags": ["drink", "water"]},
    ]

    suggestions = build_survival_suggested_actions(state)

    assert "eat_food" in _kinds(suggestions)
    assert "drink_water" in _kinds(suggestions)
    assert any(item["command"] == "I eat Trail ration" for item in suggestions)
    assert any(item["command"] == "I drink Waterskin" for item in suggestions)


def test_n1233_no_food_or_drink_suggestions_without_inventory_or_provider() -> None:
    state = _state(hunger=80, thirst=80, fatigue=10, location_id="loc_old_mill_road")

    suggestions = build_survival_suggested_actions(state)

    assert "eat_food" not in _kinds(suggestions)
    assert "drink_water" not in _kinds(suggestions)
    assert "buy_meal" not in _kinds(suggestions)
    assert "buy_drink" not in _kinds(suggestions)


def test_n1233_rest_suggestion_appears_for_fatigue_without_inventory() -> None:
    state = _state(hunger=10, thirst=10, fatigue=80, location_id="loc_old_mill_road")

    suggestions = build_survival_suggested_actions(state)

    assert "rest" in _kinds(suggestions)
    assert "buy_lodging" not in _kinds(suggestions)


def test_n1233_service_suggestions_require_provider_location_and_affordability() -> None:
    state = _state(hunger=80, thirst=80, fatigue=80, location_id="loc_tavern")

    suggestions = build_survival_suggested_actions(state)
    kinds = _kinds(suggestions)

    assert "buy_meal" in kinds
    assert "buy_lodging" in kinds
    # loc_tavern intentionally does not advertise drink service in the location registry.
    assert "buy_drink" not in kinds
    assert any(item.get("provider_id") == "npc:Bran" for item in suggestions if item.get("action_kind") == "buy_meal")


def test_n1233_service_suggestions_do_not_appear_when_unaffordable() -> None:
    state = _state(hunger=80, thirst=10, fatigue=80, location_id="loc_tavern")
    state["player_state"]["inventory_state"]["currency"] = {"gold": 0, "silver": 0, "copper": 0}

    suggestions = build_survival_suggested_actions(state)
    kinds = _kinds(suggestions)

    assert "buy_meal" not in kinds
    assert "buy_lodging" not in kinds
    assert "rest" in kinds


def test_n1233_turn_contract_projects_survival_suggestions() -> None:
    before = _state(hunger=70, thirst=10, fatigue=10, location_id="loc_old_mill_road")
    after = _state(hunger=70, thirst=10, fatigue=10, location_id="loc_old_mill_road")
    after["player_state"]["inventory_state"]["items"] = [
        {"item_id": "ration", "name": "Trail ration", "quantity": 1, "tags": ["food"]},
    ]

    contract = build_turn_contract(
        player_input="I wait.",
        action={"action_type": "wait"},
        resolved_action={"summary": "You wait."},
        simulation_state_before=before,
        simulation_state_after=after,
        runtime_state={"tick": 1},
    )

    assert "survival_suggested_actions" in contract
    assert "eat_food" in _kinds(contract["survival_suggested_actions"])
    assert contract["suggested_actions"][0]["type"] == "survival_relief"
    assert contract["presentation"]["survival_suggested_actions"] == contract["survival_suggested_actions"]
