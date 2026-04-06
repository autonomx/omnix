"""Regression tests for Phase 21 performance fixes."""
from app.rpg.core.performance import (
    PerformanceMetric,
    PerformanceState,
    BenchmarkHarness,
    PerformanceDeterminismValidator,
)


def test_phase21_normalize_state_sorts_and_clamps_metrics():
    state = PerformanceState(
        metrics=[
            PerformanceMetric(name="b", value=2.0, unit="ms", tick=2),
            PerformanceMetric(name="a", value=-1.0, unit="weird", tick=-5),
        ],
        tick=-1,
        budget_ms=-10.0,
    )
    out = PerformanceDeterminismValidator.normalize_state(state)
    assert out.tick == 0
    assert out.budget_ms == 0.0
    assert out.metrics[0].name == "a"
    assert out.metrics[0].unit == "ms"
    assert out.metrics[0].value == 0.0


def test_phase21_benchmark_payload_is_diagnostic_only():
    payload = BenchmarkHarness.benchmark(lambda: None, iterations=1)
    assert payload["diagnostic_only"] is True
    assert PerformanceDeterminismValidator.validate_diagnostic_only_payload(payload) == []