"""Server ports of the chart's core indicators (``coreIndicators.ts``) that the built-in catalog aliases.

The core functions differ from the built-in helpers in ``_helpers.py`` (warm-up
trimming and operation order), so they are ported separately.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from ..registry import BarSeries, IndicatorInputs, IndicatorOutputSeries, register
from ._helpers import js_max, js_min, js_sum


def _validate_period(period: int) -> None:
    if not isinstance(period, int) or isinstance(period, bool) or period < 1:
        raise ValueError("Indicator period must be a positive integer")


def _points(start_index: int, values: Sequence[float]) -> tuple[tuple[int, float], ...]:
    return tuple((start_index + offset, value) for offset, value in enumerate(values))


def simple_moving_average(values: Sequence[float], period: int) -> list[float]:
    _validate_period(period)
    if len(values) < period:
        return []
    total = js_sum(values[:period])
    result = [total / period]
    for index in range(period, len(values)):
        total += values[index] - values[index - period]
        result.append(total / period)
    return result


def exponential_moving_average(values: Sequence[float], period: int) -> list[float]:
    _validate_period(period)
    if len(values) < period:
        return []
    average = js_sum(values[:period]) / period
    multiplier = 2 / (period + 1)
    result = [average]
    for value in values[period:]:
        average = (value - average) * multiplier + average
        result.append(average)
    return result


def relative_strength_index(values: Sequence[float], period: int) -> list[float]:
    _validate_period(period)
    if len(values) <= period:
        return []
    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, len(values)):
        change = values[index] - values[index - 1]
        gains.append(js_max(change, 0.0))
        losses.append(js_max(-change, 0.0))
    average_gain = js_sum(gains[:period]) / period
    average_loss = js_sum(losses[:period]) / period

    def value() -> float:
        return 100.0 if average_loss == 0 else 100 - 100 / (1 + average_gain / average_loss)

    result = [value()]
    for index in range(period, len(gains)):
        average_gain = (average_gain * (period - 1) + gains[index]) / period
        average_loss = (average_loss * (period - 1) + losses[index]) / period
        result.append(value())
    return result


def _closes(bars: BarSeries) -> list[float]:
    return list(bars.close)


@register("sma", "Simple Moving Average", "exact")
def _sma(bars: BarSeries, inputs: IndicatorInputs) -> list[IndicatorOutputSeries]:
    values = simple_moving_average(_closes(bars), inputs.period)
    return [IndicatorOutputSeries(f"sma:{inputs.period}", _points(inputs.period - 1, values))]


@register("ema", "Exponential Moving Average", "recursive")
def _ema(bars: BarSeries, inputs: IndicatorInputs) -> list[IndicatorOutputSeries]:
    values = exponential_moving_average(_closes(bars), inputs.period)
    return [IndicatorOutputSeries(f"ema:{inputs.period}", _points(inputs.period - 1, values))]


@register("rsi", "Relative Strength Index (RSI)", "recursive")
def _rsi(bars: BarSeries, inputs: IndicatorInputs) -> list[IndicatorOutputSeries]:
    values = relative_strength_index(_closes(bars), inputs.period)
    return [IndicatorOutputSeries(f"rsi:{inputs.period}", _points(inputs.period, values))]


@register("bollinger", "Bollinger Bands (BB)", "exact")
def _bollinger(bars: BarSeries, inputs: IndicatorInputs) -> list[IndicatorOutputSeries]:
    period = inputs.period
    deviations = 2.0 if inputs.standard_deviations is None else inputs.standard_deviations
    _validate_period(period)
    if not math.isfinite(deviations) or deviations <= 0:
        raise ValueError("Bollinger deviation must be positive")
    values = _closes(bars)
    upper: list[float] = []
    middle: list[float] = []
    lower: list[float] = []
    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        center = js_sum(window) / period
        variance = js_sum([(value - center) * (value - center) for value in window]) / period
        deviation = math.sqrt(variance) * deviations
        middle.append(center)
        upper.append(center + deviation)
        lower.append(center - deviation)
    start = period - 1
    return [
        IndicatorOutputSeries(f"bollinger:{period}:upper", _points(start, upper)),
        IndicatorOutputSeries(f"bollinger:{period}:middle", _points(start, middle)),
        IndicatorOutputSeries(f"bollinger:{period}:lower", _points(start, lower)),
    ]


@register("atr", "Average True Range (ATR)", "recursive")
def _atr(bars: BarSeries, inputs: IndicatorInputs) -> list[IndicatorOutputSeries]:
    period = inputs.period
    _validate_period(period)
    highs, lows, closes = bars.high, bars.low, bars.close
    ranges = [
        high - lows[index]
        if index == 0
        else js_max(high - lows[index], abs(high - closes[index - 1]), abs(lows[index] - closes[index - 1]))
        for index, high in enumerate(highs)
    ]
    values: list[float] = []
    if len(ranges) >= period:
        average = js_sum(ranges[:period]) / period
        values.append(average)
        for value in ranges[period:]:
            average = (average * (period - 1) + value) / period
            values.append(average)
    return [IndicatorOutputSeries(f"atr:{period}", _points(period - 1, values))]


@register("macd", "Moving average convergence divergence (MACD) indicator", "recursive")
def _macd(bars: BarSeries, inputs: IndicatorInputs) -> list[IndicatorOutputSeries]:
    fast = 12 if inputs.fast_period is None else inputs.fast_period
    slow = 26 if inputs.slow_period is None else inputs.slow_period
    signal_period = 9 if inputs.signal_period is None else inputs.signal_period
    for period in (fast, slow, signal_period):
        _validate_period(period)
    if fast >= slow:
        raise ValueError("MACD fast period must be smaller than slow period")
    values = _closes(bars)
    fast_line = exponential_moving_average(values, fast)
    slow_line = exponential_moving_average(values, slow)
    macd: list[float] = []
    signal: list[float] = []
    if slow_line:
        macd = [fast_line[index + slow - fast] - slow_value for index, slow_value in enumerate(slow_line)]
        signal = exponential_moving_average(macd, signal_period)
    lines = [macd[index + signal_period - 1] for index in range(len(signal))]
    histogram = [line - signal_value for line, signal_value in zip(lines, signal, strict=True)]
    start = slow + signal_period - 2
    return [
        IndicatorOutputSeries(f"macd:{fast}:{slow}:line", _points(start, lines)),
        IndicatorOutputSeries(f"macd:{fast}:{slow}:signal", _points(start, signal)),
        IndicatorOutputSeries(f"macd:{fast}:{slow}:histogram", _points(start, histogram)),
    ]


@register("vwap", "Volume Weighted Average Price (VWAP)", "exact")
def _vwap(bars: BarSeries, inputs: IndicatorInputs) -> list[IndicatorOutputSeries]:
    cumulative_price_volume = 0.0
    cumulative_volume = 0.0
    values: list[float] = []
    for high, low, close, volume in zip(bars.high, bars.low, bars.close, bars.volume, strict=True):
        typical = (high + low + close) / 3
        cumulative_price_volume += typical * volume
        cumulative_volume += volume
        values.append(typical if cumulative_volume == 0 else cumulative_price_volume / cumulative_volume)
    return [IndicatorOutputSeries("vwap:dataset", _points(0, values))]


@register("stochastic-rsi", "Stochastic RSI (STOCH RSI)", "recursive")
def _stochastic_rsi(bars: BarSeries, inputs: IndicatorInputs) -> list[IndicatorOutputSeries]:
    period = inputs.period or 14
    smoothing = inputs.fast_period or 3
    signal = inputs.signal_period or 3
    rsi = relative_strength_index(_closes(bars), period)
    raw: list[float] = []
    if len(rsi) >= period:
        for index in range(len(rsi) - period + 1):
            window = rsi[index : index + period]
            minimum = js_min(*window)
            maximum = js_max(*window)
            value = rsi[index + period - 1]
            raw.append(50.0 if maximum == minimum else js_max(0.0, js_min(100.0, (value - minimum) / (maximum - minimum) * 100)))
    k = simple_moving_average(raw, smoothing)
    d = simple_moving_average(k, signal)
    start = period + period - 1 + smoothing - 1 + signal - 1

    def bounded(value: float) -> float:
        return js_max(0.0, js_min(100.0, value))

    k_points = [bounded(value) for value in k[signal - 1 :]] if d else []
    return [
        IndicatorOutputSeries("stochastic-rsi:k", _points(start, k_points)),
        IndicatorOutputSeries("stochastic-rsi:d", _points(start, [bounded(value) for value in d])),
    ]


@register("rsi-divergence", "RSI divergence indicator", "recursive")
def _rsi_divergence(bars: BarSeries, inputs: IndicatorInputs) -> list[IndicatorOutputSeries]:
    fast = 5 if inputs.fast_period is None else inputs.fast_period
    slow = inputs.period or 14
    values = _closes(bars)
    fast_rsi = relative_strength_index(values, fast)
    slow_rsi = relative_strength_index(values, slow)

    def fast_at(index: int) -> float:
        # The browser reads past the array as undefined, which becomes NaN.
        return fast_rsi[index] if 0 <= index < len(fast_rsi) else math.nan

    divergence = [fast_at(index + slow - fast) - value for index, value in enumerate(slow_rsi)]
    return [IndicatorOutputSeries("rsi-divergence:value", _points(slow, divergence))]
