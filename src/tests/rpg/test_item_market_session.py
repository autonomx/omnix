from __future__ import annotations

from typing import Any

from app.rpg.session.item_market_session import apply_session_market_action, market_offer_quantities


def _state() -> dict[str, Any]:
    return {
        "current_turn": 3,
        "turn_count": 3,
        "metadata": {"genre": "classic_fantasy"},
        "player": {
            "level": 1,
            "currency": {"gold": 1, "silver": 0, "copper": 0},
            "inventory": [],
        },
    }


def test_session_market_buy_mutates_currency_inventory_catalog_and_trace() -> None:
    state = _state()

    result = apply_session_market_action(state, "ration", action="buy", quantity=2, merchant_profile="general_store")

    assert result["ok"] is True
    assert result["action"] == "buy"
    assert result["merchant_profile"] == "general_store"
    inventory = state["player"]["inventory"]
    ration = next(item for item in inventory if item.get("item_id") == "ration")
    assert ration["quantity"] == 2
    assert state["player"]["currency"] != {"gold": 1, "silver": 0, "copper": 0}
    assert market_offer_quantities(state)["ration"] == 2
    trace = state["mechanics"]["market_traces"][0]
    assert trace["event"] == "item_transaction_applied"
    assert trace["mechanics_source"] == "engine_item_market_session_v1"
    assert trace["action"] == "buy"
    assert trace["item_id"] == "ration"
    assert state["mechanics"]["item_traces"][0] == trace


def test_session_market_sell_mutates_inventory_currency_catalog_and_trace() -> None:
    state = _state()
    state["player"]["currency"] = {"gold": 0, "silver": 0, "copper": 0}
    state["player"]["inventory"] = [{"id": "ration", "item_id": "ration", "name": "Ration", "quantity": 2, "stackable": True}]
    apply_session_market_action(state, "ration", action="buy", quantity=1, merchant_profile="general_store")
    state["player"]["currency"] = {"gold": 0, "silver": 0, "copper": 0}
    state["player"]["inventory"] = [{"id": "ration", "item_id": "ration", "name": "Ration", "quantity": 2, "stackable": True}]
    before_stock = market_offer_quantities(state)["ration"]

    result = apply_session_market_action(state, "ration", action="sell", quantity=1, merchant_profile="general_store")

    assert result["ok"] is True
    assert result["action"] == "sell"
    ration = next(item for item in state["player"]["inventory"] if item.get("item_id") == "ration")
    assert ration["quantity"] == 1
    assert state["player"]["currency"]["copper"] > 0
    assert market_offer_quantities(state)["ration"] == before_stock + 1
    trace = state["mechanics"]["market_traces"][0]
    assert trace["action"] == "sell"
    assert trace["price"]["copper_total"] > 0


def test_session_market_buy_rejects_insufficient_currency_without_trace() -> None:
    state = _state()
    state["player"]["currency"] = {"gold": 0, "silver": 0, "copper": 0}

    result = apply_session_market_action(state, "rope_coil", action="buy", quantity=1, merchant_profile="general_store")

    assert result["ok"] is False
    assert result["error"] == "insufficient_currency"
    assert state["player"]["inventory"] == []
    assert "mechanics" not in state


def test_session_market_sell_rejects_missing_inventory_without_trace() -> None:
    state = _state()

    result = apply_session_market_action(state, "ration", action="sell", quantity=1, merchant_profile="general_store")

    assert result["ok"] is False
    assert result["error"] == "item_not_owned"
    assert "mechanics" not in state
