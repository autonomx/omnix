from app.rpg.session.item_market import (
    build_merchant_catalog,
    copper_to_currency,
    find_offer,
    quote_merchant_transaction,
    value_to_copper,
)


def test_currency_helpers_normalize_values():
    assert value_to_copper({"gold": 1, "silver": 2, "copper": 3}) == 123
    assert value_to_copper(17) == 17
    assert copper_to_currency(123) == {"gold": 1, "silver": 2, "copper": 3}


def test_general_store_catalog_is_deterministic_and_traced():
    first = build_merchant_catalog("general_store", genre="classic_fantasy", level=1)
    second = build_merchant_catalog("general_store", genre="classic_fantasy", level=1)

    assert first == second
    assert first["ok"] is True
    assert first["profile"] == "general_store"
    assert [offer["item_id"] for offer in first["offers"]] == ["ration", "torch", "waterskin", "bedroll", "rope_coil"]
    assert first["trace"]["mechanics_source"] == "engine_item_market_v1"
    assert first["trace"]["offer_count"] == 5


def test_unknown_profile_falls_back_to_general_store():
    catalog = build_merchant_catalog("unknown_vendor")

    assert catalog["profile"] == "general_store"
    assert find_offer(catalog, "ration") is not None


def test_profile_controls_available_stock():
    catalog = build_merchant_catalog("apothecary")

    ids = [offer["item_id"] for offer in catalog["offers"]]
    assert ids == ["health_potion", "mana_potion", "keenleaf", "focus_crystal"]
    assert find_offer(catalog, "health_potion")["quantity"] == 2


def test_reputation_improves_buy_price():
    neutral = build_merchant_catalog("general_store", reputation=0)
    friendly = build_merchant_catalog("general_store", reputation=5)

    neutral_price = find_offer(neutral, "rope_coil")["buy_price"]["copper_total"]
    friendly_price = find_offer(friendly, "rope_coil")["buy_price"]["copper_total"]
    assert friendly_price < neutral_price


def test_quote_buy_transaction_checks_stock_and_totals():
    catalog = build_merchant_catalog("general_store")

    quote = quote_merchant_transaction(catalog, "ration", action="buy", quantity=2)

    assert quote["ok"] is True
    assert quote["action"] == "buy"
    assert quote["item_id"] == "ration"
    assert quote["quantity"] == 2
    assert quote["total_price"]["copper_total"] == quote["unit_price"]["copper_total"] * 2
    assert quote["mechanics_source"] == "engine_item_market_v1"

    too_many = quote_merchant_transaction(catalog, "waterskin", action="buy", quantity=3)
    assert too_many["ok"] is False
    assert too_many["error"] == "insufficient_stock"


def test_quote_sell_transaction_uses_sell_price():
    catalog = build_merchant_catalog("outfitter")

    quote = quote_merchant_transaction(catalog, "travelers_cloak", action="sell", quantity=1)
    offer = find_offer(catalog, "travelers_cloak")

    assert quote["ok"] is True
    assert quote["total_price"] == offer["sell_price"]


def test_missing_or_unsupported_quote_returns_error():
    catalog = build_merchant_catalog("general_store")

    assert quote_merchant_transaction(catalog, "missing", action="buy")["error"] == "offer_not_found"
    assert quote_merchant_transaction(catalog, "ration", action="trade")["error"] == "unsupported_market_action"
