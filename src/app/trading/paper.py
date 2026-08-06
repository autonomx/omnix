from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


PaperSide = Literal["buy", "sell"]
PaperOrderType = Literal["market", "limit", "stop"]
PaperOrderStatus = Literal["open", "filled", "cancelled", "rejected"]


class PaperAccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    base_currency: str = Field(default="USD", min_length=3, max_length=12)
    initial_cash: Decimal = Field(default=Decimal("100000"), ge=0)
    commission_bps: Decimal = Field(default=Decimal("0"), ge=0, le=1000)


class PaperAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    name: str
    base_currency: str
    commission_bps: Decimal
    enabled: bool = True
    revision: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PaperBalance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str
    available: Decimal
    reserved: Decimal = Decimal("0")


class PaperPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument_id: str
    quantity: Decimal
    average_cost: Decimal
    realized_pnl: Decimal
    last_price: Decimal | None = None
    unrealized_pnl: Decimal = Decimal("0")


class PaperOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(min_length=1, max_length=200)
    instrument_id: str = Field(min_length=3, max_length=200)
    binding_id: str | None = Field(default=None, max_length=240)
    side: PaperSide
    order_type: PaperOrderType
    quantity: Decimal = Field(gt=0)
    limit_price: Decimal | None = Field(default=None, gt=0)
    stop_price: Decimal | None = Field(default=None, gt=0)
    idempotency_key: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_prices(self):
        if self.order_type == "limit" and self.limit_price is None:
            raise ValueError("limit orders require limit_price")
        if self.order_type == "stop" and self.stop_price is None:
            raise ValueError("stop orders require stop_price")
        if self.order_type == "market" and (
            self.limit_price is not None or self.stop_price is not None
        ):
            raise ValueError("market orders cannot include limit_price or stop_price")
        return self


class PaperOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    order_id: str
    instrument_id: str
    binding_id: str | None = None
    side: PaperSide
    order_type: PaperOrderType
    quantity: Decimal
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    status: PaperOrderStatus = "open"
    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Decimal | None = None
    idempotency_key: str
    rejection_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PaperMarketObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument_id: str
    binding_id: str | None = None
    provider: str | None = None
    price: Decimal = Field(gt=0)
    source_time: datetime
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PaperFillDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    should_fill: bool
    fill_price: Decimal | None = None
    reason: str


class PaperFill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fill_id: str
    order_id: str
    instrument_id: str
    side: PaperSide
    quantity: Decimal
    price: Decimal
    commission: Decimal
    source_time: datetime
    evaluated_at: datetime
    idempotency_key: str


class PaperLedgerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ledger_id: str
    entry_type: Literal[
        "deposit", "withdrawal", "trade_cash", "commission", "realized_pnl"
    ]
    currency: str
    amount: Decimal
    order_id: str | None = None
    fill_id: str | None = None
    idempotency_key: str
    payload: dict[str, object] = Field(default_factory=dict)


class PaperAccountSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account: PaperAccount
    balances: list[PaperBalance]
    positions: list[PaperPosition]
    open_orders: list[PaperOrder]
    recent_fills: list[PaperFill]
    recent_ledger: list[PaperLedgerEntry]


def paper_fill_decision(
    order: PaperOrder,
    observation: PaperMarketObservation,
) -> PaperFillDecision:
    if order.status != "open":
        return PaperFillDecision(should_fill=False, reason="order_not_open")
    if order.instrument_id != observation.instrument_id:
        return PaperFillDecision(should_fill=False, reason="instrument_mismatch")
    if order.binding_id and order.binding_id != observation.binding_id:
        return PaperFillDecision(should_fill=False, reason="binding_mismatch")
    if order.order_type == "market":
        return PaperFillDecision(
            should_fill=True,
            fill_price=observation.price,
            reason="market_observation",
        )
    if order.order_type == "limit":
        triggered = (
            observation.price <= order.limit_price
            if order.side == "buy"
            else observation.price >= order.limit_price
        )
        return PaperFillDecision(
            should_fill=bool(triggered),
            fill_price=observation.price if triggered else None,
            reason="limit_reached" if triggered else "limit_not_reached",
        )
    triggered = (
        observation.price >= order.stop_price
        if order.side == "buy"
        else observation.price <= order.stop_price
    )
    return PaperFillDecision(
        should_fill=bool(triggered),
        fill_price=observation.price if triggered else None,
        reason="stop_triggered" if triggered else "stop_not_triggered",
    )


def paper_commission(notional: Decimal, commission_bps: Decimal) -> Decimal:
    return notional * commission_bps / Decimal("10000")


def paper_fill_key(
    account_id: str,
    order_id: str,
    observation: PaperMarketObservation,
) -> str:
    raw = (
        f"{account_id}|{order_id}|{observation.instrument_id}|"
        f"{observation.source_time.isoformat()}|{observation.price}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def paper_unrealized_pnl(
    quantity: Decimal,
    average_cost: Decimal,
    last_price: Decimal,
) -> Decimal:
    return (last_price - average_cost) * quantity


def paper_realized_pnl(
    quantity: Decimal,
    average_cost: Decimal,
    fill_price: Decimal,
) -> Decimal:
    return (fill_price - average_cost) * quantity
