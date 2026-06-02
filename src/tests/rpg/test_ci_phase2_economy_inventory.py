def test_ci_phase2_starter_loadout_grants_currency_items_and_is_idempotent():
    from app.rpg.economy.currency import get_player_currency
    from app.rpg.economy.starter_loadout import (
        SOURCE,
        build_starter_loadout,
        ensure_player_starter_loadout,
    )

    loadout = build_starter_loadout()
    assert loadout["source"] == SOURCE
    assert loadout["currency"] == {"gold": 0, "silver": 15, "copper": 0}

    state = {"player_state": {}}
    updated = ensure_player_starter_loadout(state)
    player_state = updated["player_state"]
    inventory_state = player_state["inventory_state"]
    item_ids = {item["item_id"]: item["qty"] for item in inventory_state["items"]}

    assert get_player_currency(updated) == {"gold": 0, "silver": 15, "copper": 0}
    assert item_ids == {
        "combat_knife": 1,
        "healing_potion": 1,
        "bandit_token": 1,
    }
    assert player_state["starter_loadout_source"] == SOURCE

    second = ensure_player_starter_loadout(updated)
    second_items = second["player_state"]["inventory_state"]["items"]
    assert second_items == inventory_state["items"]
    assert get_player_currency(second) == {"gold": 0, "silver": 15, "copper": 0}


def test_ci_phase2_starter_loadout_preserves_existing_inventory_and_currency():
    from app.rpg.economy.currency import get_player_currency
    from app.rpg.economy.starter_loadout import ensure_player_starter_loadout

    state = {
        "player_state": {
            "inventory_state": {
                "items": [{"item_id": "rusty_sword", "qty": 1}],
                "currency": {"gold": 1, "silver": 2, "copper": 3},
            }
        }
    }

    updated = ensure_player_starter_loadout(state)
    inventory_state = updated["player_state"]["inventory_state"]

    assert get_player_currency(updated) == {"gold": 1, "silver": 2, "copper": 3}
    assert [item["item_id"] for item in inventory_state["items"]] == ["rusty_sword"]
    assert updated["player_state"]["starter_loadout_source"] == "deterministic_starter_loadout"
