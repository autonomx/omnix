from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .execution import ExecutionObservation
from .paper import PaperAccountSnapshot, PaperOrderRequest
from .paper_protection import PaperPositionProtection, PaperProtectionUpsert
from .strategy_risk import paper_account_equity, paper_daily_realized_pnl


class PaperRiskPolicy(BaseModel):
    """Server-owned limits for manual paper-entry sizing.

    The defaults intentionally match the conservative strategy risk envelope so
    the browser cannot create a second, weaker sizing policy for manual orders.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal["paper-risk-v1"] = "paper-risk-v1"
    max_risk_per_trade_pct: Decimal = Field(default=Decimal("1.0"), gt=0, le=5)
    max_open_risk_pct: Decimal = Field(default=Decimal("1.0"), gt=0, le=20)
    max_daily_loss_pct: Decimal = Field(default=Decimal("1.5"), gt=0, le=20)
    max_spread_bps: Decimal = Field(default=Decimal("150"), gt=0, le=10_000)
    require_execution_eligible: bool = True
    block_unprotected_exposure: bool = True


class PaperRiskPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument_id: str = Field(min_length=3, max_length=200)
    binding_id: str | None = Field(default=None, max_length=240)
    entry_price: Decimal = Field(gt=0)
    stop_price: Decimal = Field(gt=0)
    desired_risk_pct: Decimal = Field(default=Decimal("0.35"), gt=0, le=20)


class PaperRiskPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    policy_version: str
    reason_codes: tuple[str, ...]
    limiting_reason_code: str | None = None
    recommended_quantity: Decimal = Decimal("0")
    account_equity: Decimal = Decimal("0")
    desired_risk_pct: Decimal
    actual_risk_dollars: Decimal = Decimal("0")
    actual_risk_pct: Decimal = Decimal("0")
    estimated_notional: Decimal = Decimal("0")
    buying_power_before: Decimal = Decimal("0")
    buying_power_after: Decimal = Decimal("0")
    aggregate_open_risk_dollars: Decimal = Decimal("0")
    aggregate_open_risk_pct: Decimal = Decimal("0")
    daily_realized_pnl: Decimal = Decimal("0")
    daily_loss_remaining: Decimal = Decimal("0")
    spread_bps: Decimal | None = None
    observation_age_seconds: Decimal | None = None
    freshness_mode: str = "unknown"
    execution_eligible: bool = False
    unprotected_exposure_count: int = 0


class PaperRiskOrderRequest(BaseModel):
    """Risk intent for a new long paper entry; quantity is deliberately absent."""

    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(min_length=1, max_length=200)
    instrument_id: str = Field(min_length=3, max_length=200)
    binding_id: str | None = Field(default=None, max_length=240)
    order_type: Literal["market", "limit", "stop"] = "market"
    trigger_price: Decimal | None = Field(default=None, gt=0)
    stop_loss: Decimal = Field(gt=0)
    take_profit: Decimal | None = Field(default=None, gt=0)
    desired_risk_pct: Decimal = Field(default=Decimal("0.35"), gt=0, le=20)
    idempotency_key: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_trigger(self):
        if self.order_type == "market" and self.trigger_price is not None:
            raise ValueError("market risk orders cannot include trigger_price")
        if self.order_type != "market" and self.trigger_price is None:
            raise ValueError("limit/stop risk orders require trigger_price")
        return self


def _entry_price(order) -> Decimal | None:
    return order.limit_price or order.stop_price or order.reference_price or order.average_fill_price


def paper_account_open_risk(
    snapshot: PaperAccountSnapshot,
    protections: list[PaperPositionProtection],
) -> tuple[Decimal, int]:
    """Return known downside risk plus count of exposure that cannot be bounded.

    Long positions and pending long entries are included. A stop at/above cost
    contributes zero downside risk. Exposure with no server-side stop is not
    silently treated as zero; it is counted as unprotected so policy can fail
    closed instead of understating account risk.
    """

    by_instrument = {
        item.instrument_id: item
        for item in protections
        if item.status in {"pending_entry", "active", "exit_submitted"}
    }
    total = Decimal("0")
    unprotected = 0

    for position in snapshot.positions:
        if position.quantity <= 0:
            continue
        protection = by_instrument.get(position.instrument_id)
        if protection is None or protection.stop_loss is None:
            unprotected += 1
            continue
        total += max(Decimal("0"), position.average_cost - protection.stop_loss) * position.quantity

    for order in snapshot.open_orders:
        if order.side != "buy":
            continue
        remaining = max(Decimal("0"), order.quantity - order.filled_quantity)
        if remaining <= 0:
            continue
        protection = by_instrument.get(order.instrument_id)
        entry = _entry_price(order)
        if protection is None or protection.stop_loss is None or entry is None:
            unprotected += 1
            continue
        total += max(Decimal("0"), entry - protection.stop_loss) * remaining

    return total, unprotected


def _normalize_quantity(instrument_id: str, quantity: Decimal) -> Decimal:
    if quantity <= 0:
        return Decimal("0")
    if instrument_id.startswith("equity:"):
        return quantity.to_integral_value(rounding=ROUND_DOWN)
    return quantity.quantize(Decimal("0.000001"), rounding=ROUND_DOWN)


def preview_paper_risk(
    *,
    snapshot: PaperAccountSnapshot,
    protections: list[PaperPositionProtection],
    observation: ExecutionObservation,
    request: PaperRiskPreviewRequest,
    policy: PaperRiskPolicy | None = None,
) -> PaperRiskPreview:
    active = policy or PaperRiskPolicy()
    equity = paper_account_equity(snapshot)
    daily_realized = paper_daily_realized_pnl(snapshot)
    open_risk, unprotected = paper_account_open_risk(snapshot, protections)
    balance = next(
        (item for item in snapshot.balances if item.currency == snapshot.account.base_currency),
        None,
    )
    buying_power = balance.available if balance is not None else Decimal("0")
    spread = observation.spread_bps
    reasons: list[str] = []
    existing_target_exposure = any(
        item.instrument_id == request.instrument_id and item.quantity != 0
        for item in snapshot.positions
    ) or any(
        item.instrument_id == request.instrument_id
        and item.side == "buy"
        and item.status == "open"
        and item.quantity > item.filled_quantity
        for item in snapshot.open_orders
    )

    if existing_target_exposure:
        reasons.append("EXISTING_INSTRUMENT_EXPOSURE")
    if request.stop_price >= request.entry_price:
        reasons.append("STOP_NOT_BELOW_ENTRY")
    if request.desired_risk_pct > active.max_risk_per_trade_pct:
        reasons.append("RISK_PERCENT_EXCEEDS_POLICY")
    if equity <= 0:
        reasons.append("NON_POSITIVE_EQUITY")
    if active.require_execution_eligible and not observation.execution_eligible:
        reasons.append("EXECUTION_DATA_INELIGIBLE")
    if spread is None:
        reasons.append("SPREAD_UNAVAILABLE")
    elif spread > active.max_spread_bps:
        reasons.append("SPREAD_TOO_WIDE")
    if active.block_unprotected_exposure and unprotected > 0:
        reasons.append("UNPROTECTED_OPEN_EXPOSURE")

    daily_loss_limit = equity * active.max_daily_loss_pct / Decimal("100") if equity > 0 else Decimal("0")
    daily_loss_remaining = max(Decimal("0"), daily_loss_limit + daily_realized)
    if daily_realized <= -daily_loss_limit and daily_loss_limit > 0:
        reasons.append("DAILY_LOSS_LIMIT")

    open_risk_limit = equity * active.max_open_risk_pct / Decimal("100") if equity > 0 else Decimal("0")
    open_risk_remaining = max(Decimal("0"), open_risk_limit - open_risk)
    if open_risk_remaining <= 0 and open_risk_limit > 0:
        reasons.append("OPEN_RISK_LIMIT")

    risk_per_share = request.entry_price - request.stop_price
    requested_risk = equity * request.desired_risk_pct / Decimal("100") if equity > 0 else Decimal("0")
    risk_budget = min(requested_risk, open_risk_remaining, daily_loss_remaining)
    commission_factor = Decimal("1") + snapshot.account.commission_bps / Decimal("10000")
    quantity_by_risk = risk_budget / risk_per_share if risk_per_share > 0 else Decimal("0")
    quantity_by_buying_power = (
        buying_power / (request.entry_price * commission_factor)
        if request.entry_price > 0 and commission_factor > 0
        else Decimal("0")
    )
    raw_quantity = min(quantity_by_risk, quantity_by_buying_power)
    quantity = _normalize_quantity(request.instrument_id, raw_quantity)

    limiting = None
    if raw_quantity > 0:
        limiting = "BUYING_POWER" if quantity_by_buying_power <= quantity_by_risk else "RISK_BUDGET"
        if risk_budget == open_risk_remaining and open_risk_remaining < requested_risk:
            limiting = "OPEN_RISK"
        elif risk_budget == daily_loss_remaining and daily_loss_remaining < requested_risk:
            limiting = "DAILY_LOSS_REMAINING"
    if quantity <= 0:
        reasons.append("NO_SIZABLE_QUANTITY")

    actual_risk = quantity * max(Decimal("0"), risk_per_share)
    actual_risk_pct = actual_risk / equity * Decimal("100") if equity > 0 else Decimal("0")
    estimated_notional = quantity * request.entry_price
    after = max(Decimal("0"), buying_power - estimated_notional * commission_factor)
    aggregate_pct = open_risk / equity * Decimal("100") if equity > 0 else Decimal("0")

    return PaperRiskPreview(
        allowed=not reasons,
        policy_version=active.policy_version,
        reason_codes=tuple(dict.fromkeys(reasons)),
        limiting_reason_code=limiting,
        recommended_quantity=quantity if not reasons else Decimal("0"),
        account_equity=equity,
        desired_risk_pct=request.desired_risk_pct,
        actual_risk_dollars=actual_risk if not reasons else Decimal("0"),
        actual_risk_pct=actual_risk_pct if not reasons else Decimal("0"),
        estimated_notional=estimated_notional if not reasons else Decimal("0"),
        buying_power_before=buying_power,
        buying_power_after=after if not reasons else buying_power,
        aggregate_open_risk_dollars=open_risk,
        aggregate_open_risk_pct=aggregate_pct,
        daily_realized_pnl=daily_realized,
        daily_loss_remaining=daily_loss_remaining,
        spread_bps=spread,
        observation_age_seconds=observation.age_seconds,
        freshness_mode=observation.freshness_mode,
        execution_eligible=observation.execution_eligible,
        unprotected_exposure_count=unprotected,
    )


def risk_order_request(
    intent: PaperRiskOrderRequest,
    *,
    entry_price: Decimal,
    quantity: Decimal,
) -> PaperOrderRequest:
    return PaperOrderRequest(
        order_id=intent.order_id,
        instrument_id=intent.instrument_id,
        binding_id=intent.binding_id,
        side="buy",
        order_type=intent.order_type,
        quantity=quantity,
        limit_price=intent.trigger_price if intent.order_type == "limit" else None,
        stop_price=intent.trigger_price if intent.order_type == "stop" else None,
        reference_price=entry_price if intent.order_type == "market" else None,
        idempotency_key=intent.idempotency_key,
    )


def risk_protection_request(intent: PaperRiskOrderRequest) -> PaperProtectionUpsert:
    return PaperProtectionUpsert(
        instrument_id=intent.instrument_id,
        binding_id=intent.binding_id,
        entry_order_id=intent.order_id,
        take_profit=intent.take_profit,
        stop_loss=intent.stop_loss,
    )
