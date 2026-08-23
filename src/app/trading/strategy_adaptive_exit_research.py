from __future__ import annotations

"""Research-only adaptive exit replay for fixed historical entries.

This module has no strategy/order authority. It replays an already-selected
backtest entry with a predeclared trend-following exit so entry selection and
exit management can be compared independently.
"""

from datetime import datetime, time
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from .gapper_dataset import GapperCandidate
from .indicator_signals import MultiTimeframeIndicatorContext, multi_timeframe_indicator_context
from .models import MarketBar
from .paper import PaperExecutionPolicy, PaperOrder, paper_fill_decision, paper_protection_trigger
from .strategies.models import GapPullbackConfig
from .strategy_backtest import (
    GapPullbackBacktestTrade,
    _adverse_sell_slippage_bps,
    _bar_observation,
    _exit_market_decision,
)
from .strategy_timeframes import resample_final_bars
from .strategy_v2_management import v2_active_stop_for_prior_high


_ET = ZoneInfo("America/New_York")
_FORCE_FLAT_ET = time(15, 55)
_NO_TARGET_MULTIPLE = Decimal("1000000")


class AdaptiveExitDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    exit: bool = False
    reason_codes: tuple[str, ...] = ()
    one_minute_warning_count: int = 0
    five_minute_trend_break: bool = False
    five_minute_strong_break: bool = False


