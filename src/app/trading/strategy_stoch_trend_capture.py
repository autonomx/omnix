from __future__ import annotations

"""Research-only 3-minute Stoch-RSI trend-capture strategy.

The policy is intentionally separate from AUTO PAPER authority. It uses only
finalized causal bars and produces a replay/snapshot that the strategy monitor
can persist as SHADOW evidence.

Policy:
- first regular-session 3m Stoch RSI K/D <= 20 arms the only trade of the day;
- enter at the next 3m bar open;
- if price never proves an uptrend, exit the whole position at the first later
  K/D >= 80 reading (next 3m bar open);
- if price proves trend mode first, overbought is strength rather than an exit:
  take 25% at the first later overbought reading and keep 75% as a runner;
- exit the runner only after a causal trend break or the 15:55 ET force-flat;
- live execution eligibility/halt/spread checks are a separate fail-closed veto.
"""

from datetime import datetime, time
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from .indicator_signals import _ema_aligned, _stochastic_rsi_aligned
from .models import MarketBar
from .strategies.gap_pullback import session_vwap
from .strategy_timeframes import resample_final_bars


_ET = ZoneInfo("America/New_York")
OVERSOLD = Decimal("20")
OVERBOUGHT = Decimal("80")
PARTIAL_FRACTION = Decimal("0.25")

TrendCaptureState = Literal[
    "waiting_oversold",
    "entry_armed",
    "range_active",
    "range_exit_armed",
    "range_exited",
    "trend_active",
    "trend_partial_armed",
    "trend_runner",
    "trend_exit_armed",
    "trend_exited",
    "force_flat",
]


class StochTrendCaptureSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal["stoch-trend-capture-v1"] = "stoch-trend-capture-v1"
    state: TrendCaptureState
    reason_code: str
    three_minute_bar_count: int
    entry_signal_time: datetime | None = None
    entry_time: datetime | None = None
    entry_price: Decimal | None = None
    trend_confirmed_time: datetime | None = None
    first_overbought_time: datetime | None = None
    partial_exit_time: datetime | None = None
    partial_exit_price: Decimal | None = None
    partial_fraction: Decimal = PARTIAL_FRACTION
    runner_exit_time: datetime | None = None
    runner_exit_price: Decimal | None = None
    trailing_higher_low: Decimal | None = None
    combined_exit_price: Decimal | None = None
    return_pct: Decimal | None = None
    stochastic_rsi_k: Decimal | None = None
    stochastic_rsi_d: Decimal | None = None
    execution_authority: Literal[False] = False


class StochTrendRiskDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: bool
    reason_codes: tuple[str, ...] = ()


def stoch_trend_capture_risk_decision(
    execution: dict[str, object],
    *,
    max_spread_bps: Decimal,
) -> StochTrendRiskDecision:
    """Fail closed on authoritative live execution defects at the entry signal."""

    reasons: list[str] = []
    if execution.get("halted") is True:
        reasons.append("STOCH_TREND_HALTED")
    if execution.get("execution_eligible") is not True:
        reasons.append("STOCH_TREND_EXECUTION_INELIGIBLE")
    spread_raw = execution.get("spread_bps")
    if spread_raw is not None:
        try:
            spread = Decimal(str(spread_raw))
        except Exception:
            reasons.append("STOCH_TREND_SPREAD_INVALID")
        else:
            if spread > max_spread_bps:
                reasons.append("STOCH_TREND_SPREAD_TOO_WIDE")
    return StochTrendRiskDecision(allowed=not reasons, reason_codes=tuple(dict.fromkeys(reasons)))


def _same_et_day(bars: list[MarketBar] | tuple[MarketBar, ...]) -> list[MarketBar]:
    finalized = sorted((bar for bar in bars if bar.is_final), key=lambda bar: bar.start_time)
    if not finalized:
        return []
    session_date = finalized[-1].start_time.astimezone(_ET).date()
    return [
        bar
        for bar in finalized
        if bar.start_time.astimezone(_ET).date() == session_date
    ]


def _regular_positions(bars: list[MarketBar]) -> list[int]:
    return [index for index, bar in enumerate(bars) if bar.session == "regular"]


