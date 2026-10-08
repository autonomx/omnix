"""Server ports of the chart's built-in indicators (``tradingViewBuiltIns.ts``), batch B.

Each function follows its branch of ``calculateTradingViewBuiltInOutputs`` operation
for operation, so results match the browser goldens bit for bit where possible.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC
from typing import Literal

from ..registry import BarSeries, IndicatorInputs, IndicatorOutputSeries, NumericClass, register
from ._helpers import (
    EPSILON,
    MaybeNumber,
    Values,
    atr,
    correlation_with_index,
    dmi,
    ema,
    finite,
    full,
    highest,
    hl2,
    js_max,
    js_min,
    js_sqrt,
    js_sum,
    lowest,
    mean,
    output,
    rma,
    roc,
    rolling_sum,
    rsi,
    safe_period,
    sma,
    spearman,
    stdev,
    true_range,
    typical_price,
    wma,
)

BuiltInCompute = Callable[[BarSeries, IndicatorInputs, int], list[IndicatorOutputSeries]]


def _builtin(
    indicator_id: str, name: str, numeric_class: NumericClass, default_period: int
) -> Callable[[BuiltInCompute], BuiltInCompute]:
    """Registers a branch with the browser's preamble: no bars gives no outputs, and the period falls back to the default."""

    def decorate(compute: BuiltInCompute) -> BuiltInCompute:
        @register(indicator_id, name, numeric_class)
        def run(bars: BarSeries, inputs: IndicatorInputs) -> list[IndicatorOutputSeries]:
            if len(bars) == 0:
                return []
            return compute(bars, inputs, _js_period(inputs.period, default_period))

        return compute

    return decorate


def _js_period(period: object, fallback: int = 14) -> int:
    """``safePeriod``: JavaScript's ``Number.isInteger`` also accepts integral floats such as ``20.0``."""
    if isinstance(period, float) and period.is_integer():
        return safe_period(int(period), fallback)
    return safe_period(period, fallback)


def _or_zero(values: Sequence[MaybeNumber]) -> list[float]:
    return [value if value is not None and math.isfinite(value) else 0.0 for value in values]


def _js_sign(value: float) -> float:
    if value > 0:
        return 1.0
    if value < 0:
        return -1.0
    return value


def _js_round(value: float) -> int:
    floor = math.floor(value)
    return floor + 1 if value - floor >= 0.5 else floor


def _stochastic(high: Values, low: Values, close: Values, period: int) -> list[MaybeNumber]:
    hh = highest(high, period)
    ll = lowest(low, period)
    result: list[MaybeNumber] = []
    for value, h, lo in zip(close, hh, ll, strict=True):
        if h is not None and lo is not None and finite(h) and finite(lo) and h != lo:
            result.append(100 * (value - lo) / (h - lo))
        else:
            result.append(None)
    return result


def _money_flow_index(high: Values, low: Values, close: Values, volume: Values, period: int) -> list[MaybeNumber]:
    p = safe_period(period)
    typical = [(high[i] + low[i] + value) / 3 for i, value in enumerate(close)]
    positive = [value * volume[i] if i > 0 and value > typical[i - 1] else 0.0 for i, value in enumerate(typical)]
    negative = [value * volume[i] if i > 0 and value < typical[i - 1] else 0.0 for i, value in enumerate(typical)]
    positive_sum = rolling_sum(positive, p)
    negative_sum = rolling_sum(negative, p)
    result: list[MaybeNumber] = []
    for ps, ns in zip(positive_sum, negative_sum, strict=True):
        if ps is None or ns is None or not finite(ps) or not finite(ns):
            result.append(None)
        elif ns == 0:
            result.append(100.0)
        else:
            result.append(100 - 100 / (1 + ps / ns))
    return result


