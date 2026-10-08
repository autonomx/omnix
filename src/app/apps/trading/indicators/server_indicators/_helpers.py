"""Ports of the browser's indicator helpers (``tradingViewBuiltIns.ts``), operation for operation.

Results must match the browser bit for bit where possible, so these follow the
TypeScript order of operations exactly: sums are plain left-to-right loops,
``x ** 2`` is written ``x * x`` (V8's pow returns ``x * x`` for an exponent of
2), and ``js_max``/``js_min`` keep JavaScript's NaN and signed-zero rules.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Callable, Sequence

from ..registry import BarSeries, IndicatorOutputSeries

MaybeNumber = float | None
Values = Sequence[float]

EPSILON = sys.float_info.epsilon


def full(length: int) -> list[MaybeNumber]:
    return [None] * length


def safe_period(period: object, fallback: int = 14) -> int:
    if isinstance(period, float) and period.is_integer():
        period = int(period)
    return period if isinstance(period, int) and not isinstance(period, bool) and period > 0 else fallback


def js_round(value: float) -> float:
    """JavaScript ``Math.round``: halves round up (towards +infinity). Python's ``round`` rounds halves to even."""
    return float(math.floor(value + 0.5))


def js_sum(values: Values) -> float:
    # Builtin sum() is compensated from Python 3.12 and would not match the browser's reduce().
    total = 0.0
    for value in values:
        total += value
    return total


def mean(values: Values) -> float:
    return js_sum(values) / len(values) if values else 0.0


def finite(value: MaybeNumber) -> bool:
    return value is not None and math.isfinite(value)


def js_max(*values: float) -> float:
    result = -math.inf
    for value in values:
        if math.isnan(value):
            return math.nan
        if value > result or (value == 0 and result == 0 and math.copysign(1.0, result) < 0):
            result = value
    return result


def js_min(*values: float) -> float:
    result = math.inf
    for value in values:
        if math.isnan(value):
            return math.nan
        if value < result or (value == 0 and result == 0 and math.copysign(1.0, value) < 0):
            result = value
    return result


def sma(values: Values, period: int) -> list[MaybeNumber]:
    p = safe_period(period)
    result = full(len(values))
    if len(values) < p:
        return result
    running = js_sum(values[:p])
    result[p - 1] = running / p
    for i in range(p, len(values)):
        running += values[i] - values[i - p]
        result[i] = running / p
    return result


def ema(values: Values, period: int) -> list[MaybeNumber]:
    p = safe_period(period)
    result = full(len(values))
    if len(values) < p:
        return result
    current = mean(values[:p])
    result[p - 1] = current
    alpha = 2 / (p + 1)
    for i in range(p, len(values)):
        current += alpha * (values[i] - current)
        result[i] = current
    return result


def rma(values: Values, period: int) -> list[MaybeNumber]:
    p = safe_period(period)
    result = full(len(values))
    if len(values) < p:
        return result
    current = mean(values[:p])
    result[p - 1] = current
    for i in range(p, len(values)):
        current = (current * (p - 1) + values[i]) / p
        result[i] = current
    return result


def wma(values: Values, period: int) -> list[MaybeNumber]:
    p = safe_period(period)
    result = full(len(values))
    denominator = p * (p + 1) / 2
    for i in range(p - 1, len(values)):
        weighted = 0.0
        for j in range(p):
            weighted += values[i - p + 1 + j] * (j + 1)
        result[i] = weighted / denominator
    return result


def rolling(values: Values, period: int, reducer: Callable[[Sequence[float]], float]) -> list[MaybeNumber]:
    p = safe_period(period)
    result = full(len(values))
    for i in range(p - 1, len(values)):
        result[i] = reducer(values[i - p + 1 : i + 1])
    return result


def highest(values: Values, period: int) -> list[MaybeNumber]:
    return rolling(values, period, lambda window: js_max(*window))


def lowest(values: Values, period: int) -> list[MaybeNumber]:
    return rolling(values, period, lambda window: js_min(*window))


def _median_of(window: Sequence[float]) -> float:
    ordered = sorted(window)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def median(values: Values, period: int) -> list[MaybeNumber]:
    return rolling(values, period, _median_of)


def _population_deviation(window: Sequence[float]) -> float:
    m = mean(window)
    return math.sqrt(mean([(value - m) * (value - m) for value in window]))


def stdev(values: Values, period: int) -> list[MaybeNumber]:
    return rolling(values, period, _population_deviation)


def rolling_sum(values: Values, period: int) -> list[MaybeNumber]:
    return rolling(values, period, js_sum)


def true_range(high: Values, low: Values, close: Values) -> list[float]:
    return [
        value - low[i]
        if i == 0
        else js_max(value - low[i], abs(value - close[i - 1]), abs(low[i] - close[i - 1]))
        for i, value in enumerate(high)
    ]


def atr(high: Values, low: Values, close: Values, period: int) -> list[MaybeNumber]:
    return rma(true_range(high, low, close), period)


def rsi(values: Values, period: int) -> list[MaybeNumber]:
    p = safe_period(period)
    gains = [0.0 if i == 0 else js_max(0.0, value - values[i - 1]) for i, value in enumerate(values)]
    losses = [0.0 if i == 0 else js_max(0.0, values[i - 1] - value) for i, value in enumerate(values)]
    average_gain = rma(gains, p)
    average_loss = rma(losses, p)
    result: list[MaybeNumber] = []
    for gain, loss in zip(average_gain, average_loss, strict=True):
        if gain is None or loss is None or not finite(gain) or not finite(loss):
            result.append(None)
        elif loss == 0:
            result.append(100.0)
        else:
            result.append(100 - 100 / (1 + gain / loss))
    return result