def _next_regular_index(bars: list[MarketBar], after_index: int) -> int | None:
    for index in range(after_index + 1, len(bars)):
        if bars[index].session == "regular":
            return index
    return None


def _regular_prefix(bars: list[MarketBar], through_index: int) -> list[MarketBar]:
    return [
        bar
        for index, bar in enumerate(bars)
        if index <= through_index and bar.session == "regular"
    ]


def _trend_confirmed(
    bars: list[MarketBar],
    ema9: list[Decimal | None],
    *,
    entry_index: int,
    index: int,
) -> bool:
    if index <= entry_index:
        return False
    current_ema = ema9[index]
    prior_ema = ema9[index - 1] if index > 0 else None
    if current_ema is None or prior_ema is None:
        return False
    current = bars[index]
    if current.session != "regular":
        return False

    recent = [
        bar
        for bar in bars[entry_index : index + 1]
        if bar.session == "regular"
    ][-4:]
    if len(recent) < 3:
        return False
    rising_low_pairs = sum(
        1
        for left, right in zip(recent, recent[1:])
        if right.low > left.low
    )
    if rising_low_pairs < 2:
        return False

    vwap = session_vwap(_regular_prefix(bars, index))
    return (
        current.close > current_ema
        and current_ema > prior_ema
        and vwap is not None
        and current.close >= vwap
    )


def _latest_confirmed_pivot_low(
    bars: list[MarketBar],
    *,
    entry_index: int,
    through_index: int,
) -> Decimal | None:
    latest: Decimal | None = None
    start = max(entry_index + 1, 1)
    for index in range(start, min(through_index, len(bars) - 1)):
        left, current, right = bars[index - 1], bars[index], bars[index + 1]
        if current.session != "regular" or left.session != "regular" or right.session != "regular":
            continue
        if current.low <= left.low and current.low < right.low:
            latest = current.low
    return latest


def _trend_break(
    bars: list[MarketBar],
    ema9: list[Decimal | None],
    *,
    entry_index: int,
    index: int,
) -> tuple[bool, Decimal | None]:
    if index <= entry_index or bars[index].session != "regular":
        return False, None
    current_ema = ema9[index]
    prior_ema = ema9[index - 1] if index > 0 else None
    if current_ema is None or prior_ema is None:
        return False, None
    ema_falling = current_ema < prior_ema
    current = bars[index]
    trailing_low = _latest_confirmed_pivot_low(
        bars,
        entry_index=entry_index,
        through_index=index,
    )

    pivot_break = (
        trailing_low is not None
        and current.close < trailing_low
        and current.close < current_ema
        and ema_falling
    )

    prior_regular_index = next(
        (
            candidate
            for candidate in range(index - 1, entry_index - 1, -1)
            if bars[candidate].session == "regular"
        ),
        None,
    )
    two_below_ema = False
    if prior_regular_index is not None:
        prior_bar_ema = ema9[prior_regular_index]
        two_below_ema = (
            prior_bar_ema is not None
            and bars[prior_regular_index].close < prior_bar_ema
            and current.close < current_ema
            and ema_falling
        )
    vwap = session_vwap(_regular_prefix(bars, index))
    ema_vwap_break = (
        two_below_ema
        and vwap is not None
        and current.close < vwap
    )
    return pivot_break or ema_vwap_break, trailing_low


def _first_force_flat_index(
    bars: list[MarketBar],
    *,
    start_index: int,
    force_flat_et: time,
) -> int | None:
    """Return the first finalized 3m bar whose end crosses the cutoff.

    Using the containing bar's *open* would reference a price from before the
    configured cutoff (for example 15:54 for a 15:55 force-flat). The bar close
    is the first causal finalized 3m price available after the cutoff.
    """

    return next(
        (
            index
            for index in range(start_index, len(bars))
            if bars[index].session == "regular"
            and bars[index].end_time.astimezone(_ET).time() >= force_flat_et
        ),
        None,
    )


def _weighted_return(
    entry: Decimal,
    *,
    partial_price: Decimal | None,
    runner_price: Decimal,
) -> tuple[Decimal, Decimal]:
    combined = (
        runner_price
        if partial_price is None
        else partial_price * PARTIAL_FRACTION + runner_price * (Decimal("1") - PARTIAL_FRACTION)
    )
    return combined, (combined / entry - Decimal("1")) * Decimal("100")


