def test_ci_phase2_price_modifier_neutral_player_preserves_baseline_buy_price():
    from app.rpg.economy.merchant_transactions import buy_from_merchant

    state = {"player_state": {"inventory_state": {"items": [], "currency": {"silver": 20}}}}

    result = buy_from_merchant(state, item_id="healing_potion", qty=1, tick=1)

    assert result["resolved"] is True
    assert result["price"] == {"gold": 0, "silver": 10, "copper": 0}
    assert result["price_modifier"]["source"] == "deterministic_price_modifiers"
    assert result["price_modifier"]["price_modifier"]["multiplier_bps"] == 10000
    assert result["transaction_log_entry"]["price_modifier"]["source"] == "deterministic_price_modifiers"


def test_ci_phase2_price_modifier_charisma_relationship_reputation_discount_buy_price():
    from app.rpg.economy.merchant_transactions import buy_from_merchant

    state = {
        "player_state": {
            "stats": {"charisma": 14},
            "relationships": {"merchant:elara": {"score": 25}},
            "reputation": {"local": 20},
            "inventory_state": {"items": [], "currency": {"silver": 20}},
        }
    }

    result = buy_from_merchant(state, item_id="healing_potion", qty=1, tick=2)
    modifier = result["price_modifier"]["price_modifier"]
    rows = {row["modifier"]: row for row in modifier["modifiers"]}

    assert result["resolved"] is True
    assert result["price"] == {"gold": 0, "silver": 9, "copper": 3}
    assert modifier["multiplier_bps"] == 9300
    assert rows["charisma"]["basis_points_delta"] == -400
    assert rows["relationship"]["basis_points_delta"] == -200
    assert rows["reputation"]["basis_points_delta"] == -100
    assert rows["scarcity"]["basis_points_delta"] == 0


def test_ci_phase2_price_modifier_bad_social_state_and_scarcity_raise_buy_price():
    from app.rpg.economy.merchant_transactions import buy_from_merchant

    state = {
        "player_state": {
            "stats": {"charisma": 6},
            "relationships": {"merchant:elara": {"score": -25}},
            "reputation": {"local": -20},
            "inventory_state": {"items": [], "currency": {"silver": 20}},
        },
        "economy_state": {
            "merchants": {
                "merchant:elara": {
                    "merchant_id": "merchant:elara",
                    "stock": [
                        {"item_id": "healing_potion", "qty": 1, "price": {"silver": 10}},
                    ],
                    "currency": {},
                    "transaction_log": [],
                }
            }
        },
    }

    result = buy_from_merchant(state, item_id="healing_potion", qty=1, tick=3)
    modifier = result["price_modifier"]["price_modifier"]
    rows = {row["modifier"]: row for row in modifier["modifiers"]}

    assert result["resolved"] is True
    assert result["price"] == {"gold": 0, "silver": 11, "copper": 6}
    assert modifier["multiplier_bps"] == 11600
    assert rows["charisma"]["basis_points_delta"] == 400
    assert rows["relationship"]["basis_points_delta"] == 200
    assert rows["reputation"]["basis_points_delta"] == 100
    assert rows["scarcity"]["basis_points_delta"] == 900


def test_ci_phase2_price_modifier_sell_uses_inverse_social_effects_and_logs_source():
    from app.rpg.economy.merchant_transactions import sell_to_merchant

    state = {
        "player_state": {
            "stats": {"charisma": 14},
            "relationships": {"merchant:elara": {"score": 25}},
            "reputation": {"local": 20},
            "inventory_state": {
                "items": [{"item_id": "combat_knife", "qty": 1}],
                "currency": {"silver": 0},
            },
        }
    }

    result = sell_to_merchant(state, item_id="combat_knife", qty=1, tick=4)
    modifier = result["price_modifier"]["price_modifier"]
    rows = {row["modifier"]: row for row in modifier["modifiers"]}

    assert result["resolved"] is True
    assert result["price"] == {"gold": 0, "silver": 5, "copper": 4}
    assert modifier["multiplier_bps"] == 5350
    assert rows["charisma"]["basis_points_delta"] == 200
    assert rows["relationship"]["basis_points_delta"] == 100
    assert rows["reputation"]["basis_points_delta"] == 50
    assert rows["scarcity"]["basis_points_delta"] == 0
    assert result["transaction_log_entry"]["price_modifier"]["source"] == "deterministic_price_modifiers"
