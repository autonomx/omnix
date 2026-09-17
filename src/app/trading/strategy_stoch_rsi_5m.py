"""Causal five-minute Stoch RSI strategy evaluation.

The frozen ``baseline_v12`` policy preserves the historical evaluator. The
``guarded_v1`` research profile keeps the same oscillator setup and loose
winner-management exits, but requires stronger price/trend/volume confirmation,
adds failure-aware re-entry throttling, and uses a structural catastrophic-loss
guard. Both profiles are deterministic research evidence with no broker or
order side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from .indicator_signals import _stochastic_rsi_aligned
from .indicators.engine import exponential_moving_average
from .models import MarketBar
from .strategies.gap_pullback import session_vwap
from .strategies.models import StochRsi5mConfig
from .strategy_timeframes import resample_final_bars


_ET = ZoneInfo("America/New_York")
_REGULAR_OPEN = time(9, 30)
_REGULAR_CLOSE = time(16, 0)
_SOURCE_INTERVAL_MINUTES = {"1m": 1, "5m": 5}
_EMA_PERIOD = 50
_STOCH_RSI_MIDLINE_EXIT_THRESHOLD = Decimal("80")

StochRsi5mState = Literal[
    "waiting_data",
    "data_gap",
    "waiting_oversold",
    "setup_armed",
    "entry_armed",
    "long_active",
    "exit_armed",
    "exited",
    "force_flat",
]
StochRsi5mPolicyVersion = Literal[
    "stoch-rsi-5min-v12",
    "stoch-rsi-5min-guarded-v1",
]


@dataclass(frozen=True)
class _EntrySearch:
    found: bool
    state: StochRsi5mState
    reason_code: str
    entry_index: int | None = None
    entry_signal_index: int | None = None
    entry_arm_index: int | None = None
    entry_momentum_cross_index: int | None = None
    initial_stop_price: Decimal | None = None
    entry_vwap: Decimal | None = None
    ema_slope_pct: Decimal | None = None
    recovery_volume_ratio: Decimal | None = None
    loss_count_before_entry: int = 0
    structural_reset_required: bool = False


@dataclass(frozen=True)
class _ExitSearch:
    state: Literal["exited", "force_flat", "exit_armed", "long_active"]
    reason_code: str
    exit_signal_index: int | None = None
    exit_index: int | None = None
    force_flat_index: int | None = None


class StochRsi5mTrade(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    oversold_arm_time: datetime
    momentum_cross_time: datetime
    entry_signal_time: datetime
    entry_time: datetime
    entry_price: Decimal
    exit_signal_time: datetime | None = None
    exit_time: datetime
    exit_price: Decimal
    exit_reason_code: str
    return_pct: Decimal
    initial_stop_price: Decimal | None = None
    entry_vwap: Decimal | None = None
    ema_slope_pct: Decimal | None = None
    recovery_volume_ratio: Decimal | None = None
    loss_count_before_entry: int = 0
    structural_reset_required: bool = False


class StochRsi5mSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: StochRsi5mPolicyVersion = "stoch-rsi-5min-v12"
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
    oversold_arm_time: datetime | None = None
    momentum_cross_time: datetime | None = None
    entry_signal_time: datetime | None = None
    entry_time: datetime | None = None
    entry_price: Decimal | None = None
    exit_signal_time: datetime | None = None
    exit_time: datetime | None = None
    exit_price: Decimal | None = None
    return_pct: Decimal | None = None
    trades: tuple[StochRsi5mTrade, ...] = ()
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
    policy_version: StochRsi5mPolicyVersion = "stoch-rsi-5min-v12",
    session_date: str | None = None,
    as_of: datetime | None = None,
    five_minute_bar_count: int = 0,
    ema_50_5m: Decimal | None = None,
    stochastic_rsi_k: Decimal | None = None,
    stochastic_rsi_d: Decimal | None = None,
    previous_stochastic_rsi_k: Decimal | None = None,
    previous_stochastic_rsi_d: Decimal | None = None,
    oversold_arm_time: datetime | None = None,
    momentum_cross_time: datetime | None = None,
    entry_signal_time: datetime | None = None,
    entry_time: datetime | None = None,
    entry_price: Decimal | None = None,
    exit_signal_time: datetime | None = None,
    exit_time: datetime | None = None,
    exit_price: Decimal | None = None,
    return_pct: Decimal | None = None,
    trades: tuple[StochRsi5mTrade, ...] = (),
    data_gap_start: datetime | None = None,
    data_gap_resume: datetime | None = None,
) -> StochRsi5mSnapshot:
    return StochRsi5mSnapshot(
        policy_version=policy_version,
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
        oversold_arm_time=oversold_arm_time,
        momentum_cross_time=momentum_cross_time,
        entry_signal_time=entry_signal_time,
        entry_time=entry_time,
        entry_price=entry_price,
        exit_signal_time=exit_signal_time,
        exit_time=exit_time,
        exit_price=exit_price,
        return_pct=return_pct,
        trades=trades,
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


def _ema_at(ema_values: list[Decimal], index: int) -> Decimal | None:
    ema_index = index - (_EMA_PERIOD - 1)
    if not 0 <= ema_index < len(ema_values):
        return None
    return ema_values[ema_index]


def _signal_requires_breakout(bar: MarketBar) -> bool:
    """Return whether a non-bullish baseline signal needs a confirmed high breakout."""

    return bar.close <= bar.open


def evaluate_stoch_rsi_5m(
    bars: list[MarketBar] | tuple[MarketBar, ...],
    config: StochRsi5mConfig | None = None,
) -> StochRsi5mSnapshot:
    """Evaluate the selected Stoch RSI research profile on finalized bars."""

    active = config or StochRsi5mConfig()
    guarded = active.policy_profile == "guarded_v1"
    policy_version: StochRsi5mPolicyVersion = (
        "stoch-rsi-5min-guarded-v1" if guarded else "stoch-rsi-5min-v12"
    )
    regular = _regular_bars(bars)
    if not regular:
        return _snapshot(
            state="waiting_data",
            reason_code="STOCH_RSI_5M_DATA_UNAVAILABLE",
            policy_version=policy_version,
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
            policy_version=policy_version,
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
            policy_version=policy_version,
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
            policy_version=policy_version,
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
        "policy_version": policy_version,
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
    session_start_index = current_session_indexes[0]

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
        )

    def recovery_confirmed(index: int) -> bool:
        if index <= 0 or k_values[index] is None or d_values[index] is None:
            return False
        prior_k = k_values[index - 1]
        current_k = k_values[index]
        current_d = d_values[index]
        return (
            prior_k is not None
            and current_k is not None
            and current_d is not None
            and current_k >= active.recovery_threshold
            and current_k > prior_k
            and current_k > current_d
        )

    def stochastic_crossed_down(index: int) -> bool:
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
        )

    def crossed_down(index: int) -> bool:
        return (
            stochastic_crossed_down(index)
            and k_values[index] is not None
            and k_values[index] > active.overbought_threshold
        )

    def crossed_down_below_midline(index: int) -> bool:
        return (
            stochastic_crossed_down(index)
            and k_values[index] is not None
            and k_values[index] < _STOCH_RSI_MIDLINE_EXIT_THRESHOLD
        )

    def ema_slope_pct(index: int) -> Decimal | None:
        current = _ema_at(ema_values, index)
        prior = _ema_at(ema_values, index - active.guarded_ema_slope_lookback_bars)
        if current is None or prior is None or prior == 0:
            return None
        return (current - prior) / prior * Decimal("100")

    def vwap_at(index: int) -> Decimal | None:
        return session_vwap(sampled[session_start_index : index + 1])

    def recovery_volume_ratio(arm_index: int, signal_index: int, breakout_index: int) -> Decimal | None:
        reference = sampled[arm_index:signal_index]
        if not reference:
            reference = sampled[max(session_start_index, signal_index - 3) : signal_index]
        if not reference:
            return None
        average_volume = sum((bar.volume for bar in reference), Decimal("0")) / Decimal(len(reference))
        if average_volume <= 0:
            return None
        return sampled[breakout_index].volume / average_volume

    def structural_reset_confirmed(index: int) -> bool:
        prior = sampled[session_start_index:index]
        if not prior:
            return False
        prior_high = max(bar.high for bar in prior)
        return sampled[index].close > prior_high

    def structural_stop(arm_index: int, breakout_index: int) -> Decimal:
        return min(bar.low for bar in sampled[arm_index : breakout_index + 1])

    def _entry_search(
        start_index: int,
        completed_trades: tuple[StochRsi5mTrade, ...],
    ) -> _EntrySearch:
        active_arm_index: int | None = None
        active_momentum_cross_index: int | None = None
        latest_arm_index: int | None = None
        latest_momentum_cross_index: int | None = None
        pending_entry_index: int | None = None
        pending_confirmation_index: int | None = None
        rejected_price_confirmation = False
        rejected_guarded_filter = False
        loss_count = sum(1 for trade in completed_trades if trade.return_pct < 0)
        last_trade = completed_trades[-1] if completed_trades else None
        last_loss = last_trade if last_trade is not None and last_trade.return_pct < 0 else None

        if guarded and loss_count > active.guarded_max_losses_before_structural_reset:
            return _EntrySearch(
                found=False,
                state="waiting_oversold",
                reason_code="STOCH_RSI_5M_GUARDED_MAX_LOSSES_REACHED",
                loss_count_before_entry=loss_count,
            )

        for index in current_session_indexes:
            if index < start_index:
                continue
            current_k = k_values[index]
            current_d = d_values[index]
            if current_k is None or current_d is None:
                continue

            if current_k < active.oversold_threshold and active_momentum_cross_index is None:
                if (
                    active_arm_index is None
                    or k_values[active_arm_index] is None
                    or current_k <= k_values[active_arm_index]
                ):
                    active_arm_index = index
                    latest_arm_index = index

            if active_arm_index is None:
                continue

            if active_momentum_cross_index is None:
                if not crossed_up(index):
                    continue
                active_momentum_cross_index = index
                latest_momentum_cross_index = index

            if index > active_momentum_cross_index and current_k <= current_d:
                active_momentum_cross_index = None
                active_arm_index = index if current_k < active.oversold_threshold else None
                if active_arm_index is not None:
                    latest_arm_index = active_arm_index
                continue

            if not recovery_confirmed(index):
                continue

            signal_bar = sampled[index]
            if not _entry_in_window(signal_bar, active):
                continue

            needs_breakout = guarded and active.guarded_require_recovery_high_break
            needs_breakout = needs_breakout or _signal_requires_breakout(signal_bar)
            if not needs_breakout:
                next_index = index + 1
                if next_index >= len(sampled):
                    pending_entry_index = index
                    continue
                next_bar = sampled[next_index]
                if (
                    next_bar.start_time.astimezone(_ET).date() == session_date
                    and _entry_in_window(next_bar, active)
                ):
                    signal_ema = _ema_at(ema_values, index)
                    if signal_ema is None or next_bar.open <= signal_ema:
                        rejected_price_confirmation = True
                        active_arm_index = None
                        active_momentum_cross_index = None
                        continue
                    return _EntrySearch(
                        found=True,
                        state="long_active",
                        reason_code="STOCH_RSI_5M_ENTRY_CONFIRMED",
                        entry_index=next_index,
                        entry_signal_index=index,
                        entry_arm_index=active_arm_index,
                        entry_momentum_cross_index=active_momentum_cross_index,
                    )
                continue

            breakout_index: int | None = None
            breakout_invalidated = False
            for candidate_index in range(index + 1, len(sampled)):
                candidate = sampled[candidate_index]
                if candidate.start_time.astimezone(_ET).date() != session_date:
                    break
                candidate_k = k_values[candidate_index]
                candidate_d = d_values[candidate_index]
                if (
                    candidate_k is None
                    or candidate_d is None
                    or candidate_k < active.recovery_threshold
                    or candidate_k <= candidate_d
                ):
                    rejected_price_confirmation = True
                    breakout_invalidated = True
                    break
                if candidate.close <= signal_bar.high:
                    continue
                breakout_index = candidate_index
                break
            if breakout_invalidated:
                active_arm_index = None
                active_momentum_cross_index = None
                break
            if breakout_index is None:
                pending_confirmation_index = index
                break

            next_index = breakout_index + 1
            if next_index >= len(sampled):
                pending_confirmation_index = index
                break
            next_bar = sampled[next_index]
            if (
                next_bar.start_time.astimezone(_ET).date() != session_date
                or not _entry_in_window(next_bar, active)
            ):
                continue

            signal_ema = _ema_at(ema_values, breakout_index)
            if signal_ema is None or next_bar.open <= signal_ema:
                rejected_price_confirmation = True
                active_arm_index = None
                active_momentum_cross_index = None
                continue

            if not guarded:
                return _EntrySearch(
                    found=True,
                    state="long_active",
                    reason_code="STOCH_RSI_5M_ENTRY_CONFIRMED",
                    entry_index=next_index,
                    entry_signal_index=index,
                    entry_arm_index=active_arm_index,
                    entry_momentum_cross_index=active_momentum_cross_index,
                )

            if last_loss is not None:
                cooldown_until = last_loss.exit_time + timedelta(
                    minutes=active.guarded_loss_cooldown_minutes
                )
                if next_bar.start_time < cooldown_until:
                    rejected_guarded_filter = True
                    active_arm_index = None
                    active_momentum_cross_index = None
                    continue

            slope = ema_slope_pct(breakout_index)
            if active.guarded_require_positive_ema_slope and (slope is None or slope <= 0):
                rejected_guarded_filter = True
                active_arm_index = None
                active_momentum_cross_index = None
                continue

            current_vwap = vwap_at(breakout_index)
            if active.guarded_require_vwap_confirmation and (
                current_vwap is None
                or sampled[breakout_index].close <= current_vwap
                or next_bar.open <= current_vwap
            ):
                rejected_guarded_filter = True
                active_arm_index = None
                active_momentum_cross_index = None
                continue

            volume_ratio = recovery_volume_ratio(active_arm_index, index, breakout_index)
            if (
                active.guarded_min_recovery_volume_ratio > 0
                and (volume_ratio is None or volume_ratio < active.guarded_min_recovery_volume_ratio)
            ):
                rejected_guarded_filter = True
                active_arm_index = None
                active_momentum_cross_index = None
                continue

            reset_required = loss_count >= active.guarded_max_losses_before_structural_reset
            if reset_required and not structural_reset_confirmed(breakout_index):
                rejected_guarded_filter = True
                active_arm_index = None
                active_momentum_cross_index = None
                continue

            stop_price = structural_stop(active_arm_index, breakout_index)
            if stop_price >= next_bar.open:
                rejected_guarded_filter = True
                active_arm_index = None
                active_momentum_cross_index = None
                continue
            initial_risk_pct = (next_bar.open - stop_price) / next_bar.open * Decimal("100")
            if initial_risk_pct > active.guarded_max_initial_risk_pct:
                rejected_guarded_filter = True
                active_arm_index = None
                active_momentum_cross_index = None
                continue

            return _EntrySearch(
                found=True,
                state="long_active",
                reason_code="STOCH_RSI_5M_GUARDED_ENTRY_CONFIRMED",
                entry_index=next_index,
                entry_signal_index=index,
                entry_arm_index=active_arm_index,
                entry_momentum_cross_index=active_momentum_cross_index,
                initial_stop_price=stop_price,
                entry_vwap=current_vwap,
                ema_slope_pct=slope,
                recovery_volume_ratio=volume_ratio,
                loss_count_before_entry=loss_count,
                structural_reset_required=reset_required,
            )

        if pending_entry_index is not None:
            return _EntrySearch(
                found=False,
                state="entry_armed",
                reason_code="STOCH_RSI_5M_RECOVERY_20_CONFIRMED",
                entry_signal_index=pending_entry_index,
                entry_arm_index=active_arm_index,
                entry_momentum_cross_index=active_momentum_cross_index,
                loss_count_before_entry=loss_count,
            )
        if pending_confirmation_index is not None:
            return _EntrySearch(
                found=False,
                state="entry_armed",
                reason_code=(
                    "STOCH_RSI_5M_GUARDED_WAITING_HIGH_BREAK"
                    if guarded
                    else "STOCH_RSI_5M_WAITING_PRICE_CONFIRMATION"
                ),
                entry_signal_index=pending_confirmation_index,
                entry_arm_index=active_arm_index,
                entry_momentum_cross_index=active_momentum_cross_index,
                loss_count_before_entry=loss_count,
            )
        if rejected_guarded_filter:
            return _EntrySearch(
                found=False,
                state="waiting_oversold",
                reason_code="STOCH_RSI_5M_GUARDED_FILTER_REJECTED",
                entry_arm_index=latest_arm_index,
                entry_momentum_cross_index=latest_momentum_cross_index,
                loss_count_before_entry=loss_count,
            )
        if rejected_price_confirmation:
            return _EntrySearch(
                found=False,
                state="waiting_oversold",
                reason_code="STOCH_RSI_5M_PRICE_CONFIRMATION_REJECTED",
                entry_arm_index=latest_arm_index,
                entry_momentum_cross_index=latest_momentum_cross_index,
                loss_count_before_entry=loss_count,
            )
        if active_momentum_cross_index is not None:
            return _EntrySearch(
                found=False,
                state="setup_armed",
                reason_code="STOCH_RSI_5M_WAITING_RECOVERY_20",
                entry_arm_index=active_arm_index,
                entry_momentum_cross_index=active_momentum_cross_index,
                loss_count_before_entry=loss_count,
            )
        if active_arm_index is not None:
            return _EntrySearch(
                found=False,
                state="setup_armed",
                reason_code="STOCH_RSI_5M_WAITING_MOMENTUM_CROSS",
                entry_arm_index=active_arm_index,
                loss_count_before_entry=loss_count,
            )
        return _EntrySearch(
            found=False,
            state="waiting_oversold",
            reason_code="STOCH_RSI_5M_WAITING_OVERSOLD_ARM",
            loss_count_before_entry=loss_count,
        )

    def _exit_search(entry: _EntrySearch) -> _ExitSearch:
        assert entry.entry_index is not None
        for index in range(entry.entry_index, len(sampled)):
            if (
                guarded
                and entry.initial_stop_price is not None
                and sampled[index].close < entry.initial_stop_price
            ):
                next_index = index + 1
                if next_index < len(sampled):
                    next_bar = sampled[next_index]
                    if (
                        next_bar.start_time.astimezone(_ET).date() == session_date
                        and next_bar.start_time.astimezone(_ET).time() <= active.force_flat_et
                    ):
                        return _ExitSearch(
                            state="exited",
                            reason_code="STOCH_RSI_5M_GUARDED_STRUCTURAL_STOP",
                            exit_signal_index=index,
                            exit_index=next_index,
                        )

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
                        return _ExitSearch(
                            state="exited",
                            reason_code="STOCH_RSI_5M_CLOSE_BELOW_50_5M_EMA",
                            exit_signal_index=index,
                            exit_index=next_index,
                        )

            if crossed_down_below_midline(index):
                next_index = index + 1
                if next_index < len(sampled):
                    next_bar = sampled[next_index]
                    if (
                        next_bar.start_time.astimezone(_ET).date() == session_date
                        and next_bar.start_time.astimezone(_ET).time() <= active.force_flat_et
                    ):
                        return _ExitSearch(
                            state="exited",
                            reason_code="STOCH_RSI_5M_CROSS_DOWN_BELOW_80",
                            exit_signal_index=index,
                            exit_index=next_index,
                        )
                if _force_flat_reached(sampled[index], active):
                    return _ExitSearch(
                        state="force_flat",
                        reason_code="STOCH_RSI_5M_FORCE_FLAT",
                        force_flat_index=index,
                    )

            if crossed_down(index):
                next_index = index + 1
                if next_index < len(sampled):
                    next_bar = sampled[next_index]
                    if (
                        next_bar.start_time.astimezone(_ET).date() == session_date
                        and next_bar.start_time.astimezone(_ET).time() <= active.force_flat_et
                    ):
                        return _ExitSearch(
                            state="exited",
                            reason_code="STOCH_RSI_5M_OVERBOUGHT_CROSS_DOWN",
                            exit_signal_index=index,
                            exit_index=next_index,
                        )
                if _force_flat_reached(sampled[index], active):
                    return _ExitSearch(
                        state="force_flat",
                        reason_code="STOCH_RSI_5M_FORCE_FLAT",
                        force_flat_index=index,
                    )

        force_flat_index = next(
            (
                index
                for index in range(entry.entry_index, len(sampled))
                if _force_flat_reached(sampled[index], active)
            ),
            None,
        )
        if force_flat_index is not None:
            return _ExitSearch(
                state="force_flat",
                reason_code="STOCH_RSI_5M_FORCE_FLAT",
                force_flat_index=force_flat_index,
            )

        for index in range(entry.entry_index, len(sampled)):
            if crossed_down_below_midline(index):
                return _ExitSearch(
                    state="exit_armed",
                    reason_code="STOCH_RSI_5M_CROSS_DOWN_BELOW_80",
                )
            if crossed_down(index):
                return _ExitSearch(
                    state="exit_armed",
                    reason_code="STOCH_RSI_5M_OVERBOUGHT_CROSS_DOWN",
                )
        return _ExitSearch(
            state="long_active",
            reason_code="STOCH_RSI_5M_LONG_ACTIVE",
        )

    def _trade_from(entry: _EntrySearch, exit: _ExitSearch) -> StochRsi5mTrade:
        assert entry.entry_index is not None
        assert entry.entry_signal_index is not None
        assert entry.entry_arm_index is not None
        assert entry.entry_momentum_cross_index is not None
        entry_bar = sampled[entry.entry_index]
        if exit.state == "exited":
            assert exit.exit_signal_index is not None
            assert exit.exit_index is not None
            exit_signal_time = sampled[exit.exit_signal_index].end_time
            exit_bar = sampled[exit.exit_index]
            exit_time = exit_bar.start_time
            exit_price = exit_bar.open
        else:
            assert exit.force_flat_index is not None
            exit_signal_time = None
            exit_bar = sampled[exit.force_flat_index]
            exit_time = exit_bar.end_time
            exit_price = exit_bar.close
        return StochRsi5mTrade(
            oversold_arm_time=sampled[entry.entry_arm_index].end_time,
            momentum_cross_time=sampled[entry.entry_momentum_cross_index].end_time,
            entry_signal_time=sampled[entry.entry_signal_index].end_time,
            entry_time=entry_bar.start_time,
            entry_price=entry_bar.open,
            exit_signal_time=exit_signal_time,
            exit_time=exit_time,
            exit_price=exit_price,
            exit_reason_code=exit.reason_code,
            return_pct=(exit_price - entry_bar.open) / entry_bar.open * Decimal("100"),
            initial_stop_price=entry.initial_stop_price,
            entry_vwap=entry.entry_vwap,
            ema_slope_pct=entry.ema_slope_pct,
            recovery_volume_ratio=entry.recovery_volume_ratio,
            loss_count_before_entry=entry.loss_count_before_entry,
            structural_reset_required=entry.structural_reset_required,
        )

    def _snapshot_for_trade(
        trade: StochRsi5mTrade,
        *,
        state: Literal["exited", "force_flat"],
        trades: tuple[StochRsi5mTrade, ...],
    ) -> StochRsi5mSnapshot:
        return _snapshot(
            state=state,
            reason_code=trade.exit_reason_code,
            oversold_arm_time=trade.oversold_arm_time,
            momentum_cross_time=trade.momentum_cross_time,
            entry_signal_time=trade.entry_signal_time,
            entry_time=trade.entry_time,
            entry_price=trade.entry_price,
            exit_signal_time=trade.exit_signal_time,
            exit_time=trade.exit_time,
            exit_price=trade.exit_price,
            return_pct=trade.return_pct,
            trades=trades,
            **common,
        )

    def _snapshot_for_entry_wait(
        search: _EntrySearch,
        trades: tuple[StochRsi5mTrade, ...],
    ) -> StochRsi5mSnapshot:
        return _snapshot(
            state=search.state,
            reason_code=search.reason_code,
            oversold_arm_time=(
                sampled[search.entry_arm_index].end_time
                if search.entry_arm_index is not None
                else None
            ),
            momentum_cross_time=(
                sampled[search.entry_momentum_cross_index].end_time
                if search.entry_momentum_cross_index is not None
                else None
            ),
            entry_signal_time=(
                sampled[search.entry_signal_index].end_time
                if search.entry_signal_index is not None
                else None
            ),
            trades=trades,
            **common,
        )

    completed_trades: list[StochRsi5mTrade] = []
    search_start_index = current_session_indexes[0]
    while True:
        entry = _entry_search(search_start_index, tuple(completed_trades))
        completed = tuple(completed_trades)
        if not entry.found:
            if completed_trades and entry.state == "waiting_oversold":
                # Preserve the explicit guarded lockout reason for diagnostics.
                if guarded and entry.reason_code.startswith("STOCH_RSI_5M_GUARDED_"):
                    return _snapshot_for_entry_wait(entry, completed)
                return _snapshot_for_trade(
                    completed_trades[-1],
                    state="exited",
                    trades=completed,
                )
            return _snapshot_for_entry_wait(entry, completed)

        assert entry.entry_index is not None
        exit = _exit_search(entry)
        entry_bar = sampled[entry.entry_index]
        assert entry.entry_signal_index is not None
        assert entry.entry_arm_index is not None
        assert entry.entry_momentum_cross_index is not None
        entry_signal_bar = sampled[entry.entry_signal_index]
        entry_evidence = {
            "oversold_arm_time": sampled[entry.entry_arm_index].end_time,
            "momentum_cross_time": sampled[entry.entry_momentum_cross_index].end_time,
        }
        if exit.state in {"exited", "force_flat"}:
            trade = _trade_from(entry, exit)
            completed_trades.append(trade)
            if exit.state == "force_flat":
                return _snapshot_for_trade(
                    trade,
                    state="force_flat",
                    trades=tuple(completed_trades),
                )
            assert exit.exit_index is not None
            search_start_index = exit.exit_index + 1
            if not any(index >= search_start_index for index in current_session_indexes):
                return _snapshot_for_trade(
                    trade,
                    state="exited",
                    trades=tuple(completed_trades),
                )
            continue

        if exit.state == "exit_armed":
            return _snapshot(
                state="exit_armed",
                reason_code=exit.reason_code,
                entry_signal_time=entry_signal_bar.end_time,
                entry_time=entry_bar.start_time,
                entry_price=entry_bar.open,
                trades=completed,
                **entry_evidence,
                **common,
            )
        return _snapshot(
            state="long_active",
            reason_code=(
                "STOCH_RSI_5M_GUARDED_LONG_ACTIVE"
                if guarded
                else "STOCH_RSI_5M_LONG_ACTIVE"
            ),
            entry_signal_time=entry_signal_bar.end_time,
            entry_time=entry_bar.start_time,
            entry_price=entry_bar.open,
            trades=completed,
            **entry_evidence,
            **common,
        )


__all__ = [
    "StochRsi5mPolicyVersion",
    "StochRsi5mSnapshot",
    "StochRsi5mState",
    "StochRsi5mTrade",
    "evaluate_stoch_rsi_5m",
]