def evaluate_stoch_trend_capture(
    bars: list[MarketBar] | tuple[MarketBar, ...],
    *,
    entry_start_et: time = time(9, 35),
    last_entry_et: time = time(11, 30),
    force_flat_et: time = time(15, 55),
) -> StochTrendCaptureSnapshot:
    """Replay the single-trade policy causally over the available same-day tape."""

    same_day = _same_et_day(bars)
    sampled = list(resample_final_bars(same_day, "3m")) if same_day else []
    if not sampled:
        return StochTrendCaptureSnapshot(
            state="waiting_oversold",
            reason_code="STOCH_TREND_WAITING_FOR_3M_BARS",
            three_minute_bar_count=0,
        )

    closes = [bar.close for bar in sampled]
    ema9 = _ema_aligned(closes, 9)
    stoch_k, stoch_d = _stochastic_rsi_aligned(closes)

    signal_index: int | None = None
    for index in _regular_positions(sampled):
        signal_time = sampled[index].end_time.astimezone(_ET).time()
        if signal_time < entry_start_et or signal_time > last_entry_et:
            continue
        k = stoch_k[index]
        d = stoch_d[index]
        if k is not None and d is not None and k <= OVERSOLD and d <= OVERSOLD:
            signal_index = index
            break

    last_index = len(sampled) - 1
    last_k = stoch_k[last_index]
    last_d = stoch_d[last_index]
    if signal_index is None:
        return StochTrendCaptureSnapshot(
            state="waiting_oversold",
            reason_code="STOCH_TREND_NO_OVERSOLD_SIGNAL",
            three_minute_bar_count=len(sampled),
            stochastic_rsi_k=last_k,
            stochastic_rsi_d=last_d,
        )

    signal_bar = sampled[signal_index]
    entry_index = _next_regular_index(sampled, signal_index)
    if entry_index is None:
        return StochTrendCaptureSnapshot(
            state="entry_armed",
            reason_code="STOCH_TREND_FIRST_OVERSOLD_ARMED",
            three_minute_bar_count=len(sampled),
            entry_signal_time=signal_bar.end_time,
            stochastic_rsi_k=stoch_k[signal_index],
            stochastic_rsi_d=stoch_d[signal_index],
        )

    entry_bar = sampled[entry_index]
    entry_price = entry_bar.open
    trend_index: int | None = None
    overbought_index: int | None = None
    for index in range(entry_index, len(sampled)):
        if sampled[index].session != "regular":
            continue
        if trend_index is None and _trend_confirmed(
            sampled,
            ema9,
            entry_index=entry_index,
            index=index,
        ):
            trend_index = index
        if overbought_index is None:
            k = stoch_k[index]
            d = stoch_d[index]
            if k is not None and d is not None and k >= OVERBOUGHT and d >= OVERBOUGHT:
                overbought_index = index

    base = dict(
        three_minute_bar_count=len(sampled),
        entry_signal_time=signal_bar.end_time,
        entry_time=entry_bar.start_time,
        entry_price=entry_price,
        trend_confirmed_time=(sampled[trend_index].end_time if trend_index is not None else None),
        first_overbought_time=(
            sampled[overbought_index].end_time if overbought_index is not None else None
        ),
        stochastic_rsi_k=last_k,
        stochastic_rsi_d=last_d,
    )

    # Range/rebound mode: overbought is the exit because trend mode did not
    # prove itself before the oscillator reached the first extreme.
    if overbought_index is not None and (trend_index is None or overbought_index < trend_index):
        exit_index = _next_regular_index(sampled, overbought_index)
        if exit_index is None:
            return StochTrendCaptureSnapshot(
                state="range_exit_armed",
                reason_code="STOCH_TREND_RANGE_OVERBOUGHT_EXIT_ARMED",
                **base,
            )
        exit_bar = sampled[exit_index]
        return_pct = (exit_bar.open / entry_price - Decimal("1")) * Decimal("100")
        return StochTrendCaptureSnapshot(
            state="range_exited",
            reason_code="STOCH_TREND_RANGE_OVERBOUGHT_EXIT",
            runner_exit_time=exit_bar.start_time,
            runner_exit_price=exit_bar.open,
            combined_exit_price=exit_bar.open,
            return_pct=return_pct,
            **base,
        )

    if trend_index is None:
        force_index = _first_force_flat_index(
            sampled,
            start_index=entry_index,
            force_flat_et=force_flat_et,
        )
        if force_index is not None:
            exit_bar = sampled[force_index]
            return_pct = (exit_bar.close / entry_price - Decimal("1")) * Decimal("100")
            return StochTrendCaptureSnapshot(
                state="force_flat",
                reason_code="STOCH_TREND_RANGE_FORCE_FLAT",
                runner_exit_time=exit_bar.end_time,
                runner_exit_price=exit_bar.close,
                combined_exit_price=exit_bar.close,
                return_pct=return_pct,
                **base,
            )
        return StochTrendCaptureSnapshot(
            state="range_active",
            reason_code="STOCH_TREND_RANGE_WAITING_FOR_TREND_OR_OVERBOUGHT",
            **base,
        )

    partial_time: datetime | None = None
    partial_price: Decimal | None = None
    runner_start = trend_index
    if overbought_index is not None and overbought_index >= trend_index:
        partial_index = _next_regular_index(sampled, overbought_index)
        if partial_index is None:
            return StochTrendCaptureSnapshot(
                state="trend_partial_armed",
                reason_code="STOCH_TREND_OVERBOUGHT_PARTIAL_ARMED",
                **base,
            )
        partial_time = sampled[partial_index].start_time
        partial_price = sampled[partial_index].open
        runner_start = partial_index

    trailing_low: Decimal | None = None
    for index in range(max(runner_start, entry_index + 1), len(sampled)):
        if sampled[index].session != "regular":
            continue
        et_end = sampled[index].end_time.astimezone(_ET).time()
        if et_end >= force_flat_et:
            combined, return_pct = _weighted_return(
                entry_price,
                partial_price=partial_price,
                runner_price=sampled[index].close,
            )
            return StochTrendCaptureSnapshot(
                state="force_flat",
                reason_code="STOCH_TREND_FORCE_FLAT",
                partial_exit_time=partial_time,
                partial_exit_price=partial_price,
                runner_exit_time=sampled[index].end_time,
                runner_exit_price=sampled[index].close,
                trailing_higher_low=trailing_low,
                combined_exit_price=combined,
                return_pct=return_pct,
                **base,
            )

        broken, latest_low = _trend_break(
            sampled,
            ema9,
            entry_index=entry_index,
            index=index,
        )
        if latest_low is not None:
            trailing_low = latest_low
        if not broken:
            continue
        exit_index = _next_regular_index(sampled, index)
        if exit_index is None:
            return StochTrendCaptureSnapshot(
                state="trend_exit_armed",
                reason_code="STOCH_TREND_BREAK_EXIT_ARMED",
                partial_exit_time=partial_time,
                partial_exit_price=partial_price,
                trailing_higher_low=trailing_low,
                **base,
            )
        exit_bar = sampled[exit_index]
        combined, return_pct = _weighted_return(
            entry_price,
            partial_price=partial_price,
            runner_price=exit_bar.open,
        )
        return StochTrendCaptureSnapshot(
            state="trend_exited",
            reason_code="STOCH_TREND_BREAK_EXIT",
            partial_exit_time=partial_time,
            partial_exit_price=partial_price,
            runner_exit_time=exit_bar.start_time,
            runner_exit_price=exit_bar.open,
            trailing_higher_low=trailing_low,
            combined_exit_price=combined,
            return_pct=return_pct,
            **base,
        )

    return StochTrendCaptureSnapshot(
        state="trend_runner" if partial_price is not None else "trend_active",
        reason_code=(
            "STOCH_TREND_RUNNER_ACTIVE"
            if partial_price is not None
            else "STOCH_TREND_CONFIRMED"
        ),
        partial_exit_time=partial_time,
        partial_exit_price=partial_price,
        trailing_higher_low=trailing_low,
        **base,
    )


__all__ = [
    "OVERBOUGHT",
    "OVERSOLD",
    "PARTIAL_FRACTION",
    "StochTrendCaptureSnapshot",
    "StochTrendRiskDecision",
    "evaluate_stoch_trend_capture",
    "stoch_trend_capture_risk_decision",
]
