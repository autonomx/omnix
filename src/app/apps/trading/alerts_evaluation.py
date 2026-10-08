"""Pure alert condition evaluation on bars (TVP-1.1, TVP-1.2).

An alert is evaluated at one bar ``k``: the last final bar when the alert
fires only on closed bars (``once_per_bar_close``, or ``allow_partial_bars``
false), otherwise the last bar, which may still be forming. Crossing and
channel operators compare bar ``k`` with bar ``k - 1``; moving operators
compare bar ``k`` with bar ``k - bars``. A value that is missing (indicator
warm-up, not enough bars, a zero base) makes its condition false. All
conditions must hold (AND).

Values are compared as ``Decimal``: price fields come from the bars exactly,
indicator values from the server registry (``indicators/registry.py``, the
same numbers the chart plots) through their shortest decimal representation.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from .alert_conditions import (
    MOVING_OPERATORS,
    AlertConditionSpec,
    ChangePercentSource,
    ChannelTarget,
    IndicatorSource,
    PriceSource,
    SourceTarget,
    TrendlineSource,
    ValueTarget,
    condition_sources,
    indicator_output_profile,
)
from .indicators.registry import BarSeries, compute_indicator

HISTORY_LIMIT_MAX = 1000
_HUNDRED = Decimal("100")


class AlertBar(Protocol):
    @property
    def start_time(self) -> datetime: ...
    @property
    def end_time(self) -> datetime: ...
    @property
    def open(self) -> Any: ...
    @property
    def high(self) -> Any: ...
    @property
    def low(self) -> Any: ...
    @property
    def close(self) -> Any: ...
    @property
    def volume(self) -> Any: ...
    @property
    def is_final(self) -> bool: ...


Pair = tuple[Decimal | None, Decimal | None]  # (previous, current)


@dataclass(frozen=True)
class ConditionObservation:
    position: int
    operator: str
    met: bool
    source: Decimal | None
    source_previous: Decimal | None = None
    target: Decimal | None = None
    target_previous: Decimal | None = None
    upper: Decimal | None = None
    lower: Decimal | None = None
    upper_previous: Decimal | None = None
    lower_previous: Decimal | None = None
    base: Decimal | None = None

    def payload(self) -> dict[str, Any]:
        values = {
            "source": self.source,
            "source_previous": self.source_previous,
            "target": self.target,
            "target_previous": self.target_previous,
            "upper": self.upper,
            "lower": self.lower,
            "upper_previous": self.upper_previous,
            "lower_previous": self.lower_previous,
            "base": self.base,
        }
        return {
            "position": self.position,
            "operator": self.operator,
            "met": self.met,
            **{name: str(value) for name, value in values.items() if value is not None},
        }


@dataclass(frozen=True)
class AlertConditionOutcome:
    """The result of evaluating every condition of one alert at one bar."""

    met: bool
    bar_start: datetime
    bar_end: datetime
    bar_is_final: bool
    close: Decimal
    volume: Decimal
    observations: tuple[ConditionObservation, ...] = field(default_factory=tuple)
    bar_index: int | None = None

    @property
    def primary_value(self) -> Decimal | None:
        return self.observations[0].source if self.observations else None

    def observation_payload(self) -> list[dict[str, Any]]:
        return [observation.payload() for observation in self.observations]


# --- Operators -----------------------------------------------------------------


def _inside(value: Decimal, lower: Decimal, upper: Decimal) -> bool:
    low, high = (lower, upper) if lower <= upper else (upper, lower)
    return low <= value <= high


def operator_met(
    operator: str,
    source: Pair,
    *,
    target: Pair = (None, None),
    upper: Pair = (None, None),
    lower: Pair = (None, None),
    base: Decimal | None = None,
    amount: Decimal | None = None,
) -> bool:
    """One operator on (previous, current) values; any missing value is false."""
    previous, current = source
    if current is None:
        return False
    if operator in MOVING_OPERATORS:
        if base is None or amount is None:
            return False
        if operator == "moving_up":
            return current - base >= amount
        if operator == "moving_down":
            return base - current >= amount
        if base == 0:
            return False
        change = (current - base) / abs(base) * _HUNDRED
        return change >= amount if operator == "moving_up_percent" else -change >= amount
    if operator in {"greater_than", "less_than"}:
        if target[1] is None:
            return False
        return current > target[1] if operator == "greater_than" else current < target[1]
    if operator in {"crossing", "crossing_up", "crossing_down"}:
        previous_target, current_target = target
        if previous is None or previous_target is None or current_target is None:
            return False
        up = previous < previous_target and current >= current_target
        down = previous > previous_target and current <= current_target
        if operator == "crossing_up":
            return up
        if operator == "crossing_down":
            return down
        return up or down
    # Channel operators.
    if upper[1] is None or lower[1] is None:
        return False
    inside_now = _inside(current, lower[1], upper[1])
    if operator == "inside_channel":
        return inside_now
    if operator == "outside_channel":
        return not inside_now
    if previous is None or upper[0] is None or lower[0] is None:
        return False
    inside_before = _inside(previous, lower[0], upper[0])
    if operator == "entering_channel":
        return inside_now and not inside_before
    return inside_before and not inside_now  # exiting_channel


# --- Values --------------------------------------------------------------------


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return Decimal(repr(value))
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


class _BarValues:
    """Source values at bar indexes of one bar list, with per-source caches."""

    def __init__(self, bars: Sequence[AlertBar]) -> None:
        self.bars = bars
        self._series: BarSeries | None = None
        self._indicator_cache: dict[tuple[Any, ...], dict[int, float]] = {}

    def series(self) -> BarSeries:
        if self._series is None:
            self._series = BarSeries.from_bars(self.bars)
        return self._series

    def value(self, source: Any, index: int) -> Decimal | None:
        if index < 0 or index >= len(self.bars):
            return None
        if isinstance(source, PriceSource):
            return self._price(source.field, index)
        if isinstance(source, ChangePercentSource):
            base_index = index - source.lookback_bars
            if base_index < 0:
                return None
            previous = _decimal(self.bars[base_index].close)
            current = _decimal(self.bars[index].close)
            if previous is None or current is None or previous == 0:
                return None
            return (current / previous - Decimal("1")) * _HUNDRED
        if isinstance(source, TrendlineSource):
            return _trendline_value(source, self.bars[index].end_time)
        if isinstance(source, IndicatorSource):
            return self._indicator(source, index)
        return None

    def _price(self, name: str, index: int) -> Decimal | None:
        bar = self.bars[index]
        if name in {"close", "open", "high", "low", "volume"}:
            return _decimal(getattr(bar, name))
        high, low, close = _decimal(bar.high), _decimal(bar.low), _decimal(bar.close)
        if high is None or low is None or close is None:
            return None
        if name == "hl2":
            return (high + low) / 2
        if name == "hlc3":
            return (high + low + close) / 3
        opening = _decimal(bar.open)
        return None if opening is None else (opening + high + low + close) / 4

    def _indicator(self, source: IndicatorSource, index: int) -> Decimal | None:
        anchor_bars_ago = source.inputs.anchor_bars_ago
        anchor_time: str | None = None
        if anchor_bars_ago is not None:
            anchor_index = max(0, index - anchor_bars_ago)
            anchor_time = self.bars[anchor_index].start_time.astimezone(timezone.utc).isoformat()
        cache_key = (source.model_dump_json(), anchor_time)
        points = self._indicator_cache.get(cache_key)
        if points is None:
            points = self._compute_indicator(source, anchor_time)
            self._indicator_cache[cache_key] = points
        value = points.get(index)
        return None if value is None else _decimal(value)

    def _compute_indicator(self, source: IndicatorSource, anchor_time: str | None) -> dict[int, float]:
        try:
            outputs = compute_indicator(source.indicator_id, self.series(), source.inputs.registry_inputs(anchor_time))
        except (KeyError, ValueError, TypeError, ZeroDivisionError):
            return {}
        chosen = next((output for output in outputs if output.key == source.output), None)
        if chosen is None and anchor_time is not None:
            # A moving anchor changes the key (vwap:<anchor>); the output keeps its position.
            keys = [key for key, _ in indicator_output_profile(source)]
            if source.output in keys and len(outputs) == len(keys):
                chosen = outputs[keys.index(source.output)]
        if chosen is None:
            return {}
        return {index: value for index, value in chosen.points}


def _trendline_value(source: TrendlineSource, at: datetime) -> Decimal | None:
    first, second = source.points
    first_time = first.time.astimezone(timezone.utc)
    second_time = second.time.astimezone(timezone.utc)
    duration = Decimal(str((second_time - first_time).total_seconds()))
    if duration == 0:
        return None
    elapsed = Decimal(str((at.astimezone(timezone.utc) - first_time).total_seconds()))
    return first.price + (second.price - first.price) * elapsed / duration


def _target_pair(values: _BarValues, bound: Any, index: int) -> Pair:
    if isinstance(bound, ValueTarget):
        return (bound.value, bound.value)
    if isinstance(bound, SourceTarget):
        return (values.value(bound.source, index - 1), values.value(bound.source, index))
    return (None, None)


def _evaluate_condition(values: _BarValues, position: int, condition: AlertConditionSpec, index: int) -> ConditionObservation:
    source = (values.value(condition.source, index - 1), values.value(condition.source, index))
    target: Pair = (None, None)
    upper: Pair = (None, None)
    lower: Pair = (None, None)
    base: Decimal | None = None
    if condition.operator in MOVING_OPERATORS:
        base = values.value(condition.source, index - (condition.bars or 1))
    elif isinstance(condition.target, ChannelTarget):
        upper = _target_pair(values, condition.target.upper, index)
        lower = _target_pair(values, condition.target.lower, index)
    else:
        target = _target_pair(values, condition.target, index)
    met = operator_met(
        condition.operator, source, target=target, upper=upper, lower=lower, base=base, amount=condition.amount
    )
    return ConditionObservation(
        position=position,
        operator=condition.operator,
        met=met,
        source=source[1],
        source_previous=source[0],
        target=target[1],
        target_previous=target[0],
        upper=upper[1],
        lower=lower[1],
        upper_previous=upper[0],
        lower_previous=lower[0],
        base=base,
    )


def evaluation_index(bars: Sequence[AlertBar], *, final_only: bool) -> int | None:
    """The bar to evaluate: the last bar, or the last final bar when only closed bars count."""
    if not bars:
        return None
    if not final_only:
        return len(bars) - 1
    for index in range(len(bars) - 1, -1, -1):
        if bars[index].is_final:
            return index
    return None


def evaluate_conditions(
    conditions: Sequence[AlertConditionSpec],
    bars: Sequence[AlertBar],
    *,
    final_only: bool,
) -> AlertConditionOutcome | None:
    """Evaluate every condition at the evaluation bar; ``None`` when there is no bar to evaluate."""
    index = evaluation_index(bars, final_only=final_only)
    if index is None:
        return None
    # Indicators see bars up to the evaluated bar only, so a forming bar after it cannot leak in.
    values = _BarValues(bars[: index + 1])
    observations = tuple(_evaluate_condition(values, position, condition, index) for position, condition in enumerate(conditions))
    bar = bars[index]
    return AlertConditionOutcome(
        met=bool(observations) and all(observation.met for observation in observations),
        bar_start=bar.start_time,
        bar_end=bar.end_time,
        bar_is_final=bool(bar.is_final),
        close=_decimal(bar.close) or Decimal("0"),
        volume=_decimal(bar.volume) or Decimal("0"),
        observations=observations,
        bar_index=index,
    )


# --- History -------------------------------------------------------------------


def _source_lookback(source: Any) -> int:
    if isinstance(source, ChangePercentSource):
        return source.lookback_bars
    if not isinstance(source, IndicatorSource):
        return 0
    inputs = source.inputs
    periods = [value for value in (inputs.period, inputs.fast_period, inputs.slow_period, inputs.signal_period) if value]
    required = math.ceil(max(periods, default=1))
    if source.indicator_id == "macd":
        required = max(required, math.ceil((inputs.slow_period or 26) + (inputs.signal_period or 9)))
    elif source.indicator_id == "stochastic-rsi":
        required = max(
            required,
            math.ceil(2 * (inputs.period or 14) + (inputs.fast_period or 3) + (inputs.signal_period or 3)),
        )
    if inputs.anchor_bars_ago is not None:
        required = max(required, inputs.anchor_bars_ago + 1)
    try:
        # The first bar this output has a value on, measured on a synthetic series,
        # covers indicators whose warm-up is not a simple function of the period.
        first_valid = dict(indicator_output_profile(source)).get(source.output)
    except (KeyError, ValueError, TypeError, ZeroDivisionError):
        first_valid = None
    if first_valid is not None:
        required = max(required, first_valid + 1)
    return required


def required_bars(conditions: Sequence[AlertConditionSpec]) -> int:
    """Bars the conditions need before the evaluated bar has a value and a previous value."""
    required = 1
    for condition in conditions:
        lookback = max(_source_lookback(source) for source in condition_sources(condition))
        if condition.operator in MOVING_OPERATORS:
            lookback += condition.bars or 1
        else:
            lookback += 1  # the previous bar
        required = max(required, lookback)
    return required


def history_limit(required: int) -> int:
    """Bars to fetch: the requirement plus a warm-up so recursive indicators converge.

    ``min(1000, max(required + 2, 3 * required + 50))``: recursive indicators
    (EMA, RSI, ATR, MACD...) depend on every earlier bar, so three times the
    requirement plus 50 bars keeps their seed's influence negligible, and the
    extra two bars leave room for a forming bar after the last final bar.
    """
    return min(HISTORY_LIMIT_MAX, max(required + 2, 3 * required + 50))


__all__ = [
    "HISTORY_LIMIT_MAX",
    "AlertBar",
    "AlertConditionOutcome",
    "ConditionObservation",
    "evaluate_conditions",
    "evaluation_index",
    "history_limit",
    "operator_met",
    "required_bars",
]
