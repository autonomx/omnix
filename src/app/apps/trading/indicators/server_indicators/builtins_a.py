"""Server ports of the chart's built-in indicators, batch A (``calculateTradingViewBuiltInOutputs``).

Each function mirrors one branch of the browser engine in ``tradingViewBuiltIns.ts``
operation for operation; see ``_helpers.py`` for the shared rules.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TypeGuard

from ..registry import BarSeries, IndicatorInputs, IndicatorOutputSeries, NumericClass, register
from ._helpers import (
    EPSILON,
    MaybeNumber,
    Values,
    atr,
    bollinger,
    dmi,
    ema,
    finite,
    full,
    highest,
    hl2,
    js_max,
    js_min,
    js_sum,
    linear_regression,
    lowest,
    mean,
    median,
    output,
    roc,
    rolling_sum,
    rsi,
    sma,
    stdev,
    true_range,
    typical_price,
    wma,
)

Outputs = list[IndicatorOutputSeries]


@dataclass(frozen=True)
class _Chart:
    id: str
    period: int
    inputs: IndicatorInputs
    bars: BarSeries

    @property
    def open(self) -> Values:
        return self.bars.open

    @property
    def high(self) -> Values:
        return self.bars.high

    @property
    def low(self) -> Values:
        return self.bars.low

    @property
    def close(self) -> Values:
        return self.bars.close

    @property
    def volume(self) -> Values:
        return self.bars.volume

    def out(self, suffix: str, values: Sequence[MaybeNumber]) -> IndicatorOutputSeries:
        return output(self.id, suffix, values)


_Builder = Callable[[_Chart], Outputs]


def _builtin(indicator_id: str, name: str, numeric_class: NumericClass, default_period: int) -> Callable[[_Builder], _Builder]:
    def decorate(build: _Builder) -> _Builder:
        def compute(bars: BarSeries, inputs: IndicatorInputs) -> Outputs:
            if len(bars) == 0:
                return []
            return build(_Chart(indicator_id, _safe_period(inputs.period, default_period), inputs, bars))

        register(indicator_id, name, numeric_class)(compute)
        return build

    return decorate


def _safe_period(period: object, fallback: int = 14) -> int:
    # Number.isInteger(20.0) is true in JS, so an integral float is a valid period; _helpers.safe_period rejects it.
    if isinstance(period, bool) or not isinstance(period, int | float):
        return fallback
    if isinstance(period, float) and not period.is_integer():
        return fallback
    return int(period) if period > 0 else fallback


def _ok(value: MaybeNumber) -> TypeGuard[float]:
    return finite(value)


def _or_zero(values: Sequence[MaybeNumber]) -> list[float]:
    return [value if _ok(value) else 0.0 for value in values]


def _difference(first: Sequence[MaybeNumber], second: Sequence[MaybeNumber]) -> list[MaybeNumber]:
    return [a - b if _ok(a) and _ok(b) else None for a, b in zip(first, second, strict=True)]


def _js_round(value: float) -> int:
    # Math.round rounds halves up; Python's round() rounds them to even.
    floor = math.floor(value)
    return floor + 1 if value - floor >= 0.5 else floor


def _js_sign(value: float) -> float:
    return 1.0 if value > 0 else -1.0 if value < 0 else value


def _js_log(value: float, log: Callable[[float], float] = math.log) -> float:
    # Math.log returns -Infinity for 0 and NaN for negatives, where Python raises.
    if value > 0:
        return log(value)
    return -math.inf if value == 0 else math.nan


def _js_pow(base: float, exponent: float) -> float:
    try:
        return math.pow(base, exponent)
    except OverflowError:
        return math.inf if base > 0 or exponent % 2 == 0 else -math.inf


def _last_index(values: Sequence[float], target: float) -> int:
    for index in range(len(values) - 1, -1, -1):
        if values[index] == target:
            return index
    return -1


def _accumulation_distribution(chart: _Chart) -> list[float]:
    cumulative = 0.0
    values: list[float] = []
    for high, low, close, volume in zip(chart.high, chart.low, chart.close, chart.volume, strict=True):
        span = high - low
        multiplier = 0.0 if span == 0 else ((close - low) - (high - close)) / span
        cumulative += multiplier * volume
        values.append(cumulative)
    return values


def _alma(values: Values, period: int, offset: float = 0.85, sigma: float = 6) -> list[MaybeNumber]:
    p = _safe_period(period)
    result = full(len(values))
    m = offset * (p - 1)
    s = p / sigma
    weights = [math.exp(-((i - m) * (i - m)) / (2 * s * s)) for i in range(p)]
    denominator = js_sum(weights)
    for i in range(p - 1, len(values)):
        total = 0.0
        for j in range(p):
            total += values[i - p + 1 + j] * weights[j]
        result[i] = total / denominator
    return result


def _aroon(chart: _Chart) -> tuple[list[MaybeNumber], list[MaybeNumber]]:
    period = chart.period
    up = full(len(chart.close))
    down = full(len(chart.close))
    for i in range(period - 1, len(chart.close)):
        highs = chart.high[i - period + 1 : i + 1]
        lows = chart.low[i - period + 1 : i + 1]
        up[i] = 100 * (_last_index(highs, js_max(*highs)) + 1) / period
        down[i] = 100 * (_last_index(lows, js_min(*lows)) + 1) / period
    return up, down


def _cci(bars: BarSeries, period: int) -> list[MaybeNumber]:
    typical = typical_price(bars)
    basis = sma(typical, period)
    p = _safe_period(period)
    result: list[MaybeNumber] = []
    for i, center in enumerate(basis):
        if not _ok(center):
            result.append(None)
            continue
        deviation = mean([abs(value - center) for value in typical[i - p + 1 : i + 1]])
        result.append(0.0 if deviation == 0 else (typical[i] - center) / (0.015 * deviation))
    return result


def _percentile_rank(values: Values, period: int) -> list[MaybeNumber]:
    p = _safe_period(period)
    result: list[MaybeNumber] = []
    for i, value in enumerate(values):
        if i < p - 1:
            result.append(None)
            continue
        below = len([item for item in values[i - p + 1 : i + 1] if item < value])
        result.append(100 * below / max(1, p - 1))
    return result


def _connors_rsi(close: Values) -> list[MaybeNumber]:
    price_rsi = rsi(close, 3)
    streak = [0.0]
    for i in range(1, len(close)):
        direction = _js_sign(close[i] - close[i - 1])
        previous_direction = _js_sign(streak[i - 1])
        streak.append(0.0 if direction == 0 else streak[i - 1] + direction if direction == previous_direction else direction)
    streak_rsi = rsi(streak, 2)
    one_bar_roc = [0.0 if i == 0 or close[i - 1] == 0 else (value / close[i - 1] - 1) * 100 for i, value in enumerate(close)]
    rank = _percentile_rank(one_bar_roc, 100)
    return [
        (a + b + c) / 3 if _ok(a) and _ok(b) and _ok(c) else None
        for a, b, c in zip(price_rsi, streak_rsi, rank, strict=True)
    ]


def _hull(values: Values, period: int) -> list[MaybeNumber]:
    p = _safe_period(period)
    half = wma(values, max(1, _js_round(p / 2)))
    whole = wma(values, p)
    difference = [2 * h - w if _ok(h) and _ok(w) else 0.0 for h, w in zip(half, whole, strict=True)]
    return wma(difference, max(1, _js_round(math.sqrt(p))))


def _kama(values: Values, period: int) -> list[MaybeNumber]:
    p = _safe_period(period)
    result = full(len(values))
    if len(values) <= p:
        return result
    current = mean(values[:p])
    result[p - 1] = current
    fast = 2 / 3
    slow = 2 / 31
    for i in range(p, len(values)):
        change = abs(values[i] - values[i - p])
        volatility = 0.0
        for j in range(i - p + 1, i + 1):
            volatility += abs(values[j] - values[j - 1])
        efficiency = 0.0 if volatility == 0 else change / volatility
        root = efficiency * (fast - slow) + slow
        current += root * root * (values[i] - current)
        result[i] = current
    return result


def _bands(chart: _Chart, short_period: int) -> tuple[list[MaybeNumber], list[MaybeNumber], list[MaybeNumber]]:
    deviations = 2.0 if chart.inputs.standard_deviations is None else chart.inputs.standard_deviations
    return bollinger(chart.close, short_period, deviations)


def _moving_average_cross(chart: _Chart, default_slow: int) -> Outputs:
    fast = chart.period if chart.inputs.fast_period is None else chart.inputs.fast_period
    slow = default_slow if chart.inputs.slow_period is None else chart.inputs.slow_period
    return [chart.out("fast", sma(chart.close, _safe_period(fast))), chart.out("slow", sma(chart.close, _safe_period(slow)))]


def _stops(chart: _Chart, period: int, lookback: int, multiplier: float) -> Outputs:
    average = atr(chart.high, chart.low, chart.close, period)
    hh = highest(chart.high, lookback)
    ll = lowest(chart.low, lookback)
    return [
        chart.out("long-stop", [h - multiplier * a if _ok(h) and _ok(a) else None for h, a in zip(hh, average, strict=True)]),
        chart.out("short-stop", [low + multiplier * a if _ok(low) and _ok(a) else None for low, a in zip(ll, average, strict=True)]),
    ]


@_builtin("tv-accumulation-distribution-adl", "Accumulation Distribution (ADL)", "exact", 1)
def _adl(chart: _Chart) -> Outputs:
    return [chart.out("adl", _accumulation_distribution(chart))]


@_builtin("tv-arnaud-legoux-moving-average", "Arnaud Legoux Moving Average", "transcendental", 9)
def _arnaud_legoux(chart: _Chart) -> Outputs:
    return [chart.out("alma", _alma(chart.close, chart.period))]


@_builtin("tv-aroon-indicator", "Aroon Indicator", "exact", 14)
def _aroon_indicator(chart: _Chart) -> Outputs:
    up, down = _aroon(chart)
    return [chart.out("up", up), chart.out("down", down)]


@_builtin("tv-aroon-oscillator", "Aroon Oscillator", "exact", 14)
def _aroon_oscillator(chart: _Chart) -> Outputs:
    up, down = _aroon(chart)
    return [chart.out("oscillator", _difference(up, down))]


@_builtin("tv-average-daily-range-adr-indicator", "Average Daily Range (ADR) indicator", "exact", 14)
def _average_daily_range(chart: _Chart) -> Outputs:
    return [chart.out("adr", sma([high - low for high, low in zip(chart.high, chart.low, strict=True)], chart.period))]


@_builtin("tv-average-directional-index-adx", "Average Directional Index (ADX)", "recursive", 14)
def _average_directional_index(chart: _Chart) -> Outputs:
    return [chart.out("adx", dmi(chart.high, chart.low, chart.close, chart.period)[2])]


@_builtin("tv-awesome-oscillator-ao", "Awesome Oscillator (AO)", "exact", 34)
def _awesome_oscillator(chart: _Chart) -> Outputs:
    median_price = hl2(chart.bars)
    return [chart.out("ao", _difference(sma(median_price, 5), sma(median_price, 34)))]


@_builtin("tv-balance-of-power-bop", "Balance of Power (BOP)", "exact", 14)
def _balance_of_power(chart: _Chart) -> Outputs:
    values = [
        0.0 if high == low else (close - open_) / (high - low)
        for open_, high, low, close in zip(chart.open, chart.high, chart.low, chart.close, strict=True)
    ]
    return [chart.out("bop", values)]


@_builtin("tv-bbtrend", "BBTrend", "exact", 20)
def _bbtrend(chart: _Chart) -> Outputs:
    short_middle, short_upper, short_lower = _bands(chart, 20)
    _, long_upper, long_lower = _bands(chart, 50)
    trend: list[MaybeNumber] = []
    for sl, ll, su, lu, sm in zip(short_lower, long_lower, short_upper, long_upper, short_middle, strict=True):
        if _ok(sl) and _ok(ll) and _ok(su) and _ok(lu) and _ok(sm) and sm != 0:
            trend.append((abs(sl - ll) - abs(su - lu)) / sm * 100)
        else:
            trend.append(None)
    return [chart.out("bbtrend", trend)]


@_builtin("tv-bollinger-bands-b-b", "Bollinger Bands %b (%b)", "exact", 20)
def _bollinger_percent_b(chart: _Chart) -> Outputs:
    _, upper, lower = _bands(chart, chart.period)
    values = [
        (close - lo) / (up - lo) if _ok(up) and _ok(lo) and up != lo else None
        for close, up, lo in zip(chart.close, upper, lower, strict=True)
    ]
    return [chart.out("percent-b", values)]


@_builtin("tv-bollinger-bandwidth-bbw", "Bollinger BandWidth (BBW)", "exact", 20)
def _bollinger_bandwidth(chart: _Chart) -> Outputs:
    middle, upper, lower = _bands(chart, chart.period)
    values = [
        (up - lo) / mid * 100 if _ok(up) and _ok(lo) and _ok(mid) and mid != 0 else None
        for mid, up, lo in zip(middle, upper, lower, strict=True)
    ]
    return [chart.out("bandwidth", values)]


@_builtin("tv-bull-bear-power", "Bull Bear Power", "recursive", 13)
def _bull_bear_power(chart: _Chart) -> Outputs:
    basis = ema(chart.close, chart.period)
    return [
        chart.out("bull", [high - b if _ok(b) else None for high, b in zip(chart.high, basis, strict=True)]),
        chart.out("bear", [low - b if _ok(b) else None for low, b in zip(chart.low, basis, strict=True)]),
    ]


@_builtin("tv-chaikin-money-flow-cmf", "Chaikin Money Flow (CMF)", "exact", 20)
def _chaikin_money_flow(chart: _Chart) -> Outputs:
    flow = [
        0.0 if high == low else (((close - low) - (high - close)) / (high - low)) * volume
        for high, low, close, volume in zip(chart.high, chart.low, chart.close, chart.volume, strict=True)
    ]
    flow_sum = rolling_sum(flow, chart.period)
    volume_sum = rolling_sum(chart.volume, chart.period)
    values = [f / v if _ok(f) and _ok(v) and v != 0 else None for f, v in zip(flow_sum, volume_sum, strict=True)]
    return [chart.out("cmf", values)]


@_builtin("tv-chaikin-oscillator", "Chaikin Oscillator", "recursive", 10)
def _chaikin_oscillator(chart: _Chart) -> Outputs:
    adl = _accumulation_distribution(chart)
    return [chart.out("chaikin", _difference(ema(adl, 3), ema(adl, 10)))]


@_builtin("tv-chande-kroll-stop", "Chande Kroll Stop", "recursive", 10)
def _chande_kroll_stop(chart: _Chart) -> Outputs:
    return _stops(chart, 10, 20, 1)


@_builtin("tv-chandelier-exit", "Chandelier Exit", "recursive", 22)
def _chandelier_exit(chart: _Chart) -> Outputs:
    return _stops(chart, chart.period, chart.period, 3)


@_builtin("tv-chande-momentum-oscillator-cmo", "Chande Momentum Oscillator (CMO)", "exact", 14)
def _chande_momentum_oscillator(chart: _Chart) -> Outputs:
    close = chart.close
    gains = [0.0 if i == 0 else js_max(0.0, value - close[i - 1]) for i, value in enumerate(close)]
    losses = [0.0 if i == 0 else js_max(0.0, close[i - 1] - value) for i, value in enumerate(close)]
    values = [
        100 * (g - lo) / (g + lo) if _ok(g) and _ok(lo) and g + lo != 0 else None
        for g, lo in zip(rolling_sum(gains, chart.period), rolling_sum(losses, chart.period), strict=True)
    ]
    return [chart.out("cmo", values)]


@_builtin("tv-choppiness-index-chop", "Choppiness Index (CHOP)", "transcendental", 14)
def _choppiness_index(chart: _Chart) -> Outputs:
    period = chart.period
    ranges = rolling_sum(true_range(chart.high, chart.low, chart.close), period)
    hh = highest(chart.high, period)
    ll = lowest(chart.low, period)
    scale = _js_log(period, math.log10)
    values: list[MaybeNumber] = []
    for r, h, lo in zip(ranges, hh, ll, strict=True):
        # A period of 1 divides by log10(1) = 0, which the browser plots as nothing.
        if _ok(r) and _ok(h) and _ok(lo) and h != lo and scale != 0:
            values.append(100 * _js_log(r / (h - lo), math.log10) / scale)
        else:
            values.append(None)
    return [chart.out("chop", values)]


@_builtin("tv-commodity-channel-index-cci", "Commodity Channel Index (CCI)", "exact", 20)
def _commodity_channel_index(chart: _Chart) -> Outputs:
    return [chart.out("cci", _cci(chart.bars, chart.period))]


@_builtin("tv-connors-rsi-crsi", "Connors RSI (CRSI)", "recursive", 100)
def _connors_rsi_indicator(chart: _Chart) -> Outputs:
    return [chart.out("crsi", _connors_rsi(chart.close))]


@_builtin("tv-coppock-curve", "Coppock Curve", "exact", 14)
def _coppock_curve(chart: _Chart) -> Outputs:
    raw = [
        (a if _ok(a) else 0.0) + (b if _ok(b) else 0.0)
        for a, b in zip(roc(chart.close, 14), roc(chart.close, 11), strict=True)
    ]
    return [chart.out("coppock", wma(raw, 10))]


@_builtin("tv-detrended-price-oscillator-dpo", "Detrended Price Oscillator (DPO)", "exact", 20)
def _detrended_price_oscillator(chart: _Chart) -> Outputs:
    close = chart.close
    basis = sma(close, chart.period)
    shift = chart.period // 2 + 1
    values: list[MaybeNumber] = []
    for i in range(len(close)):
        center = basis[i - shift] if i >= shift else None
        values.append(close[i - shift] - center if _ok(center) else None)
    return [chart.out("dpo", values)]


@_builtin("tv-directional-movement-dmi", "Directional Movement (DMI)", "recursive", 14)
def _directional_movement(chart: _Chart) -> Outputs:
    plus, minus, adx = dmi(chart.high, chart.low, chart.close, chart.period)
    return [chart.out("plus-di", plus), chart.out("minus-di", minus), chart.out("adx", adx)]


@_builtin("tv-donchian-channels-dc", "Donchian Channels (DC)", "exact", 20)
def _donchian_channels(chart: _Chart) -> Outputs:
    upper = highest(chart.high, chart.period)
    lower = lowest(chart.low, chart.period)
    middle = [(u + lo) / 2 if _ok(u) and _ok(lo) else None for u, lo in zip(upper, lower, strict=True)]
    return [chart.out("upper", upper), chart.out("middle", middle), chart.out("lower", lower)]


@_builtin("tv-double-exponential-moving-average-ema", "Double Exponential Moving Average (EMA)", "recursive", 9)
def _double_exponential_moving_average(chart: _Chart) -> Outputs:
    first = ema(chart.close, chart.period)
    first_numeric = [value if _ok(value) else close for value, close in zip(first, chart.close, strict=True)]
    second = ema(first_numeric, chart.period)
    values = [2 * a - b if _ok(a) and _ok(b) else None for a, b in zip(first, second, strict=True)]
    return [chart.out("dema", values)]


@_builtin("tv-ease-of-movement-eom", "Ease of Movement (EOM)", "exact", 14)
def _ease_of_movement(chart: _Chart) -> Outputs:
    high, low, volume = chart.high, chart.low, chart.volume
    raw = [
        0.0
        if i == 0 or volume[i] == 0
        else (((high[i] + low[i]) / 2 - (high[i - 1] + low[i - 1]) / 2) * (high[i] - low[i]) * 100000000) / volume[i]
        for i in range(len(chart.close))
    ]
    return [chart.out("eom", sma(raw, chart.period))]


@_builtin("tv-elder-s-force-index-efi", "Elder's Force Index (EFI)", "recursive", 13)
def _elder_force_index(chart: _Chart) -> Outputs:
    close, volume = chart.close, chart.volume
    raw = [0.0 if i == 0 else (value - close[i - 1]) * volume[i] for i, value in enumerate(close)]
    return [chart.out("efi", ema(raw, chart.period))]


@_builtin("tv-envelope-env", "Envelope (ENV)", "exact", 20)
def _envelope(chart: _Chart) -> Outputs:
    basis = sma(chart.close, chart.period)
    pct = 0.1
    return [
        chart.out("upper", [value * (1 + pct) if _ok(value) else None for value in basis]),
        chart.out("basis", basis),
        chart.out("lower", [value * (1 - pct) if _ok(value) else None for value in basis]),
    ]


@_builtin("tv-fisher-transform", "Fisher Transform", "transcendental", 9)
def _fisher_transform(chart: _Chart) -> Outputs:
    median_price = hl2(chart.bars)
    hh = highest(median_price, chart.period)
    ll = lowest(median_price, chart.period)
    values = full(len(chart.close))
    previous = 0.0
    fisher = 0.0
    for i, (h, lo) in enumerate(zip(hh, ll, strict=True)):
        if not _ok(h) or not _ok(lo) or h == lo:
            continue
        previous = js_max(-0.999, js_min(0.999, 0.66 * ((median_price[i] - lo) / (h - lo) - 0.5) + 0.67 * previous))
        fisher = 0.5 * math.log((1 + previous) / (1 - previous)) + 0.5 * fisher
        values[i] = fisher
    return [chart.out("fisher", values)]


@_builtin("tv-historical-volatility", "Historical Volatility", "transcendental", 20)
def _historical_volatility(chart: _Chart) -> Outputs:
    close = chart.close
    log_returns = [
        0.0 if i == 0 or close[i - 1] <= 0 or value <= 0 else math.log(value / close[i - 1])
        for i, value in enumerate(close)
    ]
    deviation = stdev(log_returns, chart.period)
    return [chart.out("hv", [value * math.sqrt(252) * 100 if _ok(value) else None for value in deviation])]


@_builtin("tv-hull-moving-average", "Hull Moving Average", "exact", 9)
def _hull_moving_average(chart: _Chart) -> Outputs:
    return [chart.out("hma", _hull(chart.close, chart.period))]


@_builtin("tv-ichimoku-cloud", "Ichimoku Cloud", "exact", 26)
def _ichimoku_cloud(chart: _Chart) -> Outputs:
    high, low, close = chart.high, chart.low, chart.close
    count = len(close)

    def midpoint(period: int) -> list[MaybeNumber]:
        return [(h + lo) / 2 if _ok(h) and _ok(lo) else None for h, lo in zip(highest(high, period), lowest(low, period), strict=True)]

    def leading(first: list[MaybeNumber], second: list[MaybeNumber]) -> list[MaybeNumber]:
        values: list[MaybeNumber] = []
        for i in range(count):
            a = first[i - 26] if i >= 26 else None
            b = second[i - 26] if i >= 26 else None
            values.append((a + b) / 2 if _ok(a) and _ok(b) else None)
        return values

    conversion = midpoint(9)
    base = midpoint(26)
    span_b_high = highest(high, 52)
    span_b_low = lowest(low, 52)
    lagging: list[MaybeNumber] = [close[i + 26] if i + 26 < count else None for i in range(count)]
    return [
        chart.out("conversion", conversion),
        chart.out("base", base),
        chart.out("span-a", leading(conversion, base)),
        chart.out("span-b", leading(span_b_high, span_b_low)),
        chart.out("lagging", lagging),
    ]


@_builtin("tv-kaufman-s-adaptive-moving-average-kama", "Kaufman's Adaptive Moving Average (KAMA)", "recursive", 10)
def _kaufman_adaptive_moving_average(chart: _Chart) -> Outputs:
    return [chart.out("kama", _kama(chart.close, chart.period))]


@_builtin("tv-keltner-channels-kc", "Keltner Channels (KC)", "recursive", 20)
def _keltner_channels(chart: _Chart) -> Outputs:
    basis = ema(chart.close, chart.period)
    average = atr(chart.high, chart.low, chart.close, chart.period)
    return [
        chart.out("upper", [b + 2 * a if _ok(b) and _ok(a) else None for b, a in zip(basis, average, strict=True)]),
        chart.out("basis", basis),
        chart.out("lower", [b - 2 * a if _ok(b) and _ok(a) else None for b, a in zip(basis, average, strict=True)]),
    ]


@_builtin("tv-klinger-oscillator", "Klinger Oscillator", "recursive", 55)
def _klinger_oscillator(chart: _Chart) -> Outputs:
    high, low, close, volume = chart.high, chart.low, chart.close, chart.volume
    trend = [
        1.0 if i == 0 else (1.0 if high[i] + low[i] + close[i] > high[i - 1] + low[i - 1] + close[i - 1] else -1.0)
        for i in range(len(close))
    ]
    force = [
        trend[i] * volume[i] * abs(2 * ((high[i] - low[i]) / js_max(EPSILON, high[i] + low[i])) - 1) * 100
        for i in range(len(close))
    ]
    oscillator = _difference(ema(force, 34), ema(force, 55))
    return [chart.out("klinger", oscillator), chart.out("signal", ema(_or_zero(oscillator), 13))]


@_builtin("tv-know-sure-thing-kst", "Know Sure Thing (KST)", "exact", 30)
def _know_sure_thing(chart: _Chart) -> Outputs:
    close = chart.close
    s1 = sma(_or_zero(roc(close, 10)), 10)
    s2 = sma(_or_zero(roc(close, 15)), 10)
    s3 = sma(_or_zero(roc(close, 20)), 10)
    s4 = sma(_or_zero(roc(close, 30)), 15)
    kst = [
        a + 2 * b + 3 * c + 4 * d if _ok(a) and _ok(b) and _ok(c) and _ok(d) else None
        for a, b, c, d in zip(s1, s2, s3, s4, strict=True)
    ]
    return [chart.out("kst", kst), chart.out("signal", sma(_or_zero(kst), 9))]


@_builtin("tv-least-squares-moving-average", "Least Squares Moving Average", "exact", 25)
def _least_squares_moving_average(chart: _Chart) -> Outputs:
    return [chart.out("linreg", linear_regression(chart.close, chart.period))]


@_builtin("tv-linear-regression", "Linear Regression", "exact", 20)
def _linear_regression(chart: _Chart) -> Outputs:
    return [chart.out("linreg", linear_regression(chart.close, chart.period))]


@_builtin("tv-ma-cross", "MA Cross", "exact", 9)
def _ma_cross(chart: _Chart) -> Outputs:
    return _moving_average_cross(chart, 21)


@_builtin("tv-movingavg-cross", "MovingAvg Cross", "exact", 9)
def _movingavg_cross(chart: _Chart) -> Outputs:
    return _moving_average_cross(chart, 21)


@_builtin("tv-movingavg2line-cross", "MovingAvg2Line Cross", "exact", 9)
def _movingavg2line_cross(chart: _Chart) -> Outputs:
    return _moving_average_cross(chart, 26)


@_builtin("tv-mass-index", "Mass Index", "recursive", 25)
def _mass_index(chart: _Chart) -> Outputs:
    first = ema([high - low for high, low in zip(chart.high, chart.low, strict=True)], 9)
    second = ema(_or_zero(first), 9)
    ratio = [a / b if _ok(a) and _ok(b) and b != 0 else 0.0 for a, b in zip(first, second, strict=True)]
    return [chart.out("mass", rolling_sum(ratio, chart.period))]


@_builtin("tv-mcginley-dynamic", "McGinley Dynamic", "transcendental", 14)
def _mcginley_dynamic(chart: _Chart) -> Outputs:
    close = chart.close
    values = full(len(close))
    dynamic = close[0]
    values[0] = dynamic
    for i in range(1, len(close)):
        ratio = 1.0 if dynamic == 0 else close[i] / dynamic
        dynamic += (close[i] - dynamic) / js_max(1.0, 0.6 * chart.period * _js_pow(ratio, 4))
        values[i] = dynamic
    return [chart.out("mcginley", values)]


@_builtin("tv-median", "Median", "exact", 9)
def _median(chart: _Chart) -> Outputs:
    return [chart.out("median", median(chart.close, chart.period))]


@_builtin("tv-momentum", "Momentum", "exact", 10)
def _momentum(chart: _Chart) -> Outputs:
    close, period = chart.close, chart.period
    return [chart.out("momentum", [value - close[i - period] if i >= period else None for i, value in enumerate(close)])]
