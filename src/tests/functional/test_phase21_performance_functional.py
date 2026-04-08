"""Functional tests for Phase 21 performance fixes."""
from app.rpg.core.performance import (
    BenchmarkHarness,
    PerformanceDeterminismValidator,
    PerformanceMetric,
    PerformanceState,
)


def test_phase21_record_diagnostic_only_uses_record_internally():
    state = PerformanceState(tick=5)
    state.record_diagnostic_only("test_metric", 10.5, "ms")
    assert len(state.metrics) == 1
    assert state.metrics[0].name == "test_metric"
    assert state.metrics[0].value == 10.5
    assert state.metrics[0].unit == "ms"
    assert state.metrics[0].tick == 5


def test_phase21_record_clamps_negative_value_and_tick():
    state = PerformanceState(tick=-10)
    state.record("x", -5.0, "ms")
    assert state.metrics[0].value == 0.0
    assert state.metrics[0].tick == 0


def test_phase21_record_normalizes_invalid_unit():
    state = PerformanceState(tick=1)
    state.record("y", 1.0, "invalid")
    assert state.metrics[0].unit == "ms"


def test_phase21_benchmark_returns_diagnostic_only_flag():
    payload = BenchmarkHarness.benchmark(lambda: None, iterations=1)
    assert "diagnostic_only" in payload
    assert payload["diagnostic_only"] is True


def test_phase21_normalize_state_is_idempotent():
    state = PerformanceState(
        metrics=[
            PerformanceMetric(name="b", value=2.0, unit="ms", tick=2),
            PerformanceMetric(name="a", value=1.0, unit="ms", tick=1),
        ],
        tick=0,
        budget_ms=100.0,
    )
    out1 = PerformanceDeterminismValidator.normalize_state(state)
    out2 = PerformanceDeterminismValidator.normalize_state(out1)
    assert out1.to_dict() == out2.to_dict()