from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .indicators.engine import CORE_INDICATOR_FORMULA_VERSION, simple_moving_average
from .replay import FrozenDatasetSnapshot


class MovingAverageCrossStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_id: Literal["sma_cross"] = "sma_cross"
    fast_period: int = Field(default=10, ge=1, le=500)
    slow_period: int = Field(default=30, ge=2, le=500)

    @model_validator(mode="after")
    def validate_periods(self):
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be smaller than slow_period")
        return self


class BacktestExecutionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fill_timing: Literal["next_bar_open"] = "next_bar_open"
    commission_bps: Decimal = Field(default=Decimal("0"), ge=0, le=1_000)
    slippage_bps: Decimal = Field(default=Decimal("0"), ge=0, le=1_000)
    position_size_fraction: Decimal = Field(default=Decimal("1"), gt=0, le=1)
    allow_short: bool = False
    use_finalized_bars_only: bool = True

    @model_validator(mode="after")
    def validate_policy(self):
        if self.allow_short:
            raise ValueError("short selling is not supported in OTT-12")
        if not self.use_finalized_bars_only:
            raise ValueError("OTT-12 backtests require finalized bars")
        return self


class BacktestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: MovingAverageCrossStrategy = Field(default_factory=MovingAverageCrossStrategy)
    execution_policy: BacktestExecutionPolicy = Field(default_factory=BacktestExecutionPolicy)
    initial_cash: Decimal = Field(default=Decimal("10000"), gt=0)
    formula_version: str = CORE_INDICATOR_FORMULA_VERSION

    @model_validator(mode="after")
    def validate_formula_version(self):
        if self.formula_version != CORE_INDICATOR_FORMULA_VERSION:
            raise ValueError(f"unsupported backtest formula version: {self.formula_version}")
        return self


