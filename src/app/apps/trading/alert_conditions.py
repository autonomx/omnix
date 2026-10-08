"""Alert condition model (TVP-1.2) and alert frequencies (TVP-1.1).

An alert holds one to five conditions, combined with AND. Each condition has a
``source`` (price, percent change, an indicator output from the server
registry, or a trendline), an ``operator`` and, depending on the operator, a
``target`` (a value, a second source, or a channel of two bounds) or a moving
``amount`` within ``bars``.

Alerts created before TVP-1.2 describe their single condition with
``condition_type``, ``threshold`` and ``parameters``. ``legacy_conditions``
turns those fields into the same model with the meaning they have always had,
so evaluation reads one model.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .indicators.registry import BarSeries, IndicatorInputs, compute_indicator, server_indicator

MAX_ALERT_CONDITIONS = 5

AlertFrequency = Literal["once", "every_time", "once_per_bar", "once_per_bar_close", "once_per_minute"]
ALERT_FREQUENCIES: tuple[str, ...] = ("once", "every_time", "once_per_bar", "once_per_bar_close", "once_per_minute")

AlertOperator = Literal[
    "crossing",
    "crossing_up",
    "crossing_down",
    "greater_than",
    "less_than",
    "entering_channel",
    "exiting_channel",
    "inside_channel",
    "outside_channel",
    "moving_up",
    "moving_down",
    "moving_up_percent",
    "moving_down_percent",
]
CHANNEL_OPERATORS = frozenset({"entering_channel", "exiting_channel", "inside_channel", "outside_channel"})
MOVING_OPERATORS = frozenset({"moving_up", "moving_down", "moving_up_percent", "moving_down_percent"})

PriceField = Literal["close", "open", "high", "low", "hl2", "hlc3", "ohlc4", "volume"]


class TrendlineAlertPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time: datetime
    price: Decimal


class PriceSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["price"] = "price"
    field: PriceField = "close"


class ChangePercentSource(BaseModel):
    """Close against the close ``lookback_bars`` earlier, in percent."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["change_percent"] = "change_percent"
    lookback_bars: int = Field(default=1, ge=1, le=500)


class IndicatorSourceInputs(BaseModel):
    """Indicator inputs as the chart stores them.

    ``anchor_bars_ago`` anchors an anchored indicator (VWAP) that many bars
    before the bar being evaluated, so the anchor moves with the bar.
    """

    model_config = ConfigDict(extra="forbid")

    period: int | float = Field(default=14, gt=0, le=1000)
    fast_period: int | float | None = Field(default=None, gt=0, le=1000)
    slow_period: int | float | None = Field(default=None, gt=0, le=1000)
    signal_period: int | float | None = Field(default=None, gt=0, le=1000)
    standard_deviations: float | None = Field(default=None, gt=0, le=100)
    anchor_time: str | None = Field(default=None, max_length=64)
    anchor_bars_ago: int | None = Field(default=None, ge=0, le=999)

    @model_validator(mode="after")
    def validate_anchor(self) -> IndicatorSourceInputs:
        if self.anchor_time is not None and self.anchor_bars_ago is not None:
            raise ValueError("indicator inputs take anchor_time or anchor_bars_ago, not both")
        return self

    def registry_inputs(self, anchor_time: str | None = None) -> IndicatorInputs:
        return IndicatorInputs(
            period=self.period,
            fast_period=self.fast_period,
            slow_period=self.slow_period,
            signal_period=self.signal_period,
            standard_deviations=self.standard_deviations,
            anchor_time=anchor_time if anchor_time is not None else self.anchor_time,
        )


class IndicatorSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["indicator"] = "indicator"
    indicator_id: str = Field(min_length=1, max_length=120)
    inputs: IndicatorSourceInputs = Field(default_factory=IndicatorSourceInputs)
    output: str = Field(min_length=1, max_length=240)


