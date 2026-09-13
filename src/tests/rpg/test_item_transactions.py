from app.rpg.session.inventory_items import inventory_quantity
from app.rpg.session.item_market import build_merchant_catalog, find_offer, value_to_copper
from app.rpg.session.item_system import build_item_catalog
from app.rpg.session.item_transactions import apply_item_transaction, player_currency_copper, set_player_currency


def test_player_currency_helpers_support_nested_and_flat_shapes():
    player = {"currency": {"gold": 1, "silver": 2, "copper": 3}}
    assert player_currency_copper(player) == 123

    flat = {"gold": 1, "silver": 0, "copper": 5}
    assert player_currency_copper(flat) == 105
    assert set_player_currency(flat, 47) == {"gold": 0, "silver": 4, "copper": 7}
    assert flat["gold"] == 0
    assert flat["silver"] == 4
    assert flat["copper"] == 7


def test_buy_transaction_debits_currency_and_adds_inventory_stack():
    catalog = build_merchant_catalog("general_store")
    torch_offer = find_offer(catalog, "torch")
    player = {"currency": {"gold": 1, "silver": 0, "copper": 0}, "inventory": []}

    result = apply_item_transaction(player, catalog, "torch", action="buy", quantity=2)

    assert result["ok"] is True
    assert result["action"] == "buy"
    assert result["quote"]["quantity"] == 2
    assert player["inventory"] == []
    assert player["currency"] == {"gold": 1, "silver": 0, "copper": 0}
    assert player_currency_copper(result["player"]) == 100 - result["quote"]["total_price"]["copper_total"]
    assert result["player"]["inventory"][0]["item_id"] == "torch"
    assert result["player"]["inventory"][0]["quantity"] == 2
    assert find_offer(result["catalog"], "torch")["quantity"] == torch_offer["quantity"] - 2
    assert result["trace"]["event"] == "item_transaction_applied"
    assert result["trace"]["action"] == "buy"


def test_buy_transaction_rejects_insufficient_currency():
    catalog = build_merchant_catalog("apothecary")
    player = {"currency": {"gold": 0, "silver": 0, "copper": 1}, "inventory": []}

    result = apply_item_transaction(player, catalog, "health_potion", action="buy", quantity=1)

    assert result["ok"] is False
    assert result["error"] == "insufficient_currency"
    assert result["available"] == 1
    assert result["player"]["inventory"] == []


def test_sell_transaction_removes_inventory_and_credits_currency():
    item = build_item_catalog()["ration"]
    catalog = build_merchant_catalog("general_store")
    player = {"currency": {"gold": 0, "silver": 0, "copper": 0}, "inventory": [{**item, "quantity": 3}]}
    expected_quote = apply_item_transaction(player, catalog, "ration", action="sell", quantity=2)["quote"]

    result = apply_item_transaction(player, catalog, "ration", action="sell", quantity=2)

    assert result["ok"] is True
    assert result["action"] == "sell"
    assert player_currency_copper(result["player"]) == expected_quote["total_price"]["copper_total"]
    assert result["player"]["inventory"][0]["item_id"] == "ration"
    assert inventory_quantity(result["player"]["inventory"][0]) == 1
    assert result["item"]["item_id"] == "ration"
    assert result["item"]["quantity"] == 2
    assert result["trace"]["currency_after"]["copper_total"] == expected_quote["total_price"]["copper_total"]


def test_sell_transaction_rejects_missing_or_short_inventory():
    catalog = build_merchant_catalog("general_store")
    player = {"currency": {"gold": 0, "silver": 0, "copper": 0}, "inventory": []}

    missing = apply_item_transaction(player, catalog, "ration", action="sell", quantity=1)
    assert missing["ok"] is False
    assert missing["error"] == "item_not_owned"

    item = build_item_catalog()["ration"]
    short = apply_item_transaction(
        {"currency": {"gold": 0, "silver": 0, "copper": 0}, "inventory": [{**item, "quantity": 1}]},
        catalog,
        "ration",
        action="sell",
        quantity=2,
    )
    assert short["ok"] is False
    assert short["error"] == "insufficient_inventory"


def test_unknown_catalog_offer_is_rejected():
    catalog = build_merchant_catalog("general_store")
    player = {"currency": {"gold": 1, "silver": 0, "copper": 0}, "inventory": []}

    result = apply_item_transaction(player, catalog, "focus_crystal", action="buy", quantity=1)

    assert result["ok"] is False
    assert result["error"] == "offer_not_found"
    assert value_to_copper(result["player"]["currency"]) == 100
