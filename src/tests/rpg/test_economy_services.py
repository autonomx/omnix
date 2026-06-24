from __future__ import annotations

import pytest

from app.rpg.economy_services import Currency, MerchantInventory, MerchantStockItem, ServiceOffer, adjusted_price, authorize_service, buy_item, restock_item


def _inventory() -> MerchantInventory:
    return MerchantInventory(
        "elara",
        {
            "ration": MerchantStockItem("ration", "Travel Ration", Currency.from_gsc(silver=1), 3),
            "lamp": MerchantStockItem("lamp", "Lamp", Currency.from_gsc(copper=5), 2),
        },
    )


def test_currency_converts_gold_silver_copper() -> None:
    value = Currency.from_gsc(gold=1, silver=2, copper=3)

    assert value.copper == 123
    assert value.as_gsc() == {"gold": 1, "silver": 2, "copper": 3}


def test_authorize_service_requires_payment_or_exception() -> None:
    room = ServiceOffer("room", "Room", Currency.from_gsc(silver=5), "bran")

    assert authorize_service(room, Currency.from_gsc(silver=4)).ok is False
    assert authorize_service(room, Currency.from_gsc(silver=5)).currency_after.copper == 0
    assert authorize_service(room, Currency.from_gsc(), exception="comped").reason == "service_comped"


def test_adjusted_price_supports_discount_and_surcharge() -> None:
    base = Currency.from_gsc(silver=10)

    assert adjusted_price(base, -10).copper == 90
    assert adjusted_price(base, 25).copper == 125


def test_buy_item_updates_inventory_and_wallet() -> None:
    inventory, wallet = buy_item(_inventory(), Currency.from_gsc(silver=5), "ration", 2)

    assert inventory.stock["ration"].quantity == 1
    assert wallet.as_gsc() == {"gold": 0, "silver": 3, "copper": 0}


def test_buy_item_rejects_bad_requests() -> None:
    with pytest.raises(ValueError):
        buy_item(_inventory(), Currency.from_gsc(silver=5), "ration", 0)
    with pytest.raises(ValueError):
        buy_item(_inventory(), Currency.from_gsc(silver=5), "ration", 9)


def test_restock_item_adds_quantity() -> None:
    inventory = restock_item(_inventory(), "lamp", 4)

    assert inventory.stock["lamp"].quantity == 6
