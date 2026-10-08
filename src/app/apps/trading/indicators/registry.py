"""Server indicator registry (TVP-0.2).

Chart indicators computed on the server with the same results as the browser
engine (``web/src/features/trading/indicators``), so alerts, the screener and
scripts can use any indicator a chart shows. Equality is proved by the shared
goldens in ``resources/trading/indicator_goldens``.

This module is separate from ``engine.py``: strategies use ``engine.py``
(``Decimal``) as part of their evidence, and it stays unchanged.
"""

from __future__ import annotations

import importlib
import math
import pkgutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

NumericClass = Literal["exact", "recursive", "transcendental"]


class _BarLike(Protocol):
    @property
    def start_time(self) -> datetime: ...
    @property
    def open(self) -> object: ...
    @property
    def high(self) -> object: ...
    @property
    def low(self) -> object: ...
    @property
    def close(self) -> object: ...
    @property
    def volume(self) -> object: ...


def _number(value: object) -> float:
    # Mirrors the browser's Number(value) for decimal strings and Decimals; non-finite becomes 0 like `nums()`.
    try:
        number = float(str(value))
    except ValueError:
        return 0.0
    return number if math.isfinite(number) else 0.0


@dataclass(frozen=True)
class BarSeries:
    start_times: tuple[datetime, ...]
    open: tuple[float, ...]
    high: tuple[float, ...]
    low: tuple[float, ...]
    close: tuple[float, ...]
    volume: tuple[float, ...]

    def __len__(self) -> int:
        return len(self.close)

    @classmethod
    def from_bars(cls, bars: Sequence[_BarLike]) -> BarSeries:
        return cls(
            start_times=tuple(bar.start_time for bar in bars),
            open=tuple(_number(bar.open) for bar in bars),
            high=tuple(_number(bar.high) for bar in bars),
            low=tuple(_number(bar.low) for bar in bars),
            close=tuple(_number(bar.close) for bar in bars),
            volume=tuple(_number(bar.volume) for bar in bars),
        )


@dataclass(frozen=True)
class IndicatorInputs:
    period: int
    fast_period: int | None = None
    slow_period: int | None = None
    signal_period: int | None = None
    standard_deviations: float | None = None


@dataclass(frozen=True)
class IndicatorOutputSeries:
    """One plotted line. Points are (bar index, value); a value may be NaN where the browser plots a non-finite number."""

    key: str
    points: tuple[tuple[int, float], ...]

    def latest(self) -> tuple[int, float] | None:
        return self.points[-1] if self.points else None


ComputeFunction = Callable[[BarSeries, IndicatorInputs], list[IndicatorOutputSeries]]


@dataclass(frozen=True)
class ServerIndicator:
    id: str
    name: str
    numeric_class: NumericClass
    compute: ComputeFunction


_REGISTRY: dict[str, ServerIndicator] = {}
_LOADED = False


def register(indicator_id: str, name: str, numeric_class: NumericClass) -> Callable[[ComputeFunction], ComputeFunction]:
    def decorate(compute: ComputeFunction) -> ComputeFunction:
        if indicator_id in _REGISTRY:
            raise ValueError(f"indicator {indicator_id!r} is registered twice")
        _REGISTRY[indicator_id] = ServerIndicator(indicator_id, name, numeric_class, compute)
        return compute

    return decorate


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    from . import server_indicators

    for module in pkgutil.iter_modules(server_indicators.__path__):
        if not module.name.startswith("_"):
            importlib.import_module(f"{server_indicators.__name__}.{module.name}")
    _LOADED = True


def server_indicator(indicator_id: str) -> ServerIndicator | None:
    _load()
    return _REGISTRY.get(indicator_id)


def server_indicator_ids() -> list[str]:
    _load()
    return sorted(_REGISTRY)


def compute_indicator(indicator_id: str, bars: BarSeries, inputs: IndicatorInputs) -> list[IndicatorOutputSeries]:
    indicator = server_indicator(indicator_id)
    if indicator is None:
        raise KeyError(f"no server implementation for indicator {indicator_id!r}")
    return indicator.compute(bars, inputs)
