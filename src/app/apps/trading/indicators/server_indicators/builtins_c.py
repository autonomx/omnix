"""Server ports of the chart's built-in indicators, batch C: the TVP-6.1 quick wins.

Each function mirrors one branch of ``calculateTradingViewBuiltInOutputs`` in ``tradingViewBuiltIns.ts``
operation for operation; the TypeScript helpers state each indicator's definition. Sessions are UTC days of
the bar start time and times are epoch milliseconds, as in the browser.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ..registry import BarSeries
from ._helpers import (
    Chart,
    MaybeNumber,
    Outputs,
    Values,
    builtin,
    builtin_with_compare_series,
    dmi,
    ema,
    finite,
    full,
    highest,
    js_div,
    js_max,
    js_min,
    js_sqrt,
    lowest,
    rsi,
    stochastic,
)

DAY_MS = 86_400_000
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MILLISECOND = timedelta(milliseconds=1)


def _epoch_ms(start_time: datetime) -> int:
    # Date.parse of the API's UTC ISO string; a naive time is taken as UTC.
    moment = start_time if start_time.tzinfo is not None else start_time.replace(tzinfo=UTC)
    return (moment - _EPOCH) // _MILLISECOND


def _start_times(bars: BarSeries) -> list[int]:
    return [_epoch_ms(start_time) for start_time in bars.start_times]


@dataclass
class _PivotLevels:
    pp: list[MaybeNumber]
    r1: list[MaybeNumber]
    r2: list[MaybeNumber]
    r3: list[MaybeNumber]
    s1: list[MaybeNumber]
    s2: list[MaybeNumber]
    s3: list[MaybeNumber]


def _session_pivots(times: Sequence[int], high: Values, low: Values, close: Values, developing: bool) -> _PivotLevels:
    length = len(close)
    levels = _PivotLevels(full(length), full(length), full(length), full(length), full(length), full(length), full(length))
    day = 0
    started = False
    h = low_ = c = 0.0
    previous: tuple[float, float, float] | None = None
    for i in range(length):
        bar_day = times[i] // DAY_MS
        if not started or bar_day != day:
            if started:
                previous = (h, low_, c)
            started = True
            day = bar_day
            h, low_, c = high[i], low[i], close[i]
        else:
            h = js_max(h, high[i])
            low_ = js_min(low_, low[i])
            c = close[i]
        source = (h, low_, c) if developing else previous
        if source is None:
            continue
        sh, sl, sc = source
        pp = (sh + sl + sc) / 3
        levels.pp[i] = pp
        levels.r1[i] = 2 * pp - sl
        levels.s1[i] = 2 * pp - sh
        levels.r2[i] = pp + (sh - sl)
        levels.s2[i] = pp - (sh - sl)
        levels.r3[i] = sh + 2 * (pp - sl)
        levels.s3[i] = sl - 2 * (sh - pp)
    return levels


def _missed_pivots(
    times: Sequence[int], high: Values, low: Values, close: Values, sessions_back: int
) -> tuple[list[MaybeNumber], list[MaybeNumber]]:
    above = full(len(close))
    below = full(len(close))
    pending: list[tuple[float, int]] = []
    day = 0
    session = -1
    h = low_ = c = 0.0
    for i in range(len(close)):
        bar_day = times[i] // DAY_MS
        if session < 0 or bar_day != day:
            if session >= 0:
                pending.append(((h + low_ + c) / 3, session + 1))
            session += 1
            day = bar_day
            h, low_, c = high[i], low[i], close[i]
        else:
            h = js_max(h, high[i])
            low_ = js_min(low_, low[i])
            c = close[i]
        pending = [
            (value, level_session)
            for value, level_session in pending
            if level_session >= session - sessions_back and not (low[i] <= value <= high[i])
        ]
        up: MaybeNumber = None
        down: MaybeNumber = None
        for value, level_session in pending:
            if level_session >= session:
                continue
            if value > close[i] and (up is None or value < up):
                up = value
            if value < close[i] and (down is None or value > down):
                down = value
        above[i] = up
        below[i] = down
    return above, below


def _relative_volume_at_time(times: Sequence[int], volume: Values, sessions: int) -> list[MaybeNumber]:
    result = full(len(volume))
    history: dict[int, list[float]] = {}
    day = 0
    cumulative = 0.0
    for i in range(len(volume)):
        bar_day = times[i] // DAY_MS
        if i == 0 or bar_day != day:
            day = bar_day
            cumulative = 0.0
        cumulative += volume[i]
        past = history.setdefault(times[i] - bar_day * DAY_MS, [])
        if len(past) >= sessions:
            total = 0.0
            for k in range(len(past) - sessions, len(past)):
                total += past[k]
            average = total / sessions
            if average != 0:
                result[i] = cumulative / average
        past.append(cumulative)
    return result


def _rolling_day_volume(times: Sequence[int], volume: Values) -> list[MaybeNumber]:
    result = full(len(volume))
    step: float = math.inf
    for i in range(1, len(times)):
        gap = times[i] - times[i - 1]
        if 0 < gap < step:
            step = gap
    covered = min(step, DAY_MS)
    left = 0
    running = 0.0
    for i in range(len(volume)):
        running += volume[i]
        while left < i and times[left] <= times[i] - DAY_MS:
            running -= volume[left]
            left += 1
        if times[0] <= times[i] - DAY_MS + covered:
            result[i] = running
    return result


def _aligned_compare_closes(times: Sequence[int], compare: BarSeries) -> list[MaybeNumber]:
    # A stable sort by start time, like the browser's Array.prototype.sort.
    series = sorted(zip(_start_times(compare), compare.close, strict=True), key=lambda item: item[0])
    j = -1
    result: list[MaybeNumber] = []
    for time in times:
        while j + 1 < len(series) and series[j + 1][0] <= time:
            j += 1
        result.append(series[j][1] if j >= 0 else None)
    return result


def _pearson(x: Values, y: Sequence[MaybeNumber], period: int) -> list[MaybeNumber]:
    result = full(len(x))
    for i in range(period - 1, len(x)):
        start = i - period + 1
        ys = [value for value in y[start : i + 1] if value is not None]
        if len(ys) < period:
            continue
        sx = 0.0
        sy = 0.0
        for j in range(period):
            sx += x[start + j]
            sy += ys[j]
        mx = sx / period
        my = sy / period
        sxx = syy = sxy = 0.0
        for j in range(period):
            dx = x[start + j] - mx
            dy = ys[j] - my
            sxx += dx * dx
            syy += dy * dy
            sxy += dx * dy
        result[i] = None if sxx == 0 or syy == 0 else js_div(sxy, js_sqrt(sxx * syy))
    return result


def _knoxville_divergence(high: Values, low: Values, close: Values, lookback: int) -> tuple[list[MaybeNumber], list[MaybeNumber]]:
    bearish = full(len(close))
    bullish = full(len(close))
    momentum: list[MaybeNumber] = [value - close[i - 20] if i >= 20 else None for i, value in enumerate(close)]
    overbought: list[int] = []
    oversold: list[int] = []
    for i, value in enumerate(rsi(close, 21)):
        overbought.append((overbought[i - 1] if i > 0 else 0) + (1 if finite(value) and value > 70 else 0))
        oversold.append((oversold[i - 1] if i > 0 else 0) + (1 if finite(value) and value < 30 else 0))

    def flagged(counts: list[int], start: int, end: int) -> bool:
        return counts[end] - (counts[start - 1] if start > 0 else 0) > 0

    highs: deque[int] = deque()
    lows: deque[int] = deque()
    for i in range(1, len(close)):
        while highs and high[highs[-1]] <= high[i - 1]:
            highs.pop()
        highs.append(i - 1)
        while lows and low[lows[-1]] >= low[i - 1]:
            lows.pop()
        lows.append(i - 1)
        while highs[0] < i - lookback:
            highs.popleft()
        while lows[0] < i - lookback:
            lows.popleft()
        now = momentum[i]
        if now is None:
            continue
        h = highs[0]
        lo = lows[0]
        at_high = momentum[h]
        at_low = momentum[lo]
        if high[i] > high[h] and at_high is not None and now < at_high and flagged(overbought, h, i):
            bearish[i] = high[i]
        if low[i] < low[lo] and at_low is not None and now > at_low and flagged(oversold, lo, i):
            bullish[i] = low[i]
    return bearish, bullish


@builtin("tv-24-hour-volume", "24-hour Volume", "exact", 1)
def _volume_24_hours(chart: Chart) -> Outputs:
    return [chart.out("volume-24h", _rolling_day_volume(_start_times(chart.bars), chart.volume))]


@builtin_with_compare_series("tv-correlation-coefficient-cc", "Correlation Coefficient (CC)", "exact", 20)
def _correlation_coefficient(chart: Chart) -> Outputs:
    compare = (
        _aligned_compare_closes(_start_times(chart.bars), chart.compare)
        if chart.compare is not None and len(chart.compare) > 0
        else full(len(chart.bars))
    )
    return [chart.out("cc", _pearson(chart.close, compare, chart.period))]


@builtin("tv-relative-volume-at-time", "Relative Volume at Time", "exact", 10)
def _relative_volume_at_time_builtin(chart: Chart) -> Outputs:
    return [chart.out("rvol-at-time", _relative_volume_at_time(_start_times(chart.bars), chart.volume, chart.period))]


@builtin("tv-rob-booker-adx-breakout", "Rob Booker - ADX Breakout", "recursive", 14)
def _adx_breakout(chart: Chart) -> Outputs:
    _, _, adx = dmi(chart.high, chart.low, chart.close, chart.period)
    hh = highest(chart.high, chart.period)
    ll = lowest(chart.low, chart.period)
    upper = full(len(chart.bars))
    lower = full(len(chart.bars))
    top: MaybeNumber = None
    bottom: MaybeNumber = None
    for i in range(len(chart.bars)):
        strength = adx[i]
        if finite(strength) and strength < 18 and finite(hh[i]) and finite(ll[i]):
            top = hh[i]
            bottom = ll[i]
        upper[i] = top
        lower[i] = bottom
    return [chart.out("upper", upper), chart.out("lower", lower)]


@builtin("tv-rob-booker-knoxville-divergence", "Rob Booker - Knoxville Divergence", "recursive", 150)
def _knoxville(chart: Chart) -> Outputs:
    bearish, bullish = _knoxville_divergence(chart.high, chart.low, chart.close, chart.period)
    return [chart.out("bearish", bearish), chart.out("bullish", bullish)]


@builtin("tv-rob-booker-intraday-pivot-points", "Rob Booker Intraday Pivot Points", "exact", 1)
def _intraday_pivots(chart: Chart) -> Outputs:
    levels = _session_pivots(_start_times(chart.bars), chart.high, chart.low, chart.close, developing=False)
    return [
        chart.out("pp", levels.pp),
        chart.out("r1", levels.r1),
        chart.out("r2", levels.r2),
        chart.out("r3", levels.r3),
        chart.out("s1", levels.s1),
        chart.out("s2", levels.s2),
        chart.out("s3", levels.s3),
    ]


@builtin("tv-rob-booker-missed-pivot-points", "Rob Booker Missed Pivot Points", "exact", 10)
def _missed_pivot_points(chart: Chart) -> Outputs:
    above, below = _missed_pivots(_start_times(chart.bars), chart.high, chart.low, chart.close, chart.period)
    return [chart.out("missed-above", above), chart.out("missed-below", below)]


@builtin("tv-rob-booker-reversal", "Rob Booker Reversal", "recursive", 14)
def _reversal(chart: Chart) -> Outputs:
    close, high, low = chart.close, chart.high, chart.low
    fast = ema(close, 12)
    slow = ema(close, 26)
    k = stochastic(high, low, close, chart.period)
    macd = [f - s if finite(f) and finite(s) else None for f, s in zip(fast, slow, strict=True)]
    bullish = full(len(close))
    bearish = full(len(close))
    for i in range(2, len(close)):
        now, before, earlier, stoch = macd[i], macd[i - 1], macd[i - 2], k[i]
        if now is None or before is None or earlier is None or not finite(stoch):
            continue
        if now > before and before <= earlier and stoch < 30:
            bullish[i] = low[i]
        if now < before and before >= earlier and stoch > 70:
            bearish[i] = high[i]
    return [chart.out("bullish", bullish), chart.out("bearish", bearish)]


@builtin("tv-rob-booker-ziv-ghost-pivots", "Rob Booker Ziv Ghost Pivots", "exact", 1)
def _ziv_ghost_pivots(chart: Chart) -> Outputs:
    levels = _session_pivots(_start_times(chart.bars), chart.high, chart.low, chart.close, developing=True)
    return [chart.out("pp", levels.pp), chart.out("r1", levels.r1), chart.out("s1", levels.s1)]