def _stochastic_momentum(high: Values, low: Values, close: Values, period: int) -> list[MaybeNumber]:
    hh = highest(high, period)
    ll = lowest(low, period)
    midpoint_delta: list[float] = []
    spread: list[float] = []
    for value, h, lo in zip(close, hh, ll, strict=True):
        ok = h is not None and lo is not None and finite(h) and finite(lo)
        midpoint_delta.append(value - (h + lo) / 2 if ok and h is not None and lo is not None else 0.0)
        spread.append(h - lo if ok and h is not None and lo is not None else 0.0)
    numerator = ema(_or_zero(ema(midpoint_delta, 3)), 3)
    denominator = ema(_or_zero(ema(spread, 3)), 3)
    result: list[MaybeNumber] = []
    for n, d in zip(numerator, denominator, strict=True):
        result.append(200 * n / d if n is not None and d is not None and finite(n) and finite(d) and d != 0 else None)
    return result


def _cci(high: Values, low: Values, close: Values, period: int) -> list[MaybeNumber]:
    typical = [(high[i] + low[i] + value) / 3 for i, value in enumerate(close)]
    basis = sma(typical, period)
    p = safe_period(period)
    result: list[MaybeNumber] = []
    for i, b in enumerate(basis):
        if b is None or not finite(b):
            result.append(None)
            continue
        window = typical[i - p + 1 : i + 1]
        deviation = mean([abs(value - b) for value in window])
        result.append(0.0 if deviation == 0 else (typical[i] - b) / (0.015 * deviation))
    return result


def _true_strength(close: Values, long_period: int = 25, short_period: int = 13) -> list[MaybeNumber]:
    momentum = [0.0 if i == 0 else value - close[i - 1] for i, value in enumerate(close)]
    absolute = [abs(value) for value in momentum]
    second = ema(_or_zero(ema(momentum, long_period)), short_period)
    absolute_second = ema(_or_zero(ema(absolute, long_period)), short_period)
    result: list[MaybeNumber] = []
    for s, a in zip(second, absolute_second, strict=True):
        result.append(100 * s / a if s is not None and a is not None and finite(s) and finite(a) and a != 0 else None)
    return result


def _parabolic_sar(high: Values, low: Values) -> list[MaybeNumber]:
    result = full(len(high))
    if len(high) < 2:
        return result
    up = True
    af = 0.02
    ep = high[0]
    sar = low[0]
    result[0] = sar
    for i in range(1, len(high)):
        sar += af * (ep - sar)
        if up:
            sar = js_min(sar, low[i - 1], low[i - 2] if i > 1 else low[i - 1])
            if low[i] < sar:
                up = False
                sar = ep
                ep = low[i]
                af = 0.02
            elif high[i] > ep:
                ep = high[i]
                af = js_min(0.2, af + 0.02)
        else:
            sar = js_max(sar, high[i - 1], high[i - 2] if i > 1 else high[i - 1])
            if high[i] > sar:
                up = True
                sar = ep
                ep = high[i]
                af = 0.02
            elif low[i] < ep:
                ep = low[i]
                af = js_min(0.2, af + 0.02)
        result[i] = sar
    return result


def _supertrend(high: Values, low: Values, close: Values, period: int, factor: float = 3) -> list[MaybeNumber]:
    average_range = atr(high, low, close, period)
    line = full(len(close))
    upper = 0.0
    lower = 0.0
    trend = 1
    for i, a in enumerate(average_range):
        if a is None or not finite(a):
            continue
        mid = (high[i] + low[i]) / 2
        basic_upper = mid + factor * a
        basic_lower = mid - factor * a
        upper = basic_upper if i == 0 or close[i - 1] > upper else js_min(basic_upper, upper)
        lower = basic_lower if i == 0 or close[i - 1] < lower else js_max(basic_lower, lower)
        if trend > 0 and close[i] < lower:
            trend = -1
        elif trend < 0 and close[i] > upper:
            trend = 1
        line[i] = lower if trend > 0 else upper
    return line


def _triple_ema(values: Values, period: int) -> list[MaybeNumber]:
    e1 = ema(values, period)
    first = values[0] if values else 0.0
    e1_numeric = [value if value is not None and finite(value) else first for value in e1]
    e2 = ema(e1_numeric, period)
    e2_numeric = [value if value is not None and finite(value) else e1_numeric[i] for i, value in enumerate(e2)]
    e3 = ema(e2_numeric, period)
    result: list[MaybeNumber] = []
    for a, b, c in zip(e1, e2, e3, strict=True):
        ok = a is not None and b is not None and c is not None and finite(a) and finite(b) and finite(c)
        result.append(3 * a - 3 * b + c if ok and a is not None and b is not None and c is not None else None)
    return result


