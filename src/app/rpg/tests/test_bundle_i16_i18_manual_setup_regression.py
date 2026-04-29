from app.rpg.interactions.interaction_runtime import resolve_general_interaction


def test_merchant_buy_uses_player_state_currency():
    state = {
        "location_id": "loc_tavern_market",
        "player_state": {
            "location_id": "loc_tavern_market",
            "currency": {"gold": 1, "silver": 0, "copper": 0},
            "inventory": {
                "items": [],
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
                            }
                        ],
                        "equipment": {},
                        "carry_capacity": 9999.0,
                    },
                }
            }
        },
    }

    result = resolve_general_interaction(
        state,
        player_input="I buy a minor healing potion from Elara.",
        tick=1,
    )

    merchant = result["merchant_result"]
    assert merchant["resolved"] is True
    assert merchant["reason"] == "item_bought_from_merchant"
    assert merchant["currency_before"] == {"gold": 1, "silver": 0, "copper": 0}
    assert merchant["currency_after"] == {"gold": 0, "silver": 90, "copper": 0}