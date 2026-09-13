from __future__ import annotations

from typing import Any

from app.rpg.session.item_merchant_commands import (
    apply_item_merchant_command,
    build_item_merchant_command_plan,
)


def _state() -> dict[str, Any]:
    return {
        "current_turn": 7,
        "turn_count": 7,
        "metadata": {"genre": "classic_fantasy"},
        "player": {
            "level": 1,
            "currency": {"gold": 1, "silver": 0, "copper": 0},
            "inventory": [
                {"id": "ration", "item_id": "ration", "name": "Ration", "quantity": 2, "stackable": True}
            ],
        },
    }


def test_build_item_merchant_command_plan_from_text_buy_quantity() -> None:
    plan = build_item_merchant_command_plan("buy 2 torch")

    assert plan["ok"] is True
    assert plan["handled"] is True
    assert plan["service_action"] == "buy"
    assert plan["item_id"] == "torch"
    assert plan["quantity"] == 2
    assert plan["mechanics_source"] == "engine_item_merchant_commands_v1"


def test_build_item_merchant_command_plan_from_dict_sell() -> None:
    plan = build_item_merchant_command_plan(
        {"action": "sell", "item_id": "ration", "quantity": 1, "merchant_profile": "general_store"}
    )

    assert plan["handled"] is True
    assert plan["service_action"] == "sell"
    assert plan["item_id"] == "ration"
    assert plan["quantity"] == 1
    assert plan["merchant_profile"] == "general_store"


def test_apply_item_merchant_command_menu_records_menu_trace() -> None:
    state = _state()

    result = apply_item_merchant_command(state, "shop")

    assert result["ok"] is True
    assert result["handled"] is True
    assert result["menu"]["buy_offers"]
    trace = state["mechanics"]["item_merchant_service_traces"][0]
    assert trace["event"] == "item_merchant_menu_built"


def test_apply_item_merchant_command_buy_mutates_inventory() -> None:
    state = _state()

    result = apply_item_merchant_command(state, "buy torch")

    assert result["ok"] is True
    assert result["handled"] is True
    assert result["result"]["action"] == "buy"
    assert any(item.get("item_id") == "torch" for item in state["player"]["inventory"])
    service_trace = state["mechanics"]["item_merchant_service_traces"][0]
    assert service_trace["event"] == "item_merchant_selection_applied"
    assert service_trace["action"] == "buy"


def test_apply_item_merchant_command_sell_mutates_currency() -> None:
    state = _state()
    state["player"]["currency"] = {"gold": 0, "silver": 0, "copper": 0}

    result = apply_item_merchant_command(state, "sell ration")

    assert result["ok"] is True
    assert result["result"]["action"] == "sell"
    assert state["player"]["currency"]["copper"] > 0
    ration = next(item for item in state["player"]["inventory"] if item.get("item_id") == "ration")
    assert ration["quantity"] == 1


def test_apply_item_merchant_command_non_merchant_skips_without_trace() -> None:
    state = _state()

    result = apply_item_merchant_command(state, "travel north")

    assert result["ok"] is True
    assert result["handled"] is False
    assert result["skipped"] is True
    assert "mechanics" not in state
