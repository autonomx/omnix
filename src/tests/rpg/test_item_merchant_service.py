from __future__ import annotations

from typing import Any

from app.rpg.session.item_merchant_service import build_item_merchant_menu, apply_item_merchant_selection


def _state() -> dict[str, Any]:
    return {
        "current_turn": 6,
        "turn_count": 6,
        "metadata": {"genre": "classic_fantasy"},
        "player": {
            "level": 1,
            "currency": {"gold": 1, "silver": 0, "copper": 0},
            "inventory": [
                {"id": "ration", "item_id": "ration", "name": "Ration", "quantity": 2, "stackable": True}
            ],
        },
    }


def test_build_item_merchant_menu_caches_catalog_and_records_trace() -> None:
    state = _state()

    result = build_item_merchant_menu(state, merchant_profile="general_store")

    assert result["ok"] is True
    assert result["merchant_profile"] == "general_store"
    assert any(offer["item_id"] == "ration" for offer in result["buy_offers"])
    assert any(offer["item_id"] == "ration" for offer in result["sell_offers"])
    assert state["item_market"]["catalogs"]["general_store"]["offers"]
    trace = state["mechanics"]["item_merchant_service_traces"][0]
    assert trace["event"] == "item_merchant_menu_built"
    assert trace["mechanics_source"] == "engine_item_merchant_service_v1"
    assert state["mechanics"]["item_traces"][0] == trace


def test_apply_item_merchant_buy_selection_mutates_and_records_service_trace() -> None:
    state = _state()
    starting_inventory_len = len(state["player"]["inventory"])

    result = apply_item_merchant_selection(
        state,
        "torch",
        action="buy",
        quantity=1,
        merchant_profile="general_store",
    )

    assert result["ok"] is True
    assert result["action"] == "buy"
    assert result["merchant_profile"] == "general_store"
    assert len(state["player"]["inventory"]) == starting_inventory_len + 1
    assert any(item.get("item_id") == "torch" for item in state["player"]["inventory"])
    service_trace = state["mechanics"]["item_merchant_service_traces"][0]
    assert service_trace["event"] == "item_merchant_selection_applied"
    assert service_trace["action"] == "buy"
    assert service_trace["market_trace"]["action"] == "buy"
    assert state["mechanics"]["market_traces"][0]["action"] == "buy"


def test_apply_item_merchant_sell_selection_mutates_and_records_service_trace() -> None:
    state = _state()
    state["player"]["currency"] = {"gold": 0, "silver": 0, "copper": 0}

    result = apply_item_merchant_selection(
        state,
        "ration",
        action="sell",
        quantity=1,
        merchant_profile="general_store",
    )

    assert result["ok"] is True
    assert result["action"] == "sell"
    ration = next(item for item in state["player"]["inventory"] if item.get("item_id") == "ration")
    assert ration["quantity"] == 1
    assert state["player"]["currency"]["copper"] > 0
    service_trace = state["mechanics"]["item_merchant_service_traces"][0]
    assert service_trace["action"] == "sell"
    assert service_trace["market_trace"]["action"] == "sell"


def test_apply_item_merchant_selection_rejects_bad_action_without_trace() -> None:
    state = _state()

    result = apply_item_merchant_selection(state, "ration", action="haggle", merchant_profile="general_store")

    assert result["ok"] is False
    assert result["error"] == "unsupported_merchant_service_action"
    assert "mechanics" not in state


def test_apply_item_merchant_selection_failure_does_not_record_service_trace() -> None:
    state = _state()
    state["player"]["currency"] = {"gold": 0, "silver": 0, "copper": 0}

    result = apply_item_merchant_selection(state, "rope_coil", action="buy", merchant_profile="general_store")

    assert result["ok"] is False
    assert result["error"] == "insufficient_currency"
    mechanics = state.get("mechanics")
    assert mechanics is None or "item_merchant_service_traces" not in mechanics
