from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


PaperSide = Literal["buy", "sell"]
PaperOrderType = Literal["market", "limit", "stop"]
PaperOrderStatus = Literal["open", "filled", "cancelled", "rejected"]
ProtectionTrigger = Literal["stop", "target"]


class PaperExecutionPolicy(BaseModel):
    """Deterministic, pessimistic paper-fill assumptions shared with backtests."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal["paper-execution-v2"] = "paper-execution-v2"
    slippage_bps: Decimal = Field(default=Decimal("10"), ge=0, le=5_000)
    stop_slippage_bps: Decimal = Field(default=Decimal("25"), ge=0, le=10_000)
    max_volume_participation_pct: Decimal = Field(default=Decimal("0.10"), gt=0, le=1)
    max_observation_age_seconds: Decimal = Field(default=Decimal("5"), gt=0, le=300)
    latency_ms: int = Field(default=250, ge=0, le=60_000)
    require_execution_eligible: bool = True
    reject_halted: bool = True


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
    reserved_quantity: Decimal = Decimal("0")
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
    reference_price: Decimal | None = Field(default=None, gt=0)
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
        if self.order_type != "market" and self.reference_price is not None:
            raise ValueError("reference_price is only valid for market orders")
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
    reference_price: Decimal | None = None
    status: PaperOrderStatus = "open"
    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Decimal | None = None
    idempotency_key: str
    rejection_reason: str | None = None
    reserved_cash: Decimal = Decimal("0")
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PaperMarketObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument_id: str
    binding_id: str | None = None
    provider: str | None = None
    price: Decimal = Field(gt=0)
    bid: Decimal | None = Field(default=None, gt=0)
    ask: Decimal | None = Field(default=None, gt=0)
    bid_size: Decimal | None = Field(default=None, ge=0)
    ask_size: Decimal | None = Field(default=None, ge=0)
    high: Decimal | None = Field(default=None, gt=0)
    low: Decimal | None = Field(default=None, gt=0)
    volume: Decimal | None = Field(default=None, ge=0)
    bar_start_time: datetime | None = None
    source_time: datetime
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    execution_eligible: bool = True
    freshness_mode: str = "unknown"
    rejection_reasons: tuple[str, ...] = ()
    halted: bool = False

    @model_validator(mode="after")
    def validate_range(self):
        if self.source_time.tzinfo is None or self.evaluated_at.tzinfo is None:
            raise ValueError("paper observation timestamps must be timezone-aware")
        if self.bar_start_time is not None and self.bar_start_time.tzinfo is None:
            raise ValueError("paper bar_start_time must be timezone-aware")
        if self.high is not None and self.low is not None and self.low > self.high:
            raise ValueError("paper observation low cannot exceed high")
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("paper observation bid cannot exceed ask")
        return self

    @property
    def age_seconds(self) -> Decimal:
        seconds = (self.evaluated_at - self.source_time).total_seconds()
        return max(Decimal("0"), Decimal(str(seconds)))


class PaperFillDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    should_fill: bool
    fill_price: Decimal | None = None
    fill_quantity: Decimal | None = None
    reason: str
    policy_version: str = "paper-execution-v2"


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
    created_at: datetime | None = None


class PaperAccountSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account: PaperAccount
    balances: list[PaperBalance]
    positions: list[PaperPosition]
    open_orders: list[PaperOrder]
    order_history: list[PaperOrder] = Field(default_factory=list)
    recent_fills: list[PaperFill]
    recent_ledger: list[PaperLedgerEntry]


def paper_order_request_matches(order: PaperOrder, request: PaperOrderRequest) -> bool:
    return (
        order.order_id == request.order_id
        and order.instrument_id == request.instrument_id
        and order.binding_id == request.binding_id
        and order.side == request.side
        and order.order_type == request.order_type
        and order.quantity == request.quantity
        and order.limit_price == request.limit_price
        and order.stop_price == request.stop_price
        and order.reference_price == request.reference_price
    )


def _worse_price(price: Decimal, side: PaperSide, bps: Decimal) -> Decimal:
    fraction = bps / Decimal("10000")
    return price * (Decimal("1") + fraction if side == "buy" else Decimal("1") - fraction)


def _order_activation_time(
    order: PaperOrder,
    policy: PaperExecutionPolicy,
) -> datetime | None:
    if order.created_at is None:
        return None
    return order.created_at.astimezone(timezone.utc) + timedelta(milliseconds=policy.latency_ms)


def _bar_evidence_is_causal(
    order: PaperOrder,
    observation: PaperMarketObservation,
    policy: PaperExecutionPolicy,
) -> bool:
    """Whether the whole observed bar happened after this order became executable.

    A bar that started before activation may contain a trigger or traded volume
    that occurred before the order existed. Only point-in-time quote/last-price
    evidence is safe in that case.
    """
    activation = _order_activation_time(order, policy)
    if activation is None:
        return True
    if observation.bar_start_time is None:
        return False
    return observation.bar_start_time.astimezone(timezone.utc) >= activation


def _liquidity_capacity(
    order: PaperOrder,
    observation: PaperMarketObservation,
    policy: PaperExecutionPolicy,
) -> Decimal | None:
    """Return side-specific executable capacity without pre-activation volume.

    Live observations prefer displayed top-of-book size. Historical/backtest
    observations do not have a quote book and may fall back to bar volume only
    when the complete bar starts after the order's activation time. Cumulative
    daily volume is intentionally not accepted here.
    """
    displayed = observation.ask_size if order.side == "buy" else observation.bid_size
    if displayed is not None:
        return displayed * policy.max_volume_participation_pct
    if observation.volume is None:
        return None
    if not _bar_evidence_is_causal(order, observation, policy):
        return Decimal("0")
    return observation.volume * policy.max_volume_participation_pct


def paper_protection_trigger(
    *,
    is_long: bool,
    stop_price: Decimal | None,
    target_price: Decimal | None,
    observation: PaperMarketObservation,
    activated_at: datetime | None = None,
) -> ProtectionTrigger | None:
    """Apply the same pessimistic stop-before-target trigger semantics everywhere.

    A live minute bar may contain trades that happened before an entry filled in
    that same minute. In that case only the current executable price is used; a
    whole-bar high/low is trusted only when the bar started at or after activation.
    """
    use_range = observation.high is not None and observation.low is not None
    if activated_at is not None:
        if observation.bar_start_time is None:
            use_range = False
        else:
            use_range = use_range and (
                observation.bar_start_time.astimezone(timezone.utc)
                >= activated_at.astimezone(timezone.utc)
            )
    high = observation.high if use_range and observation.high is not None else observation.price
    low = observation.low if use_range and observation.low is not None else observation.price
    if is_long:
        if stop_price is not None and low <= stop_price:
            return "stop"
        if target_price is not None and high >= target_price:
            return "target"
    else:
        if stop_price is not None and high >= stop_price:
            return "stop"
        if target_price is not None and low <= target_price:
            return "target"
    return None


def paper_fill_decision(
    order: PaperOrder,
    observation: PaperMarketObservation,
    policy: PaperExecutionPolicy | None = None,
) -> PaperFillDecision:
    active = policy or PaperExecutionPolicy()
    if order.status != "open":
        return PaperFillDecision(should_fill=False, reason="order_not_open")
    if order.instrument_id != observation.instrument_id:
        return PaperFillDecision(should_fill=False, reason="instrument_mismatch")
    if order.binding_id and order.binding_id != observation.binding_id:
        return PaperFillDecision(should_fill=False, reason="binding_mismatch")
    if active.require_execution_eligible and not observation.execution_eligible:
        return PaperFillDecision(should_fill=False, reason="execution_data_ineligible")
    if observation.age_seconds > active.max_observation_age_seconds:
        return PaperFillDecision(should_fill=False, reason="stale_market_data")
    if active.reject_halted and observation.halted:
        return PaperFillDecision(should_fill=False, reason="market_halted")
    activation = _order_activation_time(order, active)
    if activation is not None and observation.source_time.astimezone(timezone.utc) < activation:
        return PaperFillDecision(should_fill=False, reason="execution_latency_not_elapsed")

    remaining = max(Decimal("0"), order.quantity - order.filled_quantity)
    if remaining <= 0:
        return PaperFillDecision(should_fill=False, reason="order_already_filled")
    fill_quantity = remaining
    participation_capacity = _liquidity_capacity(order, observation, active)
    if participation_capacity is not None:
        if participation_capacity <= 0:
            return PaperFillDecision(should_fill=False, reason="no_causal_executable_volume")
        fill_quantity = min(remaining, participation_capacity)
        if fill_quantity <= 0:
            return PaperFillDecision(should_fill=False, reason="volume_participation_exceeded")

    if order.order_type == "market":
        base = (
            observation.ask
            if order.side == "buy" and observation.ask is not None
            else observation.bid
            if order.side == "sell" and observation.bid is not None
            else observation.price
        )
        return PaperFillDecision(
            should_fill=True,
            fill_price=_worse_price(base, order.side, active.slippage_bps),
            fill_quantity=fill_quantity,
            reason="market_execution_observation",
        )

    use_range = (
        observation.high is not None
        and observation.low is not None
        and _bar_evidence_is_causal(order, observation, active)
    )
    market_side = observation.ask if order.side == "buy" else observation.bid
    current_price = market_side if market_side is not None else observation.price
    high = observation.high if use_range and observation.high is not None else current_price
    low = observation.low if use_range and observation.low is not None else current_price
    if order.order_type == "limit":
        assert order.limit_price is not None
        triggered = low <= order.limit_price if order.side == "buy" else high >= order.limit_price
        if not triggered:
            return PaperFillDecision(should_fill=False, reason="limit_range_not_reached")
        if market_side is None:
            fill_price = order.limit_price
        elif order.side == "buy":
            fill_price = min(order.limit_price, market_side)
        else:
            fill_price = max(order.limit_price, market_side)
        return PaperFillDecision(
            should_fill=True,
            fill_price=fill_price,
            fill_quantity=fill_quantity,
            reason="limit_range_reached" if use_range else "limit_current_market_reached",
        )

    assert order.stop_price is not None
    triggered = high >= order.stop_price if order.side == "buy" else low <= order.stop_price
    if not triggered:
        return PaperFillDecision(should_fill=False, reason="stop_range_not_triggered")
    observed = current_price
    gap_through = max(order.stop_price, observed) if order.side == "buy" else min(order.stop_price, observed)
    return PaperFillDecision(
        should_fill=True,
        fill_price=_worse_price(gap_through, order.side, active.stop_slippage_bps),
        fill_quantity=fill_quantity,
        reason="stop_range_triggered_gap_aware" if use_range else "stop_current_market_triggered",
    )


def paper_commission(notional: Decimal, commission_bps: Decimal) -> Decimal:
    return notional * commission_bps / Decimal("10000")


def paper_buy_reservation(
    request: PaperOrderRequest,
    *,
    available_cash: Decimal,
    commission_bps: Decimal,
) -> Decimal:
    """Compute the cash hold for an open buy order.

    reference_price is reservation-only evidence. It never authorizes a fill.
    """
    if request.side != "buy":
        return Decimal("0")
    if request.order_type == "market":
        if request.reference_price is None:
            return available_cash
        notional = request.quantity * request.reference_price
        return notional + paper_commission(notional, commission_bps)
    reference_price = request.limit_price if request.order_type == "limit" else request.stop_price
    assert reference_price is not None
    notional = request.quantity * reference_price
    return notional + paper_commission(notional, commission_bps)


def paper_fill_is_fundable(
    order: PaperOrder,
    *,
    total_cost: Decimal,
    available_cash: Decimal,
) -> bool:
    if order.side != "buy":
        return True
    if order.order_type == "market":
        return order.reserved_cash + available_cash >= total_cost
    return order.reserved_cash >= total_cost


def paper_fill_key(
    account_id: str,
    order_id: str,
    observation: PaperMarketObservation,
) -> str:
    raw = (
        f"{account_id}|{order_id}|{observation.instrument_id}|"
        f"{observation.source_time.isoformat()}|{observation.price}|"
        f"{observation.bid}|{observation.ask}|{observation.bid_size}|{observation.ask_size}|"
        f"{observation.high}|{observation.low}|{observation.volume}|{observation.halted}"
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
