"""Unit tests for Phase 21 performance fixes."""
from app.rpg.core.performance import (
    PerformanceMetric,
    PerformanceState,
    VALID_METRIC_UNITS,
    PerformanceDeterminismValidator,
)


def test_valid_metric_units_contains_expected_values():
    assert "ms" in VALID_METRIC_UNITS
    assert "count" in VALID_METRIC_UNITS
    assert "bytes" in VALID_METRIC_UNITS


def test_normalize_state_clamps_negative_values():
    state = PerformanceState(
        metrics=[
            PerformanceMetric(name="a", value=-10.0, unit="ms", tick=-5),
        ],
        tick=-1,
        budget_ms=-50.0,
    )
    out = PerformanceDeterminismValidator.normalize_state(state)
    assert out.tick == 0
    assert out.budget_ms == 0.0
    assert out.metrics[0].value == 0.0
    assert out.metrics[0].tick == 0


def test_normalize_state_sorts_metrics():
    state = PerformanceState(
        metrics=[
            PerformanceMetric(name="z", value=3.0, unit="ms", tick=3),
            PerformanceMetric(name="a", value=1.0, unit="ms", tick=1),
            PerformanceMetric(name="b", value=2.0, unit="ms", tick=2),
        ],
    )
    out = PerformanceDeterminismValidator.normalize_state(state)
    # Sort by tick, then name, then unit, then value
    assert [m.name for m in out.metrics] == ["a", "b", "z"]


def test_validate_bounds_catches_negative_values():
    state = PerformanceState(
        metrics=[
            PerformanceMetric(name="bad", value=-1.0, unit="ms", tick=0),
        ],
    )
    violations = PerformanceDeterminismValidator.validate_bounds(state)
    assert any("negative value" in v for v in violations)


def test_validate_bounds_catches_negative_tick():
    state = PerformanceState(
        metrics=[
            PerformanceMetric(name="bad", value=1.0, unit="ms", tick=-5),
        ],
    )
    violations = PerformanceDeterminismValidator.validate_bounds(state)
    assert any("negative tick" in v for v in violations)


def test_validate_bounds_catches_invalid_unit():
    state = PerformanceState(
        metrics=[
            PerformanceMetric(name="bad", value=1.0, unit="invalid", tick=0),
        ],
    )
    violations = PerformanceDeterminismValidator.validate_bounds(state)
    assert any("invalid unit" in v for v in violations)