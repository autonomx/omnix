"""Server indicator registry against the browser goldens (TVP-0.2).

The goldens are produced by ``web/src/features/trading/indicators/goldens/indicatorGoldens.test.ts``.
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from app.apps.trading.indicators.engine import CORE_INDICATOR_FORMULA_VERSION
from app.apps.trading.indicators.registry import (
    BarSeries,
    IndicatorInputs,
    compute_indicator,
    server_indicator,
    server_indicator_ids,
)

GOLDEN_ROOT = Path(__file__).resolve().parents[3] / "resources" / "trading" / "indicator_goldens"

# Relative tolerance by numeric class (roadmap TVP-0.2). Recursive indicators are compared after a warm-up.
TOLERANCE = {"exact": 1e-12, "recursive": 1e-9, "transcendental": 1e-12}
ABSOLUTE_TOLERANCE = 1e-9
WARMUP_PERIODS = 3

ALERT_INDICATORS = {"sma", "ema", "rsi", "macd", "bollinger", "atr", "vwap", "stochastic-rsi"}


@cache
def _index() -> dict[str, Any]:
    return json.loads((GOLDEN_ROOT / "index.json").read_text(encoding="utf-8"))


@cache
def _dataset(name: str) -> BarSeries:
    payload = json.loads((GOLDEN_ROOT / "datasets" / f"{name}.json").read_text(encoding="utf-8"))
    bars = payload["bars"]
    return BarSeries(
        start_times=tuple(datetime.fromisoformat(bar["start_time"].replace("Z", "+00:00")) for bar in bars),
        open=tuple(float(bar["open"]) for bar in bars),
        high=tuple(float(bar["high"]) for bar in bars),
        low=tuple(float(bar["low"]) for bar in bars),
        close=tuple(float(bar["close"]) for bar in bars),
        volume=tuple(float(bar["volume"]) for bar in bars),
    )


def _golden(indicator_id: str) -> dict[str, Any]:
    return json.loads((GOLDEN_ROOT / "indicators" / f"{indicator_id}.json").read_text(encoding="utf-8"))


def _inputs(raw: dict[str, Any]) -> IndicatorInputs:
    return IndicatorInputs(
        period=raw["period"],
        fast_period=raw.get("fastPeriod"),
        slow_period=raw.get("slowPeriod"),
        signal_period=raw.get("signalPeriod"),
        standard_deviations=raw.get("standardDeviations"),
    )


def _same(expected: float | None, actual: float, relative: float) -> bool:
    if expected is None:
        return not math.isfinite(actual)
    return math.isclose(expected, actual, rel_tol=relative, abs_tol=ABSOLUTE_TOLERANCE)


def test_goldens_match_the_server_formula_version() -> None:
    assert _index()["formula_version"] == CORE_INDICATOR_FORMULA_VERSION


def test_every_server_indicator_is_a_known_chart_indicator() -> None:
    known = {item["id"] for item in _index()["indicators"]}
    assert set(server_indicator_ids()) <= known


def test_alert_indicators_have_server_implementations() -> None:
    assert ALERT_INDICATORS <= set(server_indicator_ids())


@pytest.mark.parametrize("indicator_id", server_indicator_ids())
def test_server_indicator_matches_browser_goldens(indicator_id: str) -> None:
    indicator = server_indicator(indicator_id)
    assert indicator is not None
    relative = TOLERANCE[indicator.numeric_class]
    golden = _golden(indicator_id)
    failures: list[str] = []
    for case in golden["cases"]:
        bars = _dataset(case["dataset"])
        inputs = _inputs(case["inputs"])
        label = f"{indicator_id} {case['case_id']}"
        if case.get("error"):
            with pytest.raises((ValueError, ZeroDivisionError, IndexError)):
                compute_indicator(indicator_id, bars, inputs)
            continue
        actual = {series.key: series.points for series in compute_indicator(indicator_id, bars, inputs)}
        expected = {output["key"]: output["points"] for output in case["outputs"]}
        if list(actual) != list(expected):
            failures.append(f"{label}: output keys {list(actual)} != {list(expected)}")
            continue
        warmup = WARMUP_PERIODS * inputs.period if indicator.numeric_class == "recursive" else 0
        for key, expected_points in expected.items():
            actual_points = actual[key]
            if [index for index, _ in actual_points] != [index for index, _ in expected_points]:
                failures.append(f"{label} {key}: points at different bars ({len(actual_points)} vs {len(expected_points)})")
                continue
            for (index, value), (_, expected_value) in zip(actual_points, expected_points, strict=True):
                if index >= warmup and not _same(expected_value, value, relative):
                    failures.append(f"{label} {key} bar {index}: {value!r} != {expected_value!r}")
                    break
    assert not failures, "\n".join(failures[:20])