def _relative_vigor(open_: Values, high: Values, low: Values, close: Values, period: int) -> tuple[list[MaybeNumber], list[MaybeNumber]]:
    numerator = [value - open_[i] for i, value in enumerate(close)]
    denominator = [js_max(EPSILON, value - low[i]) for i, value in enumerate(high)]
    numerator_sma = sma(numerator, period)
    denominator_sma = sma(denominator, period)
    rvi: list[MaybeNumber] = []
    for n, d in zip(numerator_sma, denominator_sma, strict=True):
        rvi.append(n / d * 100 if n is not None and d is not None and finite(n) and finite(d) and d != 0 else None)
    return rvi, sma(_or_zero(rvi), 4)


def _relative_volatility(close: Values, period: int) -> list[MaybeNumber]:
    p = safe_period(period)
    deviation = _or_zero(stdev(close, p))
    up = [value if i > 0 and close[i] > close[i - 1] else 0.0 for i, value in enumerate(deviation)]
    down = [value if i > 0 and close[i] < close[i - 1] else 0.0 for i, value in enumerate(deviation)]
    result: list[MaybeNumber] = []
    for u, d in zip(rma(up, p), rma(down, p), strict=True):
        result.append(100 * u / (u + d) if u is not None and d is not None and finite(u) and finite(d) and u + d != 0 else None)
    return result


def _ratio(numerators: Sequence[MaybeNumber], denominators: Sequence[MaybeNumber]) -> list[MaybeNumber]:
    result: list[MaybeNumber] = []
    for n, d in zip(numerators, denominators, strict=True):
        result.append(n / d if n is not None and d is not None and finite(n) and finite(d) and d != 0 else None)
    return result


def _ultimate_oscillator(high: Values, low: Values, close: Values) -> list[MaybeNumber]:
    buying = [value - low[i] if i == 0 else value - js_min(low[i], close[i - 1]) for i, value in enumerate(close)]
    ranges = [
        high[i] - low[i] if i == 0 else js_max(high[i], close[i - 1]) - js_min(low[i], close[i - 1])
        for i in range(len(close))
    ]

    def average(period: int) -> list[MaybeNumber]:
        return _ratio(rolling_sum(buying, period), rolling_sum(ranges, period))

    a7, a14, a28 = average(7), average(14), average(28)
    result: list[MaybeNumber] = []
    for x, y, z in zip(a7, a14, a28, strict=True):
        ok = x is not None and y is not None and z is not None and finite(x) and finite(y) and finite(z)
        result.append(100 * (4 * x + 2 * y + z) / 7 if ok and x is not None and y is not None and z is not None else None)
    return result


def _vortex(high: Values, low: Values, close: Values, period: int) -> tuple[list[MaybeNumber], list[MaybeNumber]]:
    vm_plus = [0.0 if i == 0 else abs(value - low[i - 1]) for i, value in enumerate(high)]
    vm_minus = [0.0 if i == 0 else abs(value - high[i - 1]) for i, value in enumerate(low)]
    tr_sum = rolling_sum(true_range(high, low, close), period)
    return _ratio(rolling_sum(vm_plus, period), tr_sum), _ratio(rolling_sum(vm_minus, period), tr_sum)


def _volume_weighted_ma(close: Values, volume: Values, period: int) -> list[MaybeNumber]:
    price_volume = [value * volume[i] for i, value in enumerate(close)]
    return _ratio(rolling_sum(price_volume, period), rolling_sum(volume, period))


def _session_twap(bars: BarSeries, typical: Values) -> list[MaybeNumber]:
    result = full(len(bars))
    current_day = ""
    running = 0.0
    count = 0
    for i, start_time in enumerate(bars.start_times):
        # The browser groups by the first ten characters of the bar's ISO start_time string, which the API sends in UTC.
        day = (start_time if start_time.tzinfo is None else start_time.astimezone(UTC)).date().isoformat()
        if day != current_day:
            current_day = day
            running = 0.0
            count = 0
        running += typical[i]
        count += 1
        result[i] = running / count
    return result