class BacktestTrade(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    trade_index: int = Field(ge=0)
    side: Literal["buy", "sell"]
    signal_bar_index: int = Field(ge=0)
    fill_bar_index: int = Field(ge=1)
    signal_time: datetime
    fill_time: datetime
    quantity: Decimal
    fill_price: Decimal
    commission: Decimal
    cash_after: Decimal
    position_after: Decimal

    @model_validator(mode="after")
    def validate_next_bar_fill(self):
        if self.fill_bar_index != self.signal_bar_index + 1:
            raise ValueError("backtest fills must occur on the bar after the signal")
        if self.fill_time < self.signal_time:
            raise ValueError("fill_time cannot precede signal_time")
        return self


class BacktestEquityPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    point_index: int
    bar_time: datetime
    cash: Decimal
    position: Decimal
    equity: Decimal
    drawdown_percent: Decimal


class BacktestLogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    log_index: int
    bar_time: datetime | None = None
    level: Literal["info", "warning", "error"] = "info"
    message: str
    payload: dict[str, object] = Field(default_factory=dict)


class BacktestArtifactReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    storage_provider: str
    storage_key: str
    checksum_sha256: str = Field(min_length=64, max_length=64)
    byte_size: int = Field(ge=1)


class BacktestRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    dataset_id: str
    dataset_fingerprint: str
    strategy_id: str
    strategy_parameters: dict[str, object]
    execution_policy: dict[str, object]
    formula_version: str
    status: Literal["completed", "failed"]
    initial_cash: Decimal
    final_equity: Decimal
    total_return_percent: Decimal
    max_drawdown_percent: Decimal
    win_rate_percent: Decimal = Field(ge=0, le=100)
    exposure_percent: Decimal = Field(ge=0, le=100)
    trade_count: int
    started_at: datetime
    finished_at: datetime
    trades: tuple[BacktestTrade, ...]
    equity_curve: tuple[BacktestEquityPoint, ...]
    logs: tuple[BacktestLogEntry, ...]
    artifact: BacktestArtifactReference | None = None
    error_message: str | None = None


def _aligned_sma(closes: list[Decimal], period: int) -> dict[int, Decimal]:
    values = simple_moving_average(closes, period)
    return {index + period - 1: value for index, value in enumerate(values)}


def _commission(notional: Decimal, bps: Decimal) -> Decimal:
    return notional * bps / Decimal("10000")


def _fill_price(open_price: Decimal, side: str, slippage_bps: Decimal) -> Decimal:
    adjustment = slippage_bps / Decimal("10000")
    return open_price * (
        Decimal("1") + adjustment if side == "buy" else Decimal("1") - adjustment
    )


def _round_trip_win_rate(trades: list[BacktestTrade]) -> Decimal:
    entry_cost: Decimal | None = None
    closed_results: list[Decimal] = []
    for trade in trades:
        notional = trade.quantity * trade.fill_price
        if trade.side == "buy":
            entry_cost = notional + trade.commission
        elif entry_cost is not None:
            closed_results.append(notional - trade.commission - entry_cost)
            entry_cost = None
    if not closed_results:
        return Decimal("0")
    wins = sum(1 for value in closed_results if value > 0)
    return Decimal(wins) / Decimal(len(closed_results)) * Decimal("100")


def _exposure_percent(equity_curve: list[BacktestEquityPoint]) -> Decimal:
    if not equity_curve:
        return Decimal("0")
    exposed = sum(1 for point in equity_curve if point.position > 0)
    return Decimal(exposed) / Decimal(len(equity_curve)) * Decimal("100")


def run_backtest(
    snapshot: FrozenDatasetSnapshot,
    request: BacktestRequest,
    *,
    run_id: str | None = None,
    now: datetime | None = None,
) -> BacktestRunResult:
    started_at = now or datetime.now(timezone.utc)
    identifier = run_id or f"backtest-{uuid4().hex}"
    bars = list(snapshot.bars)
    minimum = request.strategy.slow_period + 1
    if len(bars) < minimum:
        finished_at = datetime.now(timezone.utc)
        return BacktestRunResult(
            run_id=identifier,
            dataset_id=snapshot.dataset_id,
            dataset_fingerprint=snapshot.dataset_fingerprint,
            strategy_id=request.strategy.strategy_id,
            strategy_parameters=request.strategy.model_dump(mode="json"),
            execution_policy=request.execution_policy.model_dump(mode="json"),
            formula_version=request.formula_version,
            status="failed",
            initial_cash=request.initial_cash,
            final_equity=request.initial_cash,
            total_return_percent=Decimal("0"),
            max_drawdown_percent=Decimal("0"),
            win_rate_percent=Decimal("0"),
            exposure_percent=Decimal("0"),
            trade_count=0,
            started_at=started_at,
            finished_at=finished_at,
            trades=(),
            equity_curve=(),
            logs=(
                BacktestLogEntry(
                    log_index=0,
                    level="error",
                    message="insufficient dataset history",
                ),
            ),
            error_message=f"dataset requires at least {minimum} bars",
        )

    closes = [bar.close for bar in bars]
    fast = _aligned_sma(closes, request.strategy.fast_period)
    slow = _aligned_sma(closes, request.strategy.slow_period)
    cash = request.initial_cash
    position = Decimal("0")
    pending: tuple[str, int, datetime] | None = None
    trades: list[BacktestTrade] = []
    equity_curve: list[BacktestEquityPoint] = []
    logs: list[BacktestLogEntry] = []
    peak = request.initial_cash
    max_drawdown = Decimal("0")

    for index, bar in enumerate(bars):
        if pending is not None:
            side, signal_bar_index, signal_time = pending
            open_price = _fill_price(
                bar.open,
                side,
                request.execution_policy.slippage_bps,
            )
            if side == "buy" and position == 0:
                budget = cash * request.execution_policy.position_size_fraction
                commission_rate = (
                    request.execution_policy.commission_bps / Decimal("10000")
                )
                quantity = budget / (
                    open_price * (Decimal("1") + commission_rate)
                )
                notional = quantity * open_price
                commission = _commission(
                    notional,
                    request.execution_policy.commission_bps,
                )
                cash -= notional + commission
                position += quantity
            elif side == "sell" and position > 0:
                quantity = position
                notional = quantity * open_price
                commission = _commission(
                    notional,
                    request.execution_policy.commission_bps,
                )
                cash += notional - commission
                position = Decimal("0")
            else:
                quantity = Decimal("0")
                commission = Decimal("0")
            if quantity > 0:
                trades.append(
                    BacktestTrade(
                        trade_index=len(trades),
                        side=side,
                        signal_bar_index=signal_bar_index,
                        fill_bar_index=index,
                        signal_time=signal_time,
                        fill_time=bar.start_time,
                        quantity=quantity,
                        fill_price=open_price,
                        commission=commission,
                        cash_after=cash,
                        position_after=position,
                    )
                )
                logs.append(
                    BacktestLogEntry(
                        log_index=len(logs),
                        bar_time=bar.start_time,
                        message=f"filled {side} at next bar open",
                        payload={
                            "signal_bar_index": signal_bar_index,
                            "fill_bar_index": index,
                            "signal_time": signal_time.isoformat(),
                            "fill_price": str(open_price),
                        },
                    )
                )
            pending = None

        equity = cash + position * bar.close
        peak = max(peak, equity)
        drawdown = (
            Decimal("0")
            if peak == 0
            else (peak - equity) / peak * Decimal("100")
        )
        max_drawdown = max(max_drawdown, drawdown)
        equity_curve.append(
            BacktestEquityPoint(
                point_index=index,
                bar_time=bar.end_time,
                cash=cash,
                position=position,
                equity=equity,
                drawdown_percent=drawdown,
            )
        )

        if index == 0 or index not in fast or index not in slow:
            continue
        previous_index = index - 1
        if previous_index not in fast or previous_index not in slow:
            continue
        crossed_above = (
            fast[previous_index] <= slow[previous_index]
            and fast[index] > slow[index]
        )
        crossed_below = (
            fast[previous_index] >= slow[previous_index]
            and fast[index] < slow[index]
        )
        if crossed_above and position == 0:
            pending = ("buy", index, bar.end_time)
        elif crossed_below and position > 0:
            pending = ("sell", index, bar.end_time)

    final_equity = equity_curve[-1].equity
    total_return = (
        final_equity / request.initial_cash - Decimal("1")
    ) * Decimal("100")
    win_rate = _round_trip_win_rate(trades)
    exposure = _exposure_percent(equity_curve)
    finished_at = datetime.now(timezone.utc)
    logs.append(
        BacktestLogEntry(
            log_index=len(logs),
            bar_time=bars[-1].end_time,
            message="backtest completed",
            payload={
                "dataset_fingerprint": snapshot.dataset_fingerprint,
                "trade_count": len(trades),
                "final_equity": str(final_equity),
                "win_rate_percent": str(win_rate),
                "exposure_percent": str(exposure),
            },
        )
    )
    return BacktestRunResult(
        run_id=identifier,
        dataset_id=snapshot.dataset_id,
        dataset_fingerprint=snapshot.dataset_fingerprint,
        strategy_id=request.strategy.strategy_id,
        strategy_parameters=request.strategy.model_dump(mode="json"),
        execution_policy=request.execution_policy.model_dump(mode="json"),
        formula_version=request.formula_version,
        status="completed",
        initial_cash=request.initial_cash,
        final_equity=final_equity,
        total_return_percent=total_return,
        max_drawdown_percent=max_drawdown,
        win_rate_percent=win_rate,
        exposure_percent=exposure,
        trade_count=len(trades),
        started_at=started_at,
        finished_at=finished_at,
        trades=tuple(trades),
        equity_curve=tuple(equity_curve),
        logs=tuple(logs),
    )