class AdaptiveExitReplayTrade(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str
    entry_time: datetime
    baseline_exit_time: datetime
    entry_price: Decimal
    stop_price: Decimal
    entry_fill_quantity: Decimal
    exit_time: datetime
    exit_price: Decimal
    exit_reason: Literal["stop", "indicator", "force_flat"]
    indicator_reason_codes: tuple[str, ...] = ()
    exit_slippage_bps: Decimal
    pnl_per_share: Decimal
    r_multiple: Decimal
    mfe_r: Decimal
    mae_r: Decimal
    hold_minutes: Decimal


def adaptive_exit_deterioration(
    current: MultiTimeframeIndicatorContext,
    previous: MultiTimeframeIndicatorContext | None,
) -> AdaptiveExitDecision:
    """Return the frozen adaptive-exit decision from finalized indicator state.

    A one-minute warning never exits by itself. The five-minute trend must first
    be below a falling EMA9, then either two tactical 1m warnings or one stronger
    5m confirmation must agree. Stoch RSI contributes only on a bearish cross
    after an overbought prior reading; merely being overbought is not bearish.
    """

    one = current.one_minute
    five = current.five_minute
    warnings: list[str] = []
    strong: list[str] = []

    if one.price_above_ema9 is False and one.ema9_rising is False:
        warnings.append("ADAPTIVE_EXIT_1M_EMA_WEAKNESS")
    if one.macd_bullish is False and one.macd_histogram is not None and one.macd_histogram < 0:
        warnings.append("ADAPTIVE_EXIT_1M_MACD_BEARISH")

    if previous is not None:
        prior = previous.one_minute
        if (
            prior.stochastic_rsi_k is not None
            and prior.stochastic_rsi_d is not None
            and one.stochastic_rsi_k is not None
            and one.stochastic_rsi_d is not None
            and prior.stochastic_rsi_k >= Decimal("80")
            and prior.stochastic_rsi_k >= prior.stochastic_rsi_d
            and one.stochastic_rsi_k < one.stochastic_rsi_d
        ):
            warnings.append("ADAPTIVE_EXIT_1M_STOCH_OVERBOUGHT_CROSS_DOWN")

    five_break = five.price_above_ema9 is False and five.ema9_rising is False
    if five.close is not None and five.ema20 is not None and five.close < five.ema20:
        strong.append("ADAPTIVE_EXIT_5M_PRICE_BELOW_EMA20")
    if five.macd_bullish is False and five.stochastic_rsi_bullish is False:
        strong.append("ADAPTIVE_EXIT_5M_MACD_STOCH_BEARISH")

    should_exit = five_break and (len(warnings) >= 2 or bool(strong))
    reasons: list[str] = []
    if should_exit:
        reasons.append("ADAPTIVE_EXIT_5M_TREND_BREAK")
        reasons.extend(warnings)
        reasons.extend(strong)
    return AdaptiveExitDecision(
        exit=should_exit,
        reason_codes=tuple(reasons),
        one_minute_warning_count=len(warnings),
        five_minute_trend_break=five_break,
        five_minute_strong_break=bool(strong),
    )


def _stop_fill(
    *,
    candidate: GapperCandidate,
    bar: MarketBar,
    quantity: Decimal,
    active_stop: Decimal,
    policy: PaperExecutionPolicy,
    assumed_spread_bps: Decimal,
    open_only: bool,
):
    observation = _bar_observation(
        bar,
        instrument_id=candidate.instrument_id,
        binding_id=candidate.binding_id,
        spread_bps=assumed_spread_bps,
        price=bar.open,
    )
    if open_only:
        observation = observation.model_copy(update={"high": bar.open, "low": bar.open, "price": bar.open})
    order = PaperOrder(
        account_id="backtest",
        order_id=f"adaptive-stop:{candidate.instrument_id}:{bar.start_time.isoformat()}",
        instrument_id=candidate.instrument_id,
        binding_id=candidate.binding_id,
        side="sell",
        order_type="stop",
        quantity=quantity,
        stop_price=active_stop,
        idempotency_key=f"adaptive-stop:{candidate.instrument_id}:{bar.start_time.isoformat()}",
    )
    return paper_fill_decision(order, observation, policy)


def replay_adaptive_indicator_exit(
    *,
    candidate: GapperCandidate,
    bars: list[MarketBar] | tuple[MarketBar, ...],
    baseline_trade: GapPullbackBacktestTrade,
    config: GapPullbackConfig,
    policy: PaperExecutionPolicy,
    assumed_spread_bps: Decimal,
    force_flat_et: time = _FORCE_FLAT_ET,
) -> AdaptiveExitReplayTrade:
    """Replay policy B from the exact baseline entry/fill/size.

    The initial structural stop and V2 +0.75R -> +0.25R protection are retained.
    There is no fixed profit target and no 60-minute time exit. Indicator exits
    are decided only on finalized bars and submitted at the next 1m bar open.
    Force-flat uses the last finalized bar known by 15:55 ET, never a later bar.
    """

    if candidate.instrument_id != baseline_trade.instrument_id:
        raise ValueError("candidate/trade instrument mismatch")
    execution_bars = tuple(resample_final_bars(bars, config.execution_interval))
    entry_index = next(
        (index for index, bar in enumerate(execution_bars) if bar.start_time == baseline_trade.entry_time),
        None,
    )
    if entry_index is None:
        raise ValueError("baseline entry is not present in replay bars")

    entry = baseline_trade.entry_price
    stop = baseline_trade.stop_price
    risk = entry - stop
    if risk <= 0:
        raise ValueError("baseline trade has non-positive risk")
    quantity = baseline_trade.entry_fill_quantity
    unreachable_target = entry + risk * _NO_TARGET_MULTIPLE

    force_flat_index = max(
        (
            index
            for index, bar in enumerate(execution_bars)
            if index >= entry_index and bar.start_time.astimezone(_ET).time() < force_flat_et
        ),
        default=len(execution_bars) - 1,
    )

    max_high = entry
    min_low = entry
    previous_context = multi_timeframe_indicator_context(execution_bars[:entry_index]) if entry_index > 0 else None
    pending_indicator_reasons: tuple[str, ...] | None = None
    last_exit_rejection: str | None = None

    exit_price: Decimal | None = None
    exit_time: datetime | None = None
    exit_reference: Decimal | None = None
    exit_reason: Literal["stop", "indicator", "force_flat"] | None = None
    exit_indicator_reasons: tuple[str, ...] = ()

    for index in range(entry_index, min(len(execution_bars), force_flat_index + 1)):
        bar = execution_bars[index]
        active_stop = v2_active_stop_for_prior_high(
            config,
            entry_price=entry,
            initial_stop=stop,
            prior_finalized_high=max_high,
        )

        # A pending next-bar market exit owns the bar open. A gap through the
        # already-active stop is still treated pessimistically as the stop first.
        if pending_indicator_reasons is not None:
            max_high = max(max_high, bar.open)
            min_low = min(min_low, bar.open)
            if bar.open <= active_stop:
                stop_decision = _stop_fill(
                    candidate=candidate,
                    bar=bar,
                    quantity=quantity,
                    active_stop=active_stop,
                    policy=policy,
                    assumed_spread_bps=assumed_spread_bps,
                    open_only=True,
                )
                if (
                    stop_decision.should_fill
                    and stop_decision.fill_price is not None
                    and stop_decision.fill_quantity is not None
                    and stop_decision.fill_quantity >= quantity
                ):
                    exit_price = stop_decision.fill_price
                    exit_time = bar.start_time
                    exit_reference = active_stop
                    exit_reason = "stop"
                    break
                last_exit_rejection = f"exit_execution:{stop_decision.reason}"

            market = _exit_market_decision(
                candidate=candidate,
                bar=bar,
                quantity=quantity,
                policy=policy,
                assumed_spread_bps=assumed_spread_bps,
                price=bar.open,
                order_suffix="adaptive-indicator",
            )
            if (
                market.should_fill
                and market.fill_price is not None
                and market.fill_quantity is not None
                and market.fill_quantity >= quantity
            ):
                exit_price = market.fill_price
                exit_time = bar.start_time
                exit_reference = bar.open
                exit_reason = "indicator"
                exit_indicator_reasons = pending_indicator_reasons
                break
            last_exit_rejection = f"exit_execution:{market.reason}"

        max_high = max(max_high, bar.high)
        min_low = min(min_low, bar.low)
        observation = _bar_observation(
            bar,
            instrument_id=candidate.instrument_id,
            binding_id=candidate.binding_id,
            spread_bps=assumed_spread_bps,
            price=bar.open,
        )
        trigger = paper_protection_trigger(
            is_long=True,
            stop_price=active_stop,
            target_price=unreachable_target,
            observation=observation,
            activated_at=baseline_trade.entry_time,
        )
        if trigger == "stop":
            stop_decision = _stop_fill(
                candidate=candidate,
                bar=bar,
                quantity=quantity,
                active_stop=active_stop,
                policy=policy,
                assumed_spread_bps=assumed_spread_bps,
                open_only=False,
            )
            if (
                stop_decision.should_fill
                and stop_decision.fill_price is not None
                and stop_decision.fill_quantity is not None
                and stop_decision.fill_quantity >= quantity
            ):
                exit_price = stop_decision.fill_price
                exit_time = bar.end_time
                exit_reference = active_stop
                exit_reason = "stop"
                break
            last_exit_rejection = f"exit_execution:{stop_decision.reason}"

        context = multi_timeframe_indicator_context(execution_bars[: index + 1])
        decision = adaptive_exit_deterioration(context, previous_context)
        previous_context = context
        if decision.exit and pending_indicator_reasons is None:
            pending_indicator_reasons = decision.reason_codes

        if index == force_flat_index:
            market = _exit_market_decision(
                candidate=candidate,
                bar=bar,
                quantity=quantity,
                policy=policy,
                assumed_spread_bps=assumed_spread_bps,
                price=bar.close,
                order_suffix="adaptive-force-flat",
            )
            if (
                market.should_fill
                and market.fill_price is not None
                and market.fill_quantity is not None
                and market.fill_quantity >= quantity
            ):
                exit_price = market.fill_price
                exit_time = bar.end_time
                exit_reference = bar.close
                exit_reason = "force_flat"
                break
            last_exit_rejection = f"exit_execution:{market.reason}"

    if exit_price is None or exit_time is None or exit_reference is None or exit_reason is None:
        raise RuntimeError(last_exit_rejection or "adaptive exit could not be filled by force-flat cutoff")

    pnl = exit_price - entry
    return AdaptiveExitReplayTrade(
        instrument_id=candidate.instrument_id,
        entry_time=baseline_trade.entry_time,
        baseline_exit_time=baseline_trade.exit_time,
        entry_price=entry,
        stop_price=stop,
        entry_fill_quantity=quantity,
        exit_time=exit_time,
        exit_price=exit_price,
        exit_reason=exit_reason,
        indicator_reason_codes=exit_indicator_reasons,
        exit_slippage_bps=_adverse_sell_slippage_bps(exit_price, exit_reference),
        pnl_per_share=pnl,
        r_multiple=pnl / risk,
        mfe_r=(max_high - entry) / risk,
        mae_r=(min_low - entry) / risk,
        hold_minutes=Decimal(str((exit_time - baseline_trade.entry_time).total_seconds() / 60)),
    )


__all__ = [
    "AdaptiveExitDecision",
    "AdaptiveExitReplayTrade",
    "adaptive_exit_deterioration",
    "replay_adaptive_indicator_exit",
]
