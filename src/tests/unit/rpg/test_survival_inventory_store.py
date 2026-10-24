"""Eating and drinking take from the player's one inventory store (RQ-1.1 / RQ-2.4)."""
from __future__ import annotations

from app.apps.rpg.rules.interactions import survival_action_runtime as survival


def test_eating_takes_food_from_the_store_not_a_second_copy() -> None:
    state = {"player_state": {
        "inventory_state": {"items": [{"item_id": "item:lantern-bread", "name": "Lantern Bread", "qty": 2,
                                       "category": "food"}], "equipment": {}},
        "inventory": {"items": [], "equipment": {}},  # a stale sheet-side copy
    }}

    removed, item, _result = survival._remove_one_inventory_item(state, {"bread"})

    assert removed and item["item_id"] == "item:lantern-bread"
    [left] = state["player_state"]["inventory_state"]["items"]
    assert int(left.get("qty") or left.get("quantity") or 0) == 1
