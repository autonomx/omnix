from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

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


class BacktestSessionDataset(BaseModel):
    """Frozen multi-symbol morning dataset paired to the candidate universe."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_date: date
    universe: GapperUniverseSnapshot
    bars_by_instrument: dict[str, tuple[MarketBar, ...]]
    dataset_fingerprint: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def candidate_coverage(self):
        missing = [
            candidate.instrument_id
            for candidate in self.universe.candidates
            if candidate.instrument_id not in self.bars_by_instrument
        ]
        if missing:
            raise ValueError(f"missing candidate bars: {','.join(missing)}")
        return self


class GapPullbackBacktestTrade(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
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
    win_count: int
    loss_count: int
    win_rate: Decimal
    expectancy_r: Decimal
    profit_factor: Decimal | None
    average_mfe_r: Decimal
    average_mae_r: Decimal
    candidate_to_trigger_rate: Decimal
    average_hold_minutes: Decimal
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


def freeze_backtest_session(
    *,
    session_date: date,
    universe: GapperUniverseSnapshot,
    bars_by_instrument: dict[str, list[MarketBar] | tuple[MarketBar, ...]],
) -> BacktestSessionDataset:
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
                    "o": str(bar.open), "h": str(bar.high), "l": str(bar.low),
                    "c": str(bar.close), "v": str(bar.volume),
                    "provider": bar.provider, "final": bar.is_final,
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


def _find_trade(
    candidate,
    bars: tuple[MarketBar, ...],
    config: GapPullbackConfig,
    policy: PaperExecutionPolicy,
    *,
    assumed_spread_bps: Decimal,
    max_hold_minutes: int,
) -> GapPullbackBacktestTrade | None:
    trigger_index: int | None = None
    signal = None
    for index in range(1, len(bars) + 1):
        result = evaluate_gap_pullback(candidate, bars[:index], config)
        if result.state == "entry_ready" and result.signal is not None:
            trigger_index = index - 1
            signal = result.signal
            break
    if trigger_index is None or signal is None or trigger_index + 1 >= len(bars):
        return None

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
    if not entry_decision.should_fill or entry_decision.fill_price is None:
        return None
    entry = entry_decision.fill_price
    stop = signal.stop_price
    risk = entry - stop
    if risk <= 0:
        return None
    target = entry + risk * config.reward_multiple
    horizon = entry_bar.start_time + timedelta(minutes=max_hold_minutes)
    exit_price = bars[-1].close
    exit_time = bars[-1].end_time
    exit_reason: Literal["stop", "target", "time", "eod"] = "eod"
    max_high = entry
    min_low = entry

    for index in range(entry_index, len(bars)):
        bar = bars[index]
        max_high = max(max_high, bar.high)
        min_low = min(min_low, bar.low)
        stop_hit = bar.low <= stop
        target_hit = bar.high >= target
        if stop_hit:
            # Same-bar ambiguity is resolved pessimistically: stop before target.
            stop_order = PaperOrder(
                account_id="backtest",
                order_id=f"stop:{candidate.instrument_id}:{index}",
                instrument_id=candidate.instrument_id,
                binding_id=candidate.binding_id,
                side="sell",
                order_type="stop",
                quantity=Decimal("1"),
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
            if decision.should_fill and decision.fill_price is not None:
                exit_price = decision.fill_price
                exit_time = bar.end_time
                exit_reason = "stop"
                break
        if target_hit:
            target_order = PaperOrder(
                account_id="backtest",
                order_id=f"target:{candidate.instrument_id}:{index}",
                instrument_id=candidate.instrument_id,
                binding_id=candidate.binding_id,
                side="sell",
                order_type="limit",
                quantity=Decimal("1"),
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
            if decision.should_fill and decision.fill_price is not None:
                exit_price = decision.fill_price
                exit_time = bar.end_time
                exit_reason = "target"
                break
        if bar.end_time >= horizon:
            exit_price = bar.close * (Decimal("1") - assumed_spread_bps / Decimal("20000"))
            exit_time = bar.end_time
            exit_reason = "time"
            break

    pnl = exit_price - entry
    r_multiple = pnl / risk
    mfe_r = (max_high - entry) / risk
    mae_r = (min_low - entry) / risk
    hold_minutes = Decimal(str((exit_time - entry_bar.start_time).total_seconds() / 60))
    return GapPullbackBacktestTrade(
        instrument_id=candidate.instrument_id,
        entry_time=entry_bar.start_time,
        exit_time=exit_time,
        entry_price=entry,
        exit_price=exit_price,
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


def run_gap_pullback_backtest(
    dataset: BacktestSessionDataset,
    config: GapPullbackConfig | None = None,
    execution_policy: PaperExecutionPolicy | None = None,
    *,
    assumed_spread_bps: Decimal = Decimal("40"),
    max_hold_minutes: int = 90,
    max_concurrent_positions: int = 3,
) -> GapPullbackBacktestResult:
    active = config or GapPullbackConfig()
    policy = execution_policy or PaperExecutionPolicy(max_volume_participation_pct=Decimal("1"))
    proposed: list[GapPullbackBacktestTrade] = []
    for candidate in dataset.universe.candidates:
        trade = _find_trade(
            candidate,
            dataset.bars_by_instrument[candidate.instrument_id],
            active,
            policy,
            assumed_spread_bps=assumed_spread_bps,
            max_hold_minutes=max_hold_minutes,
        )
        if trade is not None:
            proposed.append(trade)
    proposed.sort(key=lambda trade: (trade.entry_time, trade.instrument_id))

    selected: list[GapPullbackBacktestTrade] = []
    for trade in proposed:
        concurrent = sum(
            1 for existing in selected if existing.entry_time <= trade.entry_time < existing.exit_time
        )
        if concurrent < max_concurrent_positions:
            selected.append(trade)

    count = len(selected)
    wins = sum(1 for trade in selected if trade.r_multiple > 0)
    losses = sum(1 for trade in selected if trade.r_multiple < 0)
    positive = sum((trade.r_multiple for trade in selected if trade.r_multiple > 0), Decimal("0"))
    negative = abs(sum((trade.r_multiple for trade in selected if trade.r_multiple < 0), Decimal("0")))
    divisor = Decimal(count) if count else Decimal("1")
    summary = GapPullbackBacktestSummary(
        candidate_count=len(dataset.universe.candidates),
        trigger_count=len(proposed),
        trade_count=count,
        win_count=wins,
        loss_count=losses,
        win_rate=Decimal(wins) / divisor,
        expectancy_r=sum((trade.r_multiple for trade in selected), Decimal("0")) / divisor,
        profit_factor=positive / negative if negative > 0 else None,
        average_mfe_r=sum((trade.mfe_r for trade in selected), Decimal("0")) / divisor,
        average_mae_r=sum((trade.mae_r for trade in selected), Decimal("0")) / divisor,
        candidate_to_trigger_rate=(
            Decimal(len(proposed)) / Decimal(len(dataset.universe.candidates))
            if dataset.universe.candidates
            else Decimal("0")
        ),
        average_hold_minutes=sum((trade.hold_minutes for trade in selected), Decimal("0")) / divisor,
        stop_count=sum(1 for trade in selected if trade.exit_reason == "stop"),
        target_count=sum(1 for trade in selected if trade.exit_reason == "target"),
        time_exit_count=sum(1 for trade in selected if trade.exit_reason in {"time", "eod"}),
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