def _technical_rating(high: Values, low: Values, close: Values) -> list[MaybeNumber]:
    r = rsi(close, 14)
    st = _stochastic(high, low, close, 14)
    c = _cci(high, low, close, 20)
    momentum = roc(close, 10)
    ma20 = sma(close, 20)
    ma50 = sma(close, 50)
    plus, minus, adx = dmi(high, low, close, 14)
    result: list[MaybeNumber] = []
    for i, value in enumerate(close):
        signals: list[float] = []
        if (ri := r[i]) is not None and finite(ri):
            signals.append(1.0 if ri > 55 else -1.0 if ri < 45 else 0.0)
        if (si := st[i]) is not None and finite(si):
            signals.append(1.0 if si > 60 else -1.0 if si < 40 else 0.0)
        if (ci := c[i]) is not None and finite(ci):
            signals.append(1.0 if ci > 50 else -1.0 if ci < -50 else 0.0)
        if (mi := momentum[i]) is not None and finite(mi):
            signals.append(_js_sign(mi))
        if (m20 := ma20[i]) is not None and finite(m20):
            signals.append(1.0 if value > m20 else -1.0)
        if (m50 := ma50[i]) is not None and finite(m50):
            signals.append(1.0 if value > m50 else -1.0)
        a, p, m = adx[i], plus[i], minus[i]
        if a is not None and p is not None and m is not None and finite(a) and finite(p) and finite(m) and a > 20:
            signals.append(1.0 if p > m else -1.0)
        result.append(mean(signals) if signals else None)
    return result


@dataclass(frozen=True)
class _Pivot:
    index: int
    price: float
    type: Literal["high", "low"]


def _pattern_pivots(bars: BarSeries, strength: int = 3) -> list[_Pivot]:
    """Port of ``findPatternPivots`` in ``autoPatterns.ts``."""
    r = min(8, max(2, math.trunc(strength) or 3))
    candidates: list[_Pivot] = []
    for index in range(r, len(bars) - r):
        maximum = js_max(*bars.high[index - r : index + r + 1])
        minimum = js_min(*bars.low[index - r : index + r + 1])
        if bars.high[index] >= maximum:
            candidates.append(_Pivot(index, bars.high[index], "high"))
        if bars.low[index] <= minimum:
            candidates.append(_Pivot(index, bars.low[index], "low"))
    alternating: list[_Pivot] = []
    # Candidates are generated in (index, high before low) order, which is the browser's sort order.
    for candidate in candidates:
        if not alternating:
            alternating.append(candidate)
            continue
        previous = alternating[-1]
        if candidate.index == previous.index:
            previous_close = bars.close[previous.index]
            if abs(candidate.price - previous_close) > abs(previous.price - previous_close):
                alternating[-1] = candidate
            continue
        if candidate.type == previous.type:
            more_extreme = candidate.price >= previous.price if candidate.type == "high" else candidate.price <= previous.price
            if more_extreme:
                alternating[-1] = candidate
            continue
        alternating.append(candidate)
    return alternating


def _both(left: Sequence[MaybeNumber], right: Sequence[MaybeNumber], combine: Callable[[float, float], float]) -> list[MaybeNumber]:
    result: list[MaybeNumber] = []
    for a, b in zip(left, right, strict=True):
        result.append(combine(a, b) if a is not None and b is not None and finite(a) and finite(b) else None)
    return result


