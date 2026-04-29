from app.rpg.interactions.interaction_runtime import resolve_general_interaction
from app.rpg.interactions.loot_runtime import generate_loot_from_table


def _state():
    return {
        "session_id": "unit_session",
        "location_id": "loc_tavern_market",
        "player_state": {
            "location_id": "loc_tavern_market",
            "currency": {"gold": 1, "silver": 0, "copper": 0},
            "inventory": {
                "items": [
                    {
                        "item_id": "item:rusty_dagger",
                        "definition_id": "def:rusty_dagger",
                        "name": "rusty dagger",
                        "aliases": ["dagger"],
                    }
                ],
                "equipment": {},
                "carry_capacity": 50.0,
            },
        },
        "scene_items": [],
        "scene_objects": [],
        "merchant_state": {
            "merchants": {
                "npc:Elara": {
                    "merchant_id": "npc:Elara",
                    "name": "Elara",
                    "buy_price_multiplier": 1.0,
                    "sell_price_multiplier": 0.5,
                    "inventory": {
                        "items": [
                            {
                                "item_id": "merchant:elara:minor_healing_potion",
                                "definition_id": "def:minor_healing_potion",
                                "name": "minor healing potion",
                                "quantity": 5,
                            },
                            {
                                "item_id": "merchant:elara:oil_flask",
                                "definition_id": "def:oil_flask",
                                "name": "oil flask",
                                "quantity": 3,
                            },
                        ],
                        "equipment": {},
                        "carry_capacity": 9999.0,
                    },
                }
            }
        },
    }


def _player_items(state):
    return state["player_state"]["inventory"]["items"]


def _item_by_def(items, definition_id):
    for item in items:
        if item.get("definition_id") == definition_id:
            return item
    return {}


def _merchant_items(state):
    return state["merchant_state"]["merchants"]["npc:Elara"]["inventory"]["items"]


def test_generate_loot_is_deterministic_and_adds_items():
    a = _state()
    b = _state()

    first = generate_loot_from_table(
        a,
        loot_table_id="loot:bandit_common",
        source_id="enc:test_bandit",
        session_id="unit_session",
        tick=1,
        add_to_inventory=True,
    )
    second = generate_loot_from_table(
        b,
        loot_table_id="loot:bandit_common",
        source_id="enc:test_bandit",
        session_id="unit_session",
        tick=1,
        add_to_inventory=True,
    )

    assert first["resolved"] is True
    assert first["reason"] == "loot_generated"
    assert first["items_created"] == second["items_created"]
    assert len(a["player_state"]["inventory"]["items"]) > 1


def test_buy_item_from_merchant_decrements_currency_and_stock():
    state = _state()

    result = resolve_general_interaction(
        state,
        player_input="I buy a minor healing potion from Elara.",
        tick=1,
    )

    merchant = result["merchant_result"]
    assert merchant["resolved"] is True
    assert merchant["reason"] == "item_bought_from_merchant"

    potion = _item_by_def(_player_items(state), "def:minor_healing_potion")
    assert potion["quantity"] == 1

    merchant_potion = _item_by_def(_merchant_items(state), "def:minor_healing_potion")
    assert merchant_potion["quantity"] == 4

    assert state["player_state"]["currency"]["gold"] == 0


def test_sell_item_to_merchant_adds_currency_and_merchant_stock():
    state = _state()

    result = resolve_general_interaction(
        state,
        player_input="I sell the rusty dagger to Elara.",
        tick=1,
    )

    merchant = result["merchant_result"]
    assert merchant["resolved"] is True
    assert merchant["reason"] == "item_sold_to_merchant"

    assert not _item_by_def(_player_items(state), "def:rusty_dagger")
    assert _item_by_def(_merchant_items(state), "def:rusty_dagger")
    assert merchant["sale_price"]["silver"] == 4


def test_buy_multiple_oil_flasks():
    state = _state()

    result = resolve_general_interaction(
        state,
        player_input="I buy 2 oil flasks from Elara.",
        tick=1,
    )

    merchant = result["merchant_result"]
    assert merchant["resolved"] is True
    assert merchant["reason"] == "item_bought_from_merchant"

    oil = _item_by_def(_player_items(state), "def:oil_flask")
    assert oil["quantity"] == 2

    merchant_oil = _item_by_def(_merchant_items(state), "def:oil_flask")
    assert merchant_oil["quantity"] == 1