def roc(values: Values, period: int) -> list[MaybeNumber]:
    p = safe_period(period)
    return [None if i < p or values[i - p] == 0 else (value / values[i - p] - 1) * 100 for i, value in enumerate(values)]


def bollinger(values: Values, period: int, deviations: float = 2) -> tuple[list[MaybeNumber], list[MaybeNumber], list[MaybeNumber]]:
    middle = sma(values, period)
    deviation = stdev(values, period)
    upper: list[MaybeNumber] = []
    lower: list[MaybeNumber] = []
    for m, d in zip(middle, deviation, strict=True):
        ok = m is not None and d is not None and finite(m) and finite(d)
        upper.append(m + d * deviations if ok and m is not None and d is not None else None)
        lower.append(m - d * deviations if ok and m is not None and d is not None else None)
    return middle, upper, lower


def dmi(high: Values, low: Values, close: Values, period: int) -> tuple[list[MaybeNumber], list[MaybeNumber], list[MaybeNumber]]:
    p = safe_period(period)
    tr = true_range(high, low, close)
    plus_dm = [
        0.0 if i == 0 else js_max(value - high[i - 1] if value - high[i - 1] > low[i - 1] - low[i] else 0.0, 0.0)
        for i, value in enumerate(high)
    ]
    minus_dm = [
        0.0 if i == 0 else js_max(low[i - 1] - value if low[i - 1] - value > high[i] - high[i - 1] else 0.0, 0.0)
        for i, value in enumerate(low)
    ]
    tr_smoothed = rma(tr, p)
    plus_smoothed = rma(plus_dm, p)
    minus_smoothed = rma(minus_dm, p)

    def directional(smoothed: list[MaybeNumber]) -> list[MaybeNumber]:
        values: list[MaybeNumber] = []
        for t, s in zip(tr_smoothed, smoothed, strict=True):
            values.append(100 * s / t if t is not None and s is not None and finite(t) and t != 0 and finite(s) else None)
        return values

    plus = directional(plus_smoothed)
    minus = directional(minus_smoothed)
    dx: list[float] = []
    for pv, mv in zip(plus, minus, strict=True):
        if pv is not None and mv is not None and finite(pv) and finite(mv) and pv + mv != 0:
            dx.append(100 * abs(pv - mv) / (pv + mv))
        else:
            dx.append(0.0)
    return plus, minus, rma(dx, p)


def linear_regression(values: Values, period: int) -> list[MaybeNumber]:
    p = safe_period(period)
    result = full(len(values))
    x_mean = (p - 1) / 2
    x_variance = 0.0
    for i in range(p):
        x_variance = x_variance + (i - x_mean) * (i - x_mean)
    for i in range(p - 1, len(values)):
        window = values[i - p + 1 : i + 1]
        y_mean = mean(window)
        covariance = 0.0
        for j in range(p):
            covariance += (j - x_mean) * (window[j] - y_mean)
        slope = 0.0 if x_variance == 0 else covariance / x_variance
        intercept = y_mean - slope * x_mean
        result[i] = intercept + slope * (p - 1)
    return result


def correlation_with_index(values: Values, period: int) -> list[MaybeNumber]:
    p = safe_period(period)
    result = full(len(values))
    x = [float(i) for i in range(p)]
    mx = mean(x)
    vx = js_sum([(value - mx) * (value - mx) for value in x])
    for i in range(p - 1, len(values)):
        y = values[i - p + 1 : i + 1]
        my = mean(y)
        vy = js_sum([(value - my) * (value - my) for value in y])
        if vy <= EPSILON or vx <= EPSILON:
            result[i] = 0.0
        else:
            result[i] = js_sum([(x[j] - mx) * (value - my) for j, value in enumerate(y)]) / math.sqrt(vx * vy)
    return result


def spearman(values: Values, period: int) -> list[MaybeNumber]:
    p = safe_period(period)
    result = full(len(values))
    for i in range(p - 1, len(values)):
        window = values[i - p + 1 : i + 1]
        order = sorted(range(p), key=lambda index: window[index])
        rank = [0] * p
        for position, index in enumerate(order):
            rank[index] = position + 1
        d2 = js_sum([float((value - (index + 1)) * (value - (index + 1))) for index, value in enumerate(rank)])
        result[i] = 0.0 if p <= 1 else (1 - 6 * d2 / (p * (p * p - 1))) * 100
    return result


def output(indicator_id: str, suffix: str, values: Sequence[MaybeNumber]) -> IndicatorOutputSeries:
    """Like the browser's ``output()``: keeps only finite values."""
    return IndicatorOutputSeries(
        key=f"{indicator_id}:{suffix}",
        points=tuple((index, value) for index, value in enumerate(values) if value is not None and math.isfinite(value)),
    )


def hl2(bars: BarSeries) -> list[float]:
    return [(high + low) / 2 for high, low in zip(bars.high, bars.low, strict=True)]


def typical_price(bars: BarSeries) -> list[float]:
    return [(high + low + close) / 3 for high, low, close in zip(bars.high, bars.low, bars.close, strict=True)]
