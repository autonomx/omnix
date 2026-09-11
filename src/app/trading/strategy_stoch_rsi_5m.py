"""Causal five-minute Stoch RSI strategy evaluation.

The evaluator consumes finalized regular-session bars only. A crossing is
confirmed on the close of a five-minute bar. Bullish signal candles use the
next five-minute bar's open; bearish upper-half signal candles require a later
close above the signal high before using the following bar's open. Open
positions exit on the next five-minute open after a close below the
50-period EMA calculated from five-minute closes. This module is deterministic
research evidence; it has no broker or order side effects.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from .indicator_signals import _stochastic_rsi_aligned
from .indicators.engine import exponential_moving_average
from .models import MarketBar
from .strategies.models import StochRsi5mConfig
from .strategy_timeframes import resample_final_bars


_ET = ZoneInfo("America/New_York")
_REGULAR_OPEN = time(9, 30)
_REGULAR_CLOSE = time(16, 0)
_SOURCE_INTERVAL_MINUTES = {"1m": 1, "5m": 5}
_EMA_PERIOD = 50

StochRsi5mState = Literal[
    "waiting_data",
    "data_gap",
    "waiting_oversold",
    "entry_armed",
    "long_active",
    "exit_armed",
    "exited",
    "force_flat",
]

_MIN_SIGNAL_CLOSE_LOCATION = Decimal("0.5")


class StochRsi5mSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal["stoch-rsi-5min-v4"] = "stoch-rsi-5min-v4"
    state: StochRsi5mState
    reason_code: str
    session_date: str | None = None
    as_of: datetime | None = None
    five_minute_bar_count: int = 0
    ema_50_5m: Decimal | None = None
    stochastic_rsi_k: Decimal | None = None
    stochastic_rsi_d: Decimal | None = None
    previous_stochastic_rsi_k: Decimal | None = None
    previous_stochastic_rsi_d: Decimal | None = None
    entry_signal_time: datetime | None = None
    entry_time: datetime | None = None
    entry_price: Decimal | None = None
    exit_signal_time: datetime | None = None
    exit_time: datetime | None = None
    exit_price: Decimal | None = None
    return_pct: Decimal | None = None
    data_gap_start: datetime | None = None
    data_gap_resume: datetime | None = None
    execution_authority: Literal[False] = False


def _regular_bars(bars: list[MarketBar] | tuple[MarketBar, ...]) -> list[MarketBar]:
    return sorted(
        (
            bar
            for bar in bars
            if bar.is_final
            and bar.session == "regular"
            and _REGULAR_OPEN
            <= bar.start_time.astimezone(_ET).time()
            < _REGULAR_CLOSE
        ),
        key=lambda bar: bar.start_time,
    )


def _snapshot(
    *,
    state: StochRsi5mState,
    reason_code: str,
    session_date: str | None = None,
    as_of: datetime | None = None,
    five_minute_bar_count: int = 0,
    ema_50_5m: Decimal | None = None,
    stochastic_rsi_k: Decimal | None = None,
    stochastic_rsi_d: Decimal | None = None,
    previous_stochastic_rsi_k: Decimal | None = None,
    previous_stochastic_rsi_d: Decimal | None = None,
    entry_signal_time: datetime | None = None,
    entry_time: datetime | None = None,
    entry_price: Decimal | None = None,
    exit_signal_time: datetime | None = None,
    exit_time: datetime | None = None,
    exit_price: Decimal | None = None,
    return_pct: Decimal | None = None,
    data_gap_start: datetime | None = None,
    data_gap_resume: datetime | None = None,
) -> StochRsi5mSnapshot:
    return StochRsi5mSnapshot(
        state=state,
        reason_code=reason_code,
        session_date=session_date,
        as_of=as_of,
        five_minute_bar_count=five_minute_bar_count,
        ema_50_5m=ema_50_5m,
        stochastic_rsi_k=stochastic_rsi_k,
        stochastic_rsi_d=stochastic_rsi_d,
        previous_stochastic_rsi_k=previous_stochastic_rsi_k,
        previous_stochastic_rsi_d=previous_stochastic_rsi_d,
        entry_signal_time=entry_signal_time,
        entry_time=entry_time,
        entry_price=entry_price,
        exit_signal_time=exit_signal_time,
        exit_time=exit_time,
        exit_price=exit_price,
        return_pct=return_pct,
        data_gap_start=data_gap_start,
        data_gap_resume=data_gap_resume,
    )


def _first_current_gap(
    bars: list[MarketBar],
    *,
    session_date,
    source_interval: str,
) -> tuple[datetime, datetime | None] | None:
    current = [
        bar
        for bar in bars
        if bar.start_time.astimezone(_ET).date() == session_date
    ]
    if not current:
        return None
    current.sort(key=lambda bar: bar.start_time)
    opening = current[0].start_time.astimezone(_ET)
    expected_open = datetime.combine(session_date, _REGULAR_OPEN, tzinfo=_ET)
    if opening > expected_open:
        return expected_open.astimezone(timezone.utc), current[0].start_time

    delta_minutes = _SOURCE_INTERVAL_MINUTES[source_interval]
    starts = {bar.start_time.astimezone(timezone.utc) for bar in current}
    cursor = expected_open.astimezone(timezone.utc)
    latest = current[-1].start_time.astimezone(timezone.utc)
    while cursor <= latest:
        if cursor not in starts:
            resume = next((value for value in sorted(starts) if value > cursor), None)
            return cursor, resume
        cursor += timedelta(minutes=delta_minutes)
    return None


def _entry_in_window(bar: MarketBar, config: StochRsi5mConfig) -> bool:
    local_time = bar.start_time.astimezone(_ET).time()
    return config.entry_start_et <= local_time <= config.last_entry_et


def _force_flat_reached(bar: MarketBar, config: StochRsi5mConfig) -> bool:
    return bar.end_time.astimezone(_ET).time() >= config.force_flat_et


def _signal_close_location(bar: MarketBar) -> Decimal:
    candle_range = bar.high - bar.low
    if candle_range <= 0:
        return Decimal("0")
    return (bar.close - bar.low) / candle_range


def _signal_requires_breakout(bar: MarketBar) -> bool:
    """Return whether a non-bullish signal needs a confirmed high breakout."""

    return bar.close <= bar.open


def _bearish_bottom_half(bar: MarketBar) -> bool:
    return (
        bar.close < bar.open
        and _signal_close_location(bar) <= _MIN_SIGNAL_CLOSE_LOCATION
    )


def evaluate_stoch_rsi_5m(
    bars: list[MarketBar] | tuple[MarketBar, ...],
    config: StochRsi5mConfig | None = None,
) -> StochRsi5mSnapshot:
    """Evaluate Stoch RSI entries and 5m EMA exits on finalized bars."""

    active = config or StochRsi5mConfig()
    regular = _regular_bars(bars)
    if not regular:
        return _snapshot(
            state="waiting_data",
            reason_code="STOCH_RSI_5M_DATA_UNAVAILABLE",
        )

    session_date = regular[-1].start_time.astimezone(_ET).date()
    source_intervals = {bar.interval for bar in regular}
    if len(source_intervals) != 1:
        raise ValueError("stoch-rsi-5min requires one source interval")
    source_interval = next(iter(source_intervals))
    if source_interval not in _SOURCE_INTERVAL_MINUTES:
        raise ValueError("stoch-rsi-5min accepts only 1m or 5m source bars")

    gap = _first_current_gap(
        regular,
        session_date=session_date,
        source_interval=source_interval,
    )
    if gap is not None:
        return _snapshot(
            state="data_gap",
            reason_code="STOCH_RSI_5M_DATA_GAP",
            session_date=session_date.isoformat(),
            as_of=regular[-1].end_time,
            data_gap_start=gap[0],
            data_gap_resume=gap[1],
        )

    sampled = regular if source_interval == "5m" else resample_final_bars(regular, "5m")
    if not sampled:
        return _snapshot(
            state="waiting_data",
            reason_code="STOCH_RSI_5M_WAITING_FOR_COMPLETED_BAR",
            session_date=session_date.isoformat(),
            as_of=regular[-1].end_time,
        )

    sampled = sorted(sampled, key=lambda bar: bar.start_time)
    ema_values = exponential_moving_average(
        (bar.close for bar in sampled),
        _EMA_PERIOD,
    )
    ema_start_index = _EMA_PERIOD - 1
    if not ema_values:
        return _snapshot(
            state="waiting_data",
            reason_code="STOCH_RSI_5M_50_5M_EMA_WARMUP",
            session_date=session_date.isoformat(),
            as_of=sampled[-1].end_time,
            five_minute_bar_count=len(sampled),
            ema_50_5m=None,
        )
    closes = [bar.close for bar in sampled]
    k_values, d_values = _stochastic_rsi_aligned(
        closes,
        rsi_period=active.rsi_period,
        stochastic_period=active.stochastic_period,
        smoothing_period=active.k_smoothing_period,
        signal_period=active.d_smoothing_period,
    )
    last = sampled[-1]
    last_k = k_values[-1] if k_values else None
    last_d = d_values[-1] if d_values else None
    previous_k = k_values[-2] if len(k_values) > 1 else None
    previous_d = d_values[-2] if len(d_values) > 1 else None
    common = {
        "session_date": session_date.isoformat(),
        "as_of": last.end_time,
        "five_minute_bar_count": len(sampled),
        "ema_50_5m": ema_values[-1],
        "stochastic_rsi_k": last_k,
        "stochastic_rsi_d": last_d,
        "previous_stochastic_rsi_k": previous_k,
        "previous_stochastic_rsi_d": previous_d,
    }
    if last_k is None or last_d is None:
        return _snapshot(
            state="waiting_data",
            reason_code="STOCH_RSI_5M_WARMUP",
            **common,
        )

    current_session_indexes = [
        index
        for index, bar in enumerate(sampled)
        if bar.start_time.astimezone(_ET).date() == session_date
    ]
    if not current_session_indexes:
        return _snapshot(
            state="waiting_data",
            reason_code="STOCH_RSI_5M_CURRENT_SESSION_UNAVAILABLE",
            **common,
        )

    def crossed_up(index: int) -> bool:
        if index <= 0 or k_values[index] is None or d_values[index] is None:
            return False
        prior_k = k_values[index - 1]
        prior_d = d_values[index - 1]
        current_k = k_values[index]
        current_d = d_values[index]
        return (
            prior_k is not None
            and prior_d is not None
            and current_k is not None
            and current_d is not None
            and prior_k <= prior_d
            and current_k > current_d
            and current_k < active.oversold_threshold
        )

    def crossed_down(index: int) -> bool:
        if index <= 0 or k_values[index] is None or d_values[index] is None:
            return False
        prior_k = k_values[index - 1]
        prior_d = d_values[index - 1]
        current_k = k_values[index]
        current_d = d_values[index]
        return (
            prior_k is not None
            and prior_d is not None
            and current_k is not None
            and current_d is not None
            and prior_k >= prior_d
            and current_k < current_d
            and current_k > active.overbought_threshold
        )

    entry_index: int | None = None
    entry_signal_index: int | None = None
    pending_entry_index: int | None = None
    pending_confirmation_index: int | None = None
    rejected_price_confirmation = False
    for index in current_session_indexes:
        if not crossed_up(index):
            continue

        signal_bar = sampled[index]
        if not _entry_in_window(signal_bar, active):
            continue

        if _bearish_bottom_half(signal_bar):
            rejected_price_confirmation = True
            continue

        if not _signal_requires_breakout(signal_bar):
            next_index = index + 1
            if next_index >= len(sampled):
                pending_entry_index = index
                continue
            next_bar = sampled[next_index]
            if (
                next_bar.start_time.astimezone(_ET).date() == session_date
                and _entry_in_window(next_bar, active)
            ):
                entry_index = next_index
                entry_signal_index = index
                break
            continue

        breakout_index: int | None = None
        for candidate_index in range(index + 1, len(sampled)):
            candidate = sampled[candidate_index]
            if candidate.start_time.astimezone(_ET).date() != session_date:
                break
            if candidate.close <= signal_bar.high:
                continue
            breakout_index = candidate_index
            break
        if breakout_index is None:
            pending_confirmation_index = index
            continue

        next_index = breakout_index + 1
        if next_index >= len(sampled):
            pending_confirmation_index = index
            continue
        next_bar = sampled[next_index]
        if (
            next_bar.start_time.astimezone(_ET).date() == session_date
            and _entry_in_window(next_bar, active)
        ):
            entry_index = next_index
            entry_signal_index = index
            break

    if entry_index is None:
        if pending_entry_index is not None:
            signal_bar = sampled[pending_entry_index]
            return _snapshot(
                state="entry_armed",
                reason_code="STOCH_RSI_5M_OVERSOLD_CROSS_UP",
                entry_signal_time=signal_bar.end_time,
                **common,
            )
        if pending_confirmation_index is not None:
            signal_bar = sampled[pending_confirmation_index]
            return _snapshot(
                state="entry_armed",
                reason_code="STOCH_RSI_5M_WAITING_PRICE_CONFIRMATION",
                entry_signal_time=signal_bar.end_time,
                **common,
            )
        if rejected_price_confirmation:
            return _snapshot(
                state="waiting_oversold",
                reason_code="STOCH_RSI_5M_PRICE_CONFIRMATION_REJECTED",
                **common,
            )
        return _snapshot(
            state="waiting_oversold",
            reason_code="STOCH_RSI_5M_WAITING_OVERSOLD_CROSS_UP",
            **common,
        )

    entry_bar = sampled[entry_index]
    entry_signal_bar = sampled[entry_signal_index]
    entry_price = entry_bar.open
    exit_signal_index: int | None = None
    exit_index: int | None = None
    exit_reason_code = "STOCH_RSI_5M_OVERBOUGHT_CROSS_DOWN"
    for index in range(entry_index, len(sampled)):
        ema_index = index - ema_start_index
        ema_value = ema_values[ema_index] if 0 <= ema_index < len(ema_values) else None
        if ema_value is not None and sampled[index].close < ema_value:
            next_index = index + 1
            if next_index < len(sampled):
                next_bar = sampled[next_index]
                if (
                    next_bar.start_time.astimezone(_ET).date() == session_date
                    and next_bar.start_time.astimezone(_ET).time() <= active.force_flat_et
                ):
                    exit_signal_index = index
                    exit_index = next_index
                    exit_reason_code = "STOCH_RSI_5M_CLOSE_BELOW_50_5M_EMA"
                    break
        if not crossed_down(index):
            continue
        next_index = index + 1
        if next_index < len(sampled):
            next_bar = sampled[next_index]
            if (
                next_bar.start_time.astimezone(_ET).date() == session_date
                and next_bar.start_time.astimezone(_ET).time() <= active.force_flat_et
            ):
                exit_signal_index = index
                exit_index = next_index
                exit_reason_code = "STOCH_RSI_5M_OVERBOUGHT_CROSS_DOWN"
                break
        if _force_flat_reached(sampled[index], active):
            exit_signal_index = index
            break

    if exit_signal_index is not None and exit_index is not None:
        exit_bar = sampled[exit_index]
        exit_price = exit_bar.open
        return _snapshot(
            state="exited",
            reason_code=exit_reason_code,
            entry_signal_time=entry_signal_bar.end_time,
            entry_time=entry_bar.start_time,
            entry_price=entry_price,
            exit_signal_time=sampled[exit_signal_index].end_time,
            exit_time=exit_bar.start_time,
            exit_price=exit_price,
            return_pct=(exit_price - entry_price) / entry_price * Decimal("100"),
            **common,
        )

    force_flat_bar = next(
        (bar for bar in sampled[entry_index:] if _force_flat_reached(bar, active)),
        None,
    )
    if force_flat_bar is not None:
        exit_price = force_flat_bar.close
        return _snapshot(
            state="force_flat",
            reason_code="STOCH_RSI_5M_FORCE_FLAT",
            entry_signal_time=entry_signal_bar.end_time,
            entry_time=entry_bar.start_time,
            entry_price=entry_price,
            exit_time=force_flat_bar.end_time,
            exit_price=exit_price,
            return_pct=(exit_price - entry_price) / entry_price * Decimal("100"),
            **common,
        )

    if any(crossed_down(index) for index in range(entry_index, len(sampled))):
        return _snapshot(
            state="exit_armed",
            reason_code="STOCH_RSI_5M_OVERBOUGHT_CROSS_DOWN",
            entry_signal_time=entry_signal_bar.end_time,
            entry_time=entry_bar.start_time,
            entry_price=entry_price,
            **common,
        )
    return _snapshot(
        state="long_active",
        reason_code="STOCH_RSI_5M_LONG_ACTIVE",
        entry_signal_time=entry_signal_bar.end_time,
        entry_time=entry_bar.start_time,
        entry_price=entry_price,
        **common,
    )


__all__ = ["StochRsi5mSnapshot", "StochRsi5mState", "evaluate_stoch_rsi_5m"]
