from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .gapper_dataset import GapperUniverseSnapshot
from .models import MarketBar
from .paper import (
    PaperExecutionPolicy,
    PaperMarketObservation,
    PaperOrder,
    paper_fill_decision,
)
from .strategies.gap_pullback import evaluate_gap_pullback
from .strategies.models import GapPullbackConfig


_ET = ZoneInfo("America/New_York")


class BacktestSessionDataset(BaseModel):
    """Frozen multi-symbol morning dataset paired to one point-in-time universe."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_date: date
    universe: GapperUniverseSnapshot
    bars_by_instrument: dict[str, tuple[MarketBar, ...]]
    dataset_fingerprint: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def candidate_coverage(self):
        if self.session_date != self.universe.session_date:
            raise ValueError("backtest session_date must match frozen universe session_date")
        missing = [
            candidate.instrument_id
            for candidate in self.universe.candidates
            if candidate.instrument_id not in self.bars_by_instrument
        ]
        if missing:
            raise ValueError(f"missing candidate bars: {','.join(missing)}")
        for instrument_id, bars in self.bars_by_instrument.items():
            if any(bar.instrument_id != instrument_id for bar in bars):
                raise ValueError(f"backtest bars do not match map instrument: {instrument_id}")
            if any(not bar.is_final for bar in bars):
                raise ValueError(f"backtest requires finalized bars: {instrument_id}")
            if any(bar.interval != "1m" for bar in bars):
                raise ValueError(f"gap_pullback_v1 backtest requires 1m bars: {instrument_id}")
            if any(bar.start_time.astimezone(_ET).date() != self.session_date for bar in bars):
                raise ValueError(f"backtest bars cross session_date: {instrument_id}")
        return self


class GapPullbackBacktestTrade(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
    entry_fill_quantity: Decimal
    entry_slippage_bps: Decimal
    exit_slippage_bps: Decimal
    stop_price: Decimal
    target_price: Decimal
    exit_reason: Literal["stop", "target", "time", "eod"]
    pnl_per_share: Decimal
    r_multiple: Decimal
    mfe_r: Decimal
    mae_r: Decimal
    hold_minutes: Decimal
    trigger_bar_index: int
    entry_bar_index: int


class GapPullbackBacktestSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_count: int
    trigger_count: int
    trade_count: int
    no_next_bar_count: int
    entry_execution_rejection_count: int
    exit_execution_rejection_count: int
    invalid_risk_count: int
    portfolio_capacity_rejection_count: int
    partial_entry_count: int
    win_count: int
    loss_count: int
    win_rate: Decimal
    expectancy_r: Decimal
    profit_factor: Decimal | None
    average_mfe_r: Decimal
    average_mae_r: Decimal
    candidate_to_trigger_rate: Decimal
    trigger_to_trade_rate: Decimal
    candidate_to_trade_rate: Decimal
    average_hold_minutes: Decimal
    average_entry_slippage_bps: Decimal
    average_exit_slippage_bps: Decimal
    trades_per_day: Decimal
    stop_count: int
    target_count: int
    time_exit_count: int


class GapPullbackBacktestResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_id: str = "gap_pullback_v1"
    strategy_version: str = "1.0.0"
    dataset_fingerprint: str
    execution_policy_version: str
    trades: tuple[GapPullbackBacktestTrade, ...]
    summary: GapPullbackBacktestSummary


@dataclass(frozen=True)
class _TradeAttempt:
    trigger_bar_index: int | None = None
    trade: GapPullbackBacktestTrade | None = None
    rejection_reason: str | None = None

    @property
    def triggered(self) -> bool:
        return self.trigger_bar_index is not None


def freeze_backtest_session(
    *,
    session_date: date,
    universe: GapperUniverseSnapshot,
    bars_by_instrument: dict[str, list[MarketBar] | tuple[MarketBar, ...]],
) -> BacktestSessionDataset:
    if session_date != universe.session_date:
        raise ValueError("backtest session_date must match frozen universe session_date")
    normalized = {
        instrument_id: tuple(sorted(bars, key=lambda bar: bar.start_time))
        for instrument_id, bars in sorted(bars_by_instrument.items())
    }
    payload = {
        "session_date": session_date.isoformat(),
        "universe_fingerprint": universe.source_fingerprint,
        "bars": {
            instrument_id: [
                {
                    "start": bar.start_time.astimezone(timezone.utc).isoformat(),
                    "end": bar.end_time.astimezone(timezone.utc).isoformat(),
                    "o": str(bar.open),
                    "h": str(bar.high),
                    "l": str(bar.low),
                    "c": str(bar.close),
                    "v": str(bar.volume),
                    "provider": bar.provider,
                    "final": bar.is_final,
                    "session": bar.session,
                    "adjustment_mode": str(bar.adjustment_mode),
                }
                for bar in bars
            ]
            for instrument_id, bars in normalized.items()
        },
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return BacktestSessionDataset(
        session_date=session_date,
        universe=universe,
        bars_by_instrument=normalized,
        dataset_fingerprint=fingerprint,
    )


def _bar_observation(
    bar: MarketBar,
    *,
    instrument_id: str,
    binding_id: str | None,
    spread_bps: Decimal,
    price: Decimal,
) -> PaperMarketObservation:
    half = spread_bps / Decimal("20000")
    return PaperMarketObservation(
        instrument_id=instrument_id,
        binding_id=binding_id,
        provider=f"backtest:{bar.provider}",
        price=price,
        bid=price * (Decimal("1") - half),
        ask=price * (Decimal("1") + half),
        high=bar.high,
        low=bar.low,
        volume=bar.volume,
        source_time=bar.start_time,
        evaluated_at=bar.start_time,
        execution_eligible=True,
        freshness_mode="historical",
    )


def _adverse_buy_slippage_bps(fill: Decimal, reference: Decimal) -> Decimal:
    if reference <= 0:
        return Decimal("0")
    return (fill - reference) / reference * Decimal("10000")


def _adverse_sell_slippage_bps(fill: Decimal, reference: Decimal) -> Decimal:
    if reference <= 0:
        return Decimal("0")
    return (reference - fill) / reference * Decimal("10000")


def _exit_market_decision(
    *,
    candidate,
    bar: MarketBar,
    quantity: Decimal,
    policy: PaperExecutionPolicy,
    assumed_spread_bps: Decimal,
    price: Decimal,
    order_suffix: str,
):
    order = PaperOrder(
        account_id="backtest",
        order_id=f"{order_suffix}:{candidate.instrument_id}:{bar.start_time.isoformat()}",
        instrument_id=candidate.instrument_id,
        binding_id=candidate.binding_id,
        side="sell",
        order_type="market",
        quantity=quantity,
        idempotency_key=f"{order_suffix}:{candidate.instrument_id}:{bar.start_time.isoformat()}",
    )
    return paper_fill_decision(
        order,
        _bar_observation(
            bar,
            instrument_id=candidate.instrument_id,
            binding_id=candidate.binding_id,
            spread_bps=assumed_spread_bps,
            price=price,
        ),
        policy,
    )


def _find_trade(
    candidate,
    bars: tuple[MarketBar, ...],
    config: GapPullbackConfig,
    policy: PaperExecutionPolicy,
    *,
    assumed_spread_bps: Decimal,
    max_hold_minutes: int,
) -> _TradeAttempt:
    trigger_index: int | None = None
    signal = None
    for index in range(1, len(bars) + 1):
        result = evaluate_gap_pullback(candidate, bars[:index], config)
        if result.state == "entry_ready" and result.signal is not None:
            trigger_index = index - 1
            signal = result.signal
            break
    if trigger_index is None or signal is None:
        return _TradeAttempt()
    if trigger_index + 1 >= len(bars):
        return _TradeAttempt(
            trigger_bar_index=trigger_index,
            rejection_reason="no_next_bar",
        )

    entry_index = trigger_index + 1
    entry_bar = bars[entry_index]
    entry_order = PaperOrder(
        account_id="backtest",
        order_id=f"entry:{candidate.instrument_id}:{entry_index}",
        instrument_id=candidate.instrument_id,
        binding_id=candidate.binding_id,
        side="buy",
        order_type="market",
        quantity=Decimal("1"),
        idempotency_key=f"entry:{candidate.instrument_id}:{entry_index}",
    )
    entry_decision = paper_fill_decision(
        entry_order,
        _bar_observation(
            entry_bar,
            instrument_id=candidate.instrument_id,
            binding_id=candidate.binding_id,
            spread_bps=assumed_spread_bps,
            price=entry_bar.open,
        ),
        policy,
    )
    if (
        not entry_decision.should_fill
        or entry_decision.fill_price is None
        or entry_decision.fill_quantity is None
        or entry_decision.fill_quantity <= 0
    ):
        return _TradeAttempt(
            trigger_bar_index=trigger_index,
            rejection_reason=f"entry_execution:{entry_decision.reason}",
        )
    entry = entry_decision.fill_price
    entry_quantity = min(Decimal("1"), entry_decision.fill_quantity)
    entry_slippage_bps = _adverse_buy_slippage_bps(entry, entry_bar.open)
    stop = signal.stop_price
    risk = entry - stop
    if risk <= 0:
        return _TradeAttempt(
            trigger_bar_index=trigger_index,
            rejection_reason="invalid_risk_distance",
        )
    target = entry + risk * config.reward_multiple
    horizon = entry_bar.start_time + timedelta(minutes=max_hold_minutes)
    max_high = entry
    min_low = entry

    exit_price: Decimal | None = None
    exit_time: datetime | None = None
    exit_reference: Decimal | None = None
    exit_reason: Literal["stop", "target", "time", "eod"] | None = None
    last_exit_rejection: str | None = None

    for index in range(entry_index, len(bars)):
        bar = bars[index]
        max_high = max(max_high, bar.high)
        min_low = min(min_low, bar.low)
        stop_hit = bar.low <= stop
        target_hit = bar.high >= target
        if stop_hit:
            # Same-bar ambiguity is pessimistic: stop is evaluated before target.
            stop_order = PaperOrder(
                account_id="backtest",
                order_id=f"stop:{candidate.instrument_id}:{index}",
                instrument_id=candidate.instrument_id,
                binding_id=candidate.binding_id,
                side="sell",
                order_type="stop",
                quantity=entry_quantity,
                stop_price=stop,
                idempotency_key=f"stop:{candidate.instrument_id}:{index}",
            )
            decision = paper_fill_decision(
                stop_order,
                _bar_observation(
                    bar,
                    instrument_id=candidate.instrument_id,
                    binding_id=candidate.binding_id,
                    spread_bps=assumed_spread_bps,
                    price=bar.open,
                ),
                policy,
            )
            if (
                decision.should_fill
                and decision.fill_price is not None
                and decision.fill_quantity is not None
                and decision.fill_quantity >= entry_quantity
            ):
                exit_price = decision.fill_price
                exit_time = bar.end_time
                exit_reference = stop
                exit_reason = "stop"
                break
            last_exit_rejection = f"exit_execution:{decision.reason}"
        if target_hit:
            target_order = PaperOrder(
                account_id="backtest",
                order_id=f"target:{candidate.instrument_id}:{index}",
                instrument_id=candidate.instrument_id,
                binding_id=candidate.binding_id,
                side="sell",
                order_type="limit",
                quantity=entry_quantity,
                limit_price=target,
                idempotency_key=f"target:{candidate.instrument_id}:{index}",
            )
            decision = paper_fill_decision(
                target_order,
                _bar_observation(
                    bar,
                    instrument_id=candidate.instrument_id,
                    binding_id=candidate.binding_id,
                    spread_bps=assumed_spread_bps,
                    price=target,
                ),
                policy,
            )
            if (
                decision.should_fill
                and decision.fill_price is not None
                and decision.fill_quantity is not None
                and decision.fill_quantity >= entry_quantity
            ):
                exit_price = decision.fill_price
                exit_time = bar.end_time
                exit_reference = target
                exit_reason = "target"
                break
            last_exit_rejection = f"exit_execution:{decision.reason}"
        if bar.end_time >= horizon:
            decision = _exit_market_decision(
                candidate=candidate,
                bar=bar,
                quantity=entry_quantity,
                policy=policy,
                assumed_spread_bps=assumed_spread_bps,
                price=bar.close,
                order_suffix="time",
            )
            if (
                decision.should_fill
                and decision.fill_price is not None
                and decision.fill_quantity is not None
                and decision.fill_quantity >= entry_quantity
            ):
                exit_price = decision.fill_price
                exit_time = bar.end_time
                exit_reference = bar.close
                exit_reason = "time"
                break
            last_exit_rejection = f"exit_execution:{decision.reason}"

    if exit_price is None:
        last_bar = bars[-1]
        decision = _exit_market_decision(
            candidate=candidate,
            bar=last_bar,
            quantity=entry_quantity,
            policy=policy,
            assumed_spread_bps=assumed_spread_bps,
            price=last_bar.close,
            order_suffix="eod",
        )
        if (
            decision.should_fill
            and decision.fill_price is not None
            and decision.fill_quantity is not None
            and decision.fill_quantity >= entry_quantity
        ):
            exit_price = decision.fill_price
            exit_time = last_bar.end_time
            exit_reference = last_bar.close
            exit_reason = "eod"
        else:
            last_exit_rejection = f"exit_execution:{decision.reason}"

    if exit_price is None or exit_time is None or exit_reference is None or exit_reason is None:
        return _TradeAttempt(
            trigger_bar_index=trigger_index,
            rejection_reason=last_exit_rejection or "exit_execution:unfilled",
        )

    pnl = exit_price - entry
    r_multiple = pnl / risk
    mfe_r = (max_high - entry) / risk
    mae_r = (min_low - entry) / risk
    hold_minutes = Decimal(str((exit_time - entry_bar.start_time).total_seconds() / 60))
    trade = GapPullbackBacktestTrade(
        instrument_id=candidate.instrument_id,
        entry_time=entry_bar.start_time,
        exit_time=exit_time,
        entry_price=entry,
        exit_price=exit_price,
        entry_fill_quantity=entry_quantity,
        entry_slippage_bps=entry_slippage_bps,
        exit_slippage_bps=_adverse_sell_slippage_bps(exit_price, exit_reference),
        stop_price=stop,
        target_price=target,
        exit_reason=exit_reason,
        pnl_per_share=pnl,
        r_multiple=r_multiple,
        mfe_r=mfe_r,
        mae_r=mae_r,
        hold_minutes=hold_minutes,
        trigger_bar_index=trigger_index,
        entry_bar_index=entry_index,
    )
    return _TradeAttempt(trigger_bar_index=trigger_index, trade=trade)


def run_gap_pullback_backtest(
    dataset: BacktestSessionDataset,
    config: GapPullbackConfig | None = None,
    execution_policy: PaperExecutionPolicy | None = None,
    *,
    assumed_spread_bps: Decimal = Decimal("40"),
    max_hold_minutes: int = 90,
    max_concurrent_positions: int = 3,
) -> GapPullbackBacktestResult:
    if assumed_spread_bps < 0:
        raise ValueError("assumed_spread_bps cannot be negative")
    if max_hold_minutes < 1:
        raise ValueError("max_hold_minutes must be positive")
    if max_concurrent_positions < 1:
        raise ValueError("max_concurrent_positions must be positive")
    active = config or GapPullbackConfig()
    policy = execution_policy or PaperExecutionPolicy(
        max_volume_participation_pct=Decimal("1")
    )

    attempts: list[_TradeAttempt] = []
    proposed: list[GapPullbackBacktestTrade] = []
    for candidate in dataset.universe.candidates:
        attempt = _find_trade(
            candidate,
            dataset.bars_by_instrument[candidate.instrument_id],
            active,
            policy,
            assumed_spread_bps=assumed_spread_bps,
            max_hold_minutes=max_hold_minutes,
        )
        attempts.append(attempt)
        if attempt.trade is not None:
            proposed.append(attempt.trade)
    proposed.sort(key=lambda trade: (trade.entry_time, trade.instrument_id))

    selected: list[GapPullbackBacktestTrade] = []
    capacity_rejections = 0
    for trade in proposed:
        concurrent = sum(
            1 for existing in selected if existing.entry_time <= trade.entry_time < existing.exit_time
        )
        if concurrent < max_concurrent_positions:
            selected.append(trade)
        else:
            capacity_rejections += 1

    trigger_count = sum(1 for attempt in attempts if attempt.triggered)
    no_next_bar_count = sum(
        1 for attempt in attempts if attempt.rejection_reason == "no_next_bar"
    )
    entry_execution_rejections = sum(
        1
        for attempt in attempts
        if (attempt.rejection_reason or "").startswith("entry_execution:")
    )
    exit_execution_rejections = sum(
        1
        for attempt in attempts
        if (attempt.rejection_reason or "").startswith("exit_execution:")
    )
    invalid_risk_count = sum(
        1 for attempt in attempts if attempt.rejection_reason == "invalid_risk_distance"
    )

    count = len(selected)
    wins = sum(1 for trade in selected if trade.r_multiple > 0)
    losses = sum(1 for trade in selected if trade.r_multiple < 0)
    positive = sum(
        (trade.r_multiple for trade in selected if trade.r_multiple > 0), Decimal("0")
    )
    negative = abs(
        sum((trade.r_multiple for trade in selected if trade.r_multiple < 0), Decimal("0"))
    )
    divisor = Decimal(count) if count else Decimal("1")
    candidate_count = len(dataset.universe.candidates)
    summary = GapPullbackBacktestSummary(
        candidate_count=candidate_count,
        trigger_count=trigger_count,
        trade_count=count,
        no_next_bar_count=no_next_bar_count,
        entry_execution_rejection_count=entry_execution_rejections,
        exit_execution_rejection_count=exit_execution_rejections,
        invalid_risk_count=invalid_risk_count,
        portfolio_capacity_rejection_count=capacity_rejections,
        partial_entry_count=sum(
            1 for trade in selected if trade.entry_fill_quantity < Decimal("1")
        ),
        win_count=wins,
        loss_count=losses,
        win_rate=Decimal(wins) / divisor,
        expectancy_r=sum((trade.r_multiple for trade in selected), Decimal("0")) / divisor,
        profit_factor=positive / negative if negative > 0 else None,
        average_mfe_r=sum((trade.mfe_r for trade in selected), Decimal("0")) / divisor,
        average_mae_r=sum((trade.mae_r for trade in selected), Decimal("0")) / divisor,
        candidate_to_trigger_rate=(
            Decimal(trigger_count) / Decimal(candidate_count)
            if candidate_count
            else Decimal("0")
        ),
        trigger_to_trade_rate=(
            Decimal(count) / Decimal(trigger_count) if trigger_count else Decimal("0")
        ),
        candidate_to_trade_rate=(
            Decimal(count) / Decimal(candidate_count) if candidate_count else Decimal("0")
        ),
        average_hold_minutes=sum((trade.hold_minutes for trade in selected), Decimal("0")) / divisor,
        average_entry_slippage_bps=sum(
            (trade.entry_slippage_bps for trade in selected), Decimal("0")
        ) / divisor,
        average_exit_slippage_bps=sum(
            (trade.exit_slippage_bps for trade in selected), Decimal("0")
        ) / divisor,
        trades_per_day=Decimal(count),
        stop_count=sum(1 for trade in selected if trade.exit_reason == "stop"),
        target_count=sum(1 for trade in selected if trade.exit_reason == "target"),
        time_exit_count=sum(
            1 for trade in selected if trade.exit_reason in {"time", "eod"}
        ),
    )
    return GapPullbackBacktestResult(
        dataset_fingerprint=dataset.dataset_fingerprint,
        execution_policy_version=policy.policy_version,
        trades=tuple(selected),
        summary=summary,
    )


def walk_forward_splits(
    sessions: list[BacktestSessionDataset] | tuple[BacktestSessionDataset, ...],
    *,
    train_sessions: int,
    test_sessions: int,
) -> list[tuple[tuple[BacktestSessionDataset, ...], tuple[BacktestSessionDataset, ...]]]:
    ordered = tuple(sorted(sessions, key=lambda item: item.session_date))
    if train_sessions < 1 or test_sessions < 1:
        raise ValueError("walk-forward windows must be positive")
    output = []
    start = 0
    while start + train_sessions + test_sessions <= len(ordered):
        train = ordered[start : start + train_sessions]
        test = ordered[start + train_sessions : start + train_sessions + test_sessions]
        output.append((train, test))
        start += test_sessions
    return output
