from __future__ import annotations

from decimal import Decimal
from typing import Iterable


CORE_INDICATOR_FORMULA_VERSION = "omnix-indicators-v1"


def _values(values: Iterable[Decimal | float | int | str]) -> list[Decimal]:
    return [value if isinstance(value, Decimal) else Decimal(str(value)) for value in values]


def _period(period: int) -> int:
    clean = int(period)
    if clean < 1:
        raise ValueError("Indicator period must be positive")
    return clean


def simple_moving_average(values: Iterable[Decimal | float | int | str], period: int) -> list[Decimal]:
    data = _values(values)
    clean_period = _period(period)
    if len(data) < clean_period:
        return []
    running = sum(data[:clean_period], Decimal("0"))
    result = [running / clean_period]
    for index in range(clean_period, len(data)):
        running += data[index] - data[index - clean_period]
        result.append(running / clean_period)
    return result


def exponential_moving_average(values: Iterable[Decimal | float | int | str], period: int) -> list[Decimal]:
    data = _values(values)
    clean_period = _period(period)
    if len(data) < clean_period:
        return []
    average = sum(data[:clean_period], Decimal("0")) / clean_period
    multiplier = Decimal("2") / Decimal(clean_period + 1)
    result = [average]
    for value in data[clean_period:]:
        average = (value - average) * multiplier + average
        result.append(average)
    return result


def relative_strength_index(values: Iterable[Decimal | float | int | str], period: int) -> list[Decimal]:
    data = _values(values)
    clean_period = _period(period)
    if len(data) <= clean_period:
        return []
    gains: list[Decimal] = []
    losses: list[Decimal] = []
    for previous, current in zip(data, data[1:]):
        change = current - previous
        gains.append(max(change, Decimal("0")))
        losses.append(max(-change, Decimal("0")))
    average_gain = sum(gains[:clean_period], Decimal("0")) / clean_period
    average_loss = sum(losses[:clean_period], Decimal("0")) / clean_period

    def value() -> Decimal:
        if average_loss == 0:
            return Decimal("100")
        strength = average_gain / average_loss
        return Decimal("100") - Decimal("100") / (Decimal("1") + strength)

    result = [value()]
    for gain, loss in zip(gains[clean_period:], losses[clean_period:]):
        average_gain = (average_gain * (clean_period - 1) + gain) / clean_period
        average_loss = (average_loss * (clean_period - 1) + loss) / clean_period
        result.append(value())
    return result