@_builtin("tv-money-flow-mfi", "Money Flow (MFI)", "exact", 14)
def _mfi(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    values = _money_flow_index(bars.high, bars.low, bars.close, bars.volume, period)
    return [output("tv-money-flow-mfi", "mfi", values)]


@_builtin("tv-moving-average-ribbon", "Moving Average Ribbon", "exact", 20)
def _moving_average_ribbon(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-moving-average-ribbon", f"sma-{p}", sma(bars.close, p)) for p in (20, 50, 100, 200)]


@_builtin("tv-moving-averages", "Moving Averages", "recursive", 20)
def _moving_averages(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [
        output("tv-moving-averages", "sma", sma(bars.close, period)),
        output("tv-moving-averages", "ema", ema(bars.close, period)),
    ]


def _volume_index(bars: BarSeries, positive: bool) -> list[MaybeNumber]:
    close, volume = bars.close, bars.volume
    current = 1000.0
    values: list[MaybeNumber] = []
    for i, value in enumerate(close):
        if i > 0 and (volume[i] > volume[i - 1] if positive else volume[i] < volume[i - 1]) and close[i - 1] != 0:
            current *= 1 + (value - close[i - 1]) / close[i - 1]
        values.append(current)
    return values


@_builtin("tv-negative-volume-index-nvi", "Negative Volume Index (NVI)", "exact", 1)
def _nvi(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-negative-volume-index-nvi", "nvi", _volume_index(bars, positive=False))]


@_builtin("tv-positive-volume-index-pvi", "Positive Volume Index (PVI)", "exact", 1)
def _pvi(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-positive-volume-index-pvi", "pvi", _volume_index(bars, positive=True))]


def _net_volume(bars: BarSeries) -> list[MaybeNumber]:
    close = bars.close
    return [
        0.0 if i == 0 else value if close[i] > close[i - 1] else -value if close[i] < close[i - 1] else 0.0
        for i, value in enumerate(bars.volume)
    ]


@_builtin("tv-net-volume", "Net Volume", "exact", 1)
def _net_volume_indicator(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-net-volume", "net-volume", _net_volume(bars))]


@_builtin("tv-up-down-volume", "Up/Down Volume", "exact", 1)
def _up_down_volume(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-up-down-volume", "net-volume", _net_volume(bars))]


@_builtin("tv-on-balance-volume-obv", "On Balance Volume (OBV)", "exact", 1)
def _obv(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    close = bars.close
    current = 0.0
    values: list[MaybeNumber] = []
    for i, value in enumerate(bars.volume):
        if i > 0:
            current += value if close[i] > close[i - 1] else -value if close[i] < close[i - 1] else 0.0
        values.append(current)
    return [output("tv-on-balance-volume-obv", "obv", values)]


@_builtin("tv-parabolic-sar-sar", "Parabolic SAR (SAR)", "recursive", 2)
def _parabolic_sar_indicator(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-parabolic-sar-sar", "sar", _parabolic_sar(bars.high, bars.low))]


def _percentage_oscillator(indicator_id: str, source: Values, inputs: IndicatorInputs) -> list[IndicatorOutputSeries]:
    fast_period = 12 if inputs.fast_period is None else inputs.fast_period
    slow_period = 26 if inputs.slow_period is None else inputs.slow_period
    signal_period = 9 if inputs.signal_period is None else inputs.signal_period
    fast = ema(source, _js_period(fast_period))
    slow = ema(source, _js_period(slow_period))
    line: list[MaybeNumber] = []
    for f, s in zip(fast, slow, strict=True):
        line.append(100 * (f - s) / s if f is not None and s is not None and finite(f) and finite(s) and s != 0 else None)
    return [output(indicator_id, "line", line), output(indicator_id, "signal", ema(_or_zero(line), _js_period(signal_period)))]


@_builtin("tv-percentage-price-oscillator-ppo", "Percentage Price Oscillator (PPO)", "recursive", 9)
def _ppo(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return _percentage_oscillator("tv-percentage-price-oscillator-ppo", bars.close, inputs)


@_builtin("tv-percentage-volume-oscillator-pvo", "Percentage Volume Oscillator (PVO)", "recursive", 9)
def _pvo(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return _percentage_oscillator("tv-percentage-volume-oscillator-pvo", bars.volume, inputs)


@_builtin("tv-performance", "Performance", "exact", 1)
def _performance(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    anchor = bars.close[0] or 1.0
    return [output("tv-performance", "performance", [(value / anchor - 1) * 100 for value in bars.close])]


@_builtin("tv-pivot-points-high-low", "Pivot Points High Low", "exact", 10)
def _pivot_points_high_low(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    strength = max(2, min(8, _js_round(period / 3)))
    by_index = {pivot.index: pivot for pivot in _pattern_pivots(bars, strength)}
    highs = full(len(bars))
    lows = full(len(bars))
    h: MaybeNumber = None
    lo: MaybeNumber = None
    for i in range(len(bars)):
        pivot = by_index.get(i)
        if pivot is not None and pivot.type == "high":
            h = pivot.price
        if pivot is not None and pivot.type == "low":
            lo = pivot.price
        highs[i] = h
        lows[i] = lo
    return [
        output("tv-pivot-points-high-low", "pivot-high", highs),
        output("tv-pivot-points-high-low", "pivot-low", lows),
    ]


@_builtin("tv-pivot-points-standard", "Pivot Points Standard", "exact", 20)
def _pivot_points_standard(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    high, low, close = bars.high, bars.low, bars.close
    pp, r1, s1 = full(len(close)), full(len(close)), full(len(close))
    for i in range(1, len(close)):
        pivot = (high[i - 1] + low[i - 1] + close[i - 1]) / 3
        pp[i] = pivot
        r1[i] = 2 * pivot - low[i - 1]
        s1[i] = 2 * pivot - high[i - 1]
    return [
        output("tv-pivot-points-standard", "pp", pp),
        output("tv-pivot-points-standard", "r1", r1),
        output("tv-pivot-points-standard", "s1", s1),
    ]


@_builtin("tv-price-momentum-oscillator-pmo", "Price Momentum Oscillator (PMO)", "recursive", 35)
def _pmo(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    one_roc = [value * 10 if value is not None and finite(value) else 0.0 for value in roc(bars.close, 1)]
    pmo = ema(_or_zero(ema(one_roc, 35)), 20)
    signal = ema(_or_zero(pmo), 10)
    return [
        output("tv-price-momentum-oscillator-pmo", "pmo", pmo),
        output("tv-price-momentum-oscillator-pmo", "signal", signal),
    ]


@_builtin("tv-price-volume-trend-pvt", "Price Volume Trend (PVT)", "exact", 1)
def _pvt(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    close, volume = bars.close, bars.volume
    current = 0.0
    values: list[MaybeNumber] = []
    for i, value in enumerate(close):
        if i > 0 and close[i - 1] != 0:
            current += volume[i] * (value - close[i - 1]) / close[i - 1]
        values.append(current)
    return [output("tv-price-volume-trend-pvt", "pvt", values)]


_SPECIAL_K_COMPONENTS = (
    (10, 10, 1), (15, 10, 2), (20, 10, 3), (30, 15, 4), (40, 20, 1), (65, 30, 2),
    (75, 30, 3), (100, 40, 4), (195, 65, 1), (265, 65, 2), (390, 100, 3), (530, 130, 4),
)


@_builtin("tv-pring-s-special-k", "Pring's Special K", "exact", 30)
def _special_k(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    components = [
        [value * weight if value is not None and finite(value) else 0.0 for value in sma(_or_zero(roc(bars.close, r)), s)]
        for r, s, weight in _SPECIAL_K_COMPONENTS
    ]
    values = [js_sum([series[i] for series in components]) for i in range(len(bars))]
    return [output("tv-pring-s-special-k", "special-k", values)]


@_builtin("tv-rank-correlation-index-rci", "Rank Correlation Index (RCI)", "exact", 9)
def _rci(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-rank-correlation-index-rci", "rci", spearman(bars.close, period))]


@_builtin("tv-rci-ribbon", "RCI Ribbon", "exact", 9)
def _rci_ribbon(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-rci-ribbon", f"rci-{p}", spearman(bars.close, p)) for p in (9, 26, 52)]


@_builtin("tv-rate-of-change-roc", "Rate of Change (ROC)", "exact", 9)
def _roc(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-rate-of-change-roc", "roc", roc(bars.close, period))]


@_builtin("tv-relative-vigor-index", "Relative Vigor Index", "exact", 10)
def _relative_vigor_index(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    rvi, signal = _relative_vigor(bars.open, bars.high, bars.low, bars.close, period)
    return [output("tv-relative-vigor-index", "rvi", rvi), output("tv-relative-vigor-index", "signal", signal)]


@_builtin("tv-relative-volatility-index", "Relative Volatility Index", "recursive", 14)
def _relative_volatility_index(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-relative-volatility-index", "rvol", _relative_volatility(bars.close, period))]


def _smi_ergodic(close: Values) -> tuple[list[MaybeNumber], list[MaybeNumber]]:
    tsi = _true_strength(close, 20, 5)
    return tsi, ema(_or_zero(tsi), 5)


@_builtin("tv-smi-ergodic-indicator", "SMI Ergodic Indicator", "recursive", 20)
def _smi_ergodic_indicator(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    tsi, signal = _smi_ergodic(bars.close)
    return [output("tv-smi-ergodic-indicator", "smi", tsi), output("tv-smi-ergodic-indicator", "signal", signal)]


@_builtin("tv-smi-ergodic-oscillator", "SMI Ergodic Oscillator", "recursive", 20)
def _smi_ergodic_oscillator(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    tsi, signal = _smi_ergodic(bars.close)
    return [output("tv-smi-ergodic-oscillator", "oscillator", _both(tsi, signal, lambda t, s: t - s))]


@_builtin("tv-smoothed-moving-average", "Smoothed Moving Average", "recursive", 20)
def _smoothed_moving_average(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-smoothed-moving-average", "smma", rma(bars.close, period))]


@_builtin("tv-stochastic-stoch", "Stochastic (STOCH)", "exact", 14)
def _stochastic_indicator(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    k = _stochastic(bars.high, bars.low, bars.close, period)
    return [output("tv-stochastic-stoch", "k", k), output("tv-stochastic-stoch", "d", sma(_or_zero(k), 3))]


@_builtin("tv-stochastic-momentum-index-smi", "Stochastic Momentum Index (SMI)", "recursive", 14)
def _stochastic_momentum_index(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    smi = _stochastic_momentum(bars.high, bars.low, bars.close, period)
    return [
        output("tv-stochastic-momentum-index-smi", "smi", smi),
        output("tv-stochastic-momentum-index-smi", "signal", ema(_or_zero(smi), 3)),
    ]


@_builtin("tv-supertrend", "Supertrend", "recursive", 10)
def _supertrend_indicator(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-supertrend", "supertrend", _supertrend(bars.high, bars.low, bars.close, period))]


@_builtin("tv-technical-ratings", "Technical Ratings", "recursive", 14)
def _technical_ratings(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-technical-ratings", "rating", _technical_rating(bars.high, bars.low, bars.close))]


@_builtin("tv-time-weighted-average-price", "Time Weighted Average Price", "exact", 1)
def _twap(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-time-weighted-average-price", "twap", _session_twap(bars, typical_price(bars)))]


@_builtin("tv-trend-strength-index", "Trend Strength Index", "exact", 20)
def _trend_strength_index(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-trend-strength-index", "trend-strength", correlation_with_index(bars.close, period))]


@_builtin("tv-triple-ema", "Triple EMA", "recursive", 9)
def _triple_ema_indicator(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-triple-ema", "tema", _triple_ema(bars.close, period))]


@_builtin("tv-trix", "TRIX", "recursive", 18)
def _trix(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    def smoothed(source: Values) -> list[float]:
        return [value if value is not None and finite(value) else source[i] for i, value in enumerate(ema(source, period))]

    e3 = smoothed(smoothed(smoothed(bars.close)))
    values: list[MaybeNumber] = [None if i == 0 or e3[i - 1] == 0 else (value / e3[i - 1] - 1) * 100 for i, value in enumerate(e3)]
    return [output("tv-trix", "trix", values)]


@_builtin("tv-true-strength-index", "True Strength Index", "recursive", 25)
def _true_strength_index(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    long_period = 25 if inputs.slow_period is None else inputs.slow_period
    short_period = 13 if inputs.fast_period is None else inputs.fast_period
    signal_period = 13 if inputs.signal_period is None else inputs.signal_period
    tsi = _true_strength(bars.close, _js_period(long_period), _js_period(short_period))
    return [
        output("tv-true-strength-index", "tsi", tsi),
        output("tv-true-strength-index", "signal", ema(_or_zero(tsi), _js_period(signal_period))),
    ]


@_builtin("tv-ulcer-index", "Ulcer Index", "exact", 14)
def _ulcer_index(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    hh = highest(bars.close, period)
    squared: list[float] = []
    for value, h in zip(bars.close, hh, strict=True):
        if h is not None and finite(h) and h != 0:
            drawdown = (value - h) / h * 100
            squared.append(drawdown * drawdown)
        else:
            squared.append(0.0)
    average = sma(squared, period)
    return [output("tv-ulcer-index", "ulcer", [js_sqrt(v) if v is not None and finite(v) else None for v in average])]


@_builtin("tv-ultimate-oscillator-uo", "Ultimate Oscillator (UO)", "exact", 28)
def _ultimate_oscillator_indicator(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-ultimate-oscillator-uo", "uo", _ultimate_oscillator(bars.high, bars.low, bars.close))]


@_builtin("tv-volatility-stop", "Volatility Stop", "recursive", 20)
def _volatility_stop(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    close = bars.close
    average_range = atr(bars.high, bars.low, close, period)
    hh = highest(close, period)
    ll = lowest(close, period)
    values: list[MaybeNumber] = []
    for value, a, h, lo in zip(close, average_range, hh, ll, strict=True):
        if a is None or h is None or lo is None or not (finite(a) and finite(h) and finite(lo)):
            values.append(None)
        else:
            values.append(h - 2 * a if value >= (h + lo) / 2 else lo + 2 * a)
    return [output("tv-volatility-stop", "vstop", values)]


@_builtin("tv-volume", "Volume", "exact", 1)
def _volume(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-volume", "volume", bars.volume)]


@_builtin("tv-volume-weighted-moving-average-vwma", "Volume-Weighted Moving Average (VWMA)", "exact", 20)
def _vwma(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-volume-weighted-moving-average-vwma", "vwma", _volume_weighted_ma(bars.close, bars.volume, period))]


@_builtin("tv-vortex-indicator", "Vortex Indicator", "exact", 14)
def _vortex_indicator(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    plus, minus = _vortex(bars.high, bars.low, bars.close, period)
    return [output("tv-vortex-indicator", "plus", plus), output("tv-vortex-indicator", "minus", minus)]


@_builtin("tv-weighted-moving-average", "Weighted Moving Average", "exact", 9)
def _weighted_moving_average(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [output("tv-weighted-moving-average", "wma", wma(bars.close, period))]


@_builtin("tv-williams-r-r", "Williams %R (%R)", "exact", 14)
def _williams_r(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    hh = highest(bars.high, period)
    ll = lowest(bars.low, period)
    values: list[MaybeNumber] = []
    for value, h, lo in zip(bars.close, hh, ll, strict=True):
        if h is not None and lo is not None and finite(h) and finite(lo) and h != lo:
            values.append(-100 * (h - value) / (h - lo))
        else:
            values.append(None)
    return [output("tv-williams-r-r", "williams-r", values)]


@_builtin("tv-williams-alligator", "Williams Alligator", "recursive", 13)
def _williams_alligator(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    median_price = hl2(bars)
    return [
        output("tv-williams-alligator", "jaw", rma(median_price, 13)),
        output("tv-williams-alligator", "teeth", rma(median_price, 8)),
        output("tv-williams-alligator", "lips", rma(median_price, 5)),
    ]


@_builtin("tv-williams-fractal", "Williams Fractal", "exact", 2)
def _williams_fractal(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    high, low = bars.high, bars.low
    radius = max(2, min(8, period))
    up = full(len(bars))
    down = full(len(bars))
    for i in range(radius, len(bars) - radius):
        if high[i] == js_max(*high[i - radius : i + radius + 1]):
            up[i] = high[i]
        if low[i] == js_min(*low[i - radius : i + radius + 1]):
            down[i] = low[i]
    return [output("tv-williams-fractal", "up-fractal", up), output("tv-williams-fractal", "down-fractal", down)]


@_builtin("tv-woodies-cci", "Woodies CCI", "exact", 14)
def _woodies_cci(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    return [
        output("tv-woodies-cci", "trend-cci", _cci(bars.high, bars.low, bars.close, period)),
        output("tv-woodies-cci", "entry-cci", _cci(bars.high, bars.low, bars.close, 6)),
    ]


@_builtin("tv-zig-zag", "Zig Zag", "exact", 5)
def _zig_zag(bars: BarSeries, inputs: IndicatorInputs, period: int) -> list[IndicatorOutputSeries]:
    values = full(len(bars))
    for pivot in _pattern_pivots(bars, max(2, min(8, period))):
        values[pivot.index] = pivot.price
    return [output("tv-zig-zag", "zigzag", values)]
