"""Deterministic RPG currency, merchant, and service helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Mapping

ServiceException = Literal["paid", "persuaded", "credit", "sponsored", "stolen", "comped", "quest_authorized"]
COPPER_PER_SILVER = 10
SILVER_PER_GOLD = 10
COPPER_PER_GOLD = COPPER_PER_SILVER * SILVER_PER_GOLD


@dataclass(frozen=True)
class Currency:
    copper: int = 0

    @classmethod
    def from_gsc(cls, *, gold: int = 0, silver: int = 0, copper: int = 0) -> "Currency":
        return cls(gold * COPPER_PER_GOLD + silver * COPPER_PER_SILVER + copper)

    def as_gsc(self) -> dict[str, int]:
        remaining = max(0, self.copper)
        gold, remaining = divmod(remaining, COPPER_PER_GOLD)
        silver, copper = divmod(remaining, COPPER_PER_SILVER)
        return {"gold": gold, "silver": silver, "copper": copper}

    def can_afford(self, price: "Currency") -> bool:
        return self.copper >= price.copper

    def add(self, value: "Currency") -> "Currency":
        return Currency(self.copper + value.copper)

    def subtract(self, value: "Currency") -> "Currency":
        if not self.can_afford(value):
            raise ValueError("insufficient currency")
        return Currency(self.copper - value.copper)


@dataclass(frozen=True)
class MerchantStockItem:
    item_id: str
    name: str
    price: Currency
    quantity: int


@dataclass(frozen=True)
class MerchantInventory:
    merchant_id: str
    stock: Mapping[str, MerchantStockItem]

    def item(self, item_id: str) -> MerchantStockItem | None:
        return self.stock.get(item_id)

    def with_quantity(self, item_id: str, quantity: int) -> "MerchantInventory":
        stock = dict(self.stock)
        item = stock[item_id]
        stock[item_id] = replace(item, quantity=max(0, quantity))
        return replace(self, stock=stock)


@dataclass(frozen=True)
class ServiceOffer:
    service_id: str
    name: str
    price: Currency
    provider_id: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ServiceResolution:
    ok: bool
    service_id: str
    reason: str
    currency_after: Currency
    exception: ServiceException | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "service_id": self.service_id,
            "reason": self.reason,
            "currency_after": self.currency_after.as_gsc(),
            "exception": self.exception,
        }


def adjusted_price(base_price: Currency, adjustment_percent: int) -> Currency:
    adjusted = round(base_price.copper * (100 + adjustment_percent) / 100)
    return Currency(max(0, adjusted))


def authorize_service(
    offer: ServiceOffer,
    wallet: Currency,
    *,
    exception: ServiceException | None = None,
) -> ServiceResolution:
    if exception and exception != "paid":
        return ServiceResolution(True, offer.service_id, f"service_{exception}", wallet, exception)
    if not wallet.can_afford(offer.price):
        return ServiceResolution(False, offer.service_id, "insufficient_currency", wallet)
    return ServiceResolution(True, offer.service_id, "paid", wallet.subtract(offer.price), "paid")


def buy_item(inventory: MerchantInventory, wallet: Currency, item_id: str, quantity: int = 1) -> tuple[MerchantInventory, Currency]:
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    item = inventory.item(item_id)
    if item is None:
        raise KeyError(f"unknown stock item: {item_id}")
    if item.quantity < quantity:
        raise ValueError("insufficient stock")
    total_price = Currency(item.price.copper * quantity)
    updated_wallet = wallet.subtract(total_price)
    return inventory.with_quantity(item_id, item.quantity - quantity), updated_wallet


def restock_item(inventory: MerchantInventory, item_id: str, quantity: int) -> MerchantInventory:
    item = inventory.item(item_id)
    if item is None:
        raise KeyError(f"unknown stock item: {item_id}")
    return inventory.with_quantity(item_id, item.quantity + max(0, quantity))