class TrendlineSource(BaseModel):
    """A line through two points; its value at a bar is the line at the bar's end time."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["trendline"] = "trendline"
    points: list[TrendlineAlertPoint] = Field(min_length=2, max_length=2)


AlertSource = Annotated[
    PriceSource | ChangePercentSource | IndicatorSource | TrendlineSource,
    Field(discriminator="kind"),
]


class ValueTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["value"] = "value"
    value: Decimal


class SourceTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["source"] = "source"
    source: AlertSource


ChannelBound = Annotated[ValueTarget | SourceTarget, Field(discriminator="kind")]


class ChannelTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["channel"] = "channel"
    upper: ChannelBound
    lower: ChannelBound


AlertTarget = Annotated[ValueTarget | SourceTarget | ChannelTarget, Field(discriminator="kind")]


class AlertConditionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: AlertSource
    operator: AlertOperator
    target: AlertTarget | None = None
    amount: Decimal | None = None
    bars: int | None = Field(default=None, ge=1, le=500)

    @model_validator(mode="after")
    def validate_operator_contract(self) -> AlertConditionSpec:
        if self.operator in MOVING_OPERATORS:
            if self.target is not None:
                raise ValueError(f"{self.operator} takes an amount and bars, not a target")
            if self.amount is None or self.amount <= 0:
                raise ValueError(f"{self.operator} needs an amount greater than zero")
            if self.bars is None:
                raise ValueError(f"{self.operator} needs bars of at least 1")
            return self
        if self.amount is not None or self.bars is not None:
            raise ValueError(f"{self.operator} does not take an amount or bars")
        if self.target is None:
            raise ValueError(f"{self.operator} needs a target")
        is_channel = isinstance(self.target, ChannelTarget)
        if self.operator in CHANNEL_OPERATORS and not is_channel:
            raise ValueError(f"{self.operator} needs a channel target")
        if self.operator not in CHANNEL_OPERATORS and is_channel:
            raise ValueError(f"a channel target needs a channel operator, not {self.operator}")
        return self


def condition_sources(condition: AlertConditionSpec) -> list[Any]:
    """Every source a condition reads: its own and those inside its target."""
    sources: list[Any] = [condition.source]
    target = condition.target
    if isinstance(target, SourceTarget):
        sources.append(target.source)
    elif isinstance(target, ChannelTarget):
        sources.extend(bound.source for bound in (target.upper, target.lower) if isinstance(bound, SourceTarget))
    return sources


# --- Indicator registry checks -------------------------------------------------

_SYNTHETIC_BARS = 1200


class _SyntheticBar:
    __slots__ = ("start_time", "open", "high", "low", "close", "volume")

    def __init__(self, index: int, previous_close: float) -> None:
        close = 100 + 10 * math.sin(index / 7) + 3 * math.sin(index / 2.3) + index * 0.01
        self.start_time = datetime(2000, 1, 3, tzinfo=timezone.utc) + timedelta(minutes=index)
        self.open = previous_close
        self.high = max(previous_close, close) + 0.5 + (index % 3) * 0.1
        self.low = min(previous_close, close) - 0.5 - (index % 5) * 0.1
        self.close = close
        self.volume = 1000 + (index % 11) * 37


@lru_cache(maxsize=1)
def _synthetic_series() -> BarSeries:
    bars: list[_SyntheticBar] = []
    previous = 100.0
    for index in range(_SYNTHETIC_BARS):
        bar = _SyntheticBar(index, previous)
        previous = bar.close
        bars.append(bar)
    return BarSeries.from_bars(bars)


def _inputs_key(inputs: IndicatorSourceInputs) -> tuple[Any, ...]:
    return (
        inputs.period,
        inputs.fast_period,
        inputs.slow_period,
        inputs.signal_period,
        inputs.standard_deviations,
        inputs.anchor_time,
    )


@lru_cache(maxsize=512)
def _output_profile(indicator_id: str, inputs_key: tuple[Any, ...]) -> tuple[tuple[str, int | None], ...]:
    period, fast, slow, signal, deviations, anchor_time = inputs_key
    outputs = compute_indicator(
        indicator_id,
        _synthetic_series(),
        IndicatorInputs(
            period=period,
            fast_period=fast,
            slow_period=slow,
            signal_period=signal,
            standard_deviations=deviations,
            anchor_time=anchor_time,
        ),
    )
    profile: list[tuple[str, int | None]] = []
    for output in outputs:
        first = next((index for index, value in output.points if math.isfinite(value)), None)
        profile.append((output.key, first))
    return tuple(profile)


def indicator_output_profile(source: IndicatorSource) -> tuple[tuple[str, int | None], ...]:
    """The output keys an indicator produces for these inputs, with each key's first valid bar.

    Computed once per (indicator, inputs) on a synthetic series. ``anchor_bars_ago``
    is left out: its keys are those of the unanchored indicator.
    """
    return _output_profile(source.indicator_id, _inputs_key(source.inputs))


def validate_indicator_source(source: IndicatorSource) -> None:
    if server_indicator(source.indicator_id) is None:
        raise ValueError(f"indicator {source.indicator_id!r} is not available on the server")
    try:
        profile = indicator_output_profile(source)
    except (ValueError, TypeError, ZeroDivisionError) as exc:
        raise ValueError(f"invalid inputs for indicator {source.indicator_id!r}: {exc}") from exc
    keys = [key for key, _ in profile]
    if source.output not in keys:
        raise ValueError(
            f"indicator {source.indicator_id!r} has no output {source.output!r}; outputs: {', '.join(keys) or 'none'}"
        )


def validate_conditions_against_registry(conditions: list[AlertConditionSpec]) -> None:
    for condition in conditions:
        for source in condition_sources(condition):
            if isinstance(source, IndicatorSource):
                validate_indicator_source(source)


# --- Legacy adapter ------------------------------------------------------------

LegacyAlertCondition = Literal[
    "price_above",
    "price_below",
    "percent_change_above",
    "percent_change_below",
    "indicator_above",
    "indicator_below",
    "indicator_cross_above",
    "indicator_cross_below",
    "volume_above",
    "volume_below",
    "trendline_crossing",
    "trendline_crossing_up",
    "trendline_crossing_down",
    "trendline_above",
    "trendline_below",
]

_TRENDLINE_OPERATORS: dict[str, AlertOperator] = {
    "trendline_crossing": "crossing",
    "trendline_crossing_up": "crossing_up",
    "trendline_crossing_down": "crossing_down",
    # Before TVP-1.2 "above"/"below" trendline alerts fired on the crossing, and they still do.
    "trendline_above": "crossing_up",
    "trendline_below": "crossing_down",
}


def legacy_indicator_source(parameters: Any) -> IndicatorSource:
    """The registry indicator a pre-TVP-1.2 indicator alert means."""
    indicator_id = parameters.indicator_id
    period = parameters.period
    component = parameters.component
    if indicator_id in {"sma", "ema", "rsi", "atr"}:
        return IndicatorSource(indicator_id=indicator_id, inputs=IndicatorSourceInputs(period=period), output=f"{indicator_id}:{period}")
    if indicator_id == "bollinger":
        band = component if component in {"upper", "middle", "lower"} else "middle"
        return IndicatorSource(
            indicator_id="bollinger",
            inputs=IndicatorSourceInputs(period=period, standard_deviations=2.0),
            output=f"bollinger:{period}:{band}",
        )
    if indicator_id == "macd":
        line = component if component in {"line", "signal", "histogram"} else "line"
        fast, slow = parameters.fast_period, parameters.slow_period
        return IndicatorSource(
            indicator_id="macd",
            inputs=IndicatorSourceInputs(period=period, fast_period=fast, slow_period=slow, signal_period=parameters.signal_period),
            output=f"macd:{fast}:{slow}:{line}",
        )
    if indicator_id == "stochastic-rsi":
        return IndicatorSource(
            indicator_id="stochastic-rsi",
            inputs=IndicatorSourceInputs(period=period, fast_period=parameters.fast_period, signal_period=parameters.signal_period),
            output="stochastic-rsi:k",
        )
    if indicator_id == "vwap":
        return IndicatorSource(
            indicator_id="vwap",
            inputs=IndicatorSourceInputs(period=1, anchor_bars_ago=parameters.anchor_bars_ago),
            output="vwap:dataset",
        )
    raise ValueError(f"unsupported legacy indicator {indicator_id!r}")


def legacy_conditions(condition_type: str, threshold: Decimal, parameters: Any) -> list[AlertConditionSpec]:
    """Conditions with the meaning a pre-TVP-1.2 alert has always had.

    Every legacy family fires on a crossing: "_above" types when the value
    crosses up through the threshold, "_below" types when it crosses down.
    """
    if condition_type.startswith("trendline_"):
        points = parameters.trendline_points
        if points is None or len(points) != 2:
            raise ValueError("trendline conditions require two trendline points")
        return [
            AlertConditionSpec(
                source=PriceSource(field="close"),
                operator=_TRENDLINE_OPERATORS[condition_type],
                target=SourceTarget(source=TrendlineSource(points=list(points))),
            )
        ]
    operator: AlertOperator = "crossing_up" if condition_type.endswith("_above") else "crossing_down"
    source: Any
    if condition_type.startswith("price_"):
        source = PriceSource(field="close")
    elif condition_type.startswith("volume_"):
        source = PriceSource(field="volume")
    elif condition_type.startswith("percent_change_"):
        source = ChangePercentSource(lookback_bars=parameters.lookback_bars)
    elif condition_type.startswith("indicator_"):
        source = legacy_indicator_source(parameters)
    else:
        raise ValueError(f"unsupported legacy condition type {condition_type!r}")
    return [AlertConditionSpec(source=source, operator=operator, target=ValueTarget(value=threshold))]


__all__ = [
    "ALERT_FREQUENCIES",
    "CHANNEL_OPERATORS",
    "MAX_ALERT_CONDITIONS",
    "MOVING_OPERATORS",
    "AlertConditionSpec",
    "AlertFrequency",
    "AlertOperator",
    "AlertSource",
    "AlertTarget",
    "ChangePercentSource",
    "ChannelTarget",
    "IndicatorSource",
    "IndicatorSourceInputs",
    "LegacyAlertCondition",
    "PriceSource",
    "SourceTarget",
    "TrendlineAlertPoint",
    "TrendlineSource",
    "ValueTarget",
    "condition_sources",
    "indicator_output_profile",
    "legacy_conditions",
    "legacy_indicator_source",
    "validate_conditions_against_registry",
    "validate_indicator_source",
]
