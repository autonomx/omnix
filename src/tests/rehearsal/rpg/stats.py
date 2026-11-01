"""Proportions with Wilson 95% bounds and percentiles, for the RPG harnesses' reports."""
from __future__ import annotations

import math
from typing import Sequence

Z95 = 1.959964


def wilson_interval(successes: int, trials: int, z: float = Z95) -> tuple[float, float]:
    """The 95% Wilson score interval for a proportion; (0, 0) without trials."""
    if trials <= 0:
        return 0.0, 0.0
    phat = successes / trials
    denominator = 1 + z * z / trials
    centre = (phat + z * z / (2 * trials)) / denominator
    margin = z * math.sqrt(phat * (1 - phat) / trials + z * z / (4 * trials * trials)) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def proportion(successes: int, trials: int) -> dict[str, float | int | None]:
    """A metric with its own denominator: rate and Wilson 95% bounds."""
    lower, upper = wilson_interval(successes, trials)
    return {"successes": successes, "n": trials, "rate": round(successes / trials, 4) if trials else None,
            "wilson_lower": round(lower, 4), "wilson_upper": round(upper, 4)}


def percentile(values: Sequence[float], fraction: float) -> float | None:
    """Nearest-rank percentile; None without values."""
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return round(float(ordered[index]), 1)


def summary(values: Sequence[float]) -> dict[str, float | int | None]:
    return {"n": len(values), "p50": percentile(values, 0.5), "p95": percentile(values, 0.95),
            "max": round(max(values), 1) if values else None}
