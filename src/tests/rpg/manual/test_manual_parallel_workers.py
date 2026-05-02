import pytest

from tests.rpg.manual.threading_helpers import (
    _default_scenario_workers,
    _effective_scenario_workers,
    _scenario_workers_source,
)


def test_default_scenario_workers_unset(monkeypatch):
    # Test default worker count is 8 when env is unset.
    monkeypatch.delenv("OMNIX_MANUAL_SCENARIO_WORKERS", raising=False)
    assert _default_scenario_workers() == 8


def test_default_scenario_workers_env(monkeypatch):
    # Test env override works.
    monkeypatch.setenv("OMNIX_MANUAL_SCENARIO_WORKERS", "3")
    assert _default_scenario_workers() == 3


def test_default_scenario_workers_invalid(monkeypatch):
    # Test invalid env falls back to 8.
    monkeypatch.setenv("OMNIX_MANUAL_SCENARIO_WORKERS", "invalid")
    assert _default_scenario_workers() == 8


def test_scenario_workers_source_default(monkeypatch):
    monkeypatch.delenv("OMNIX_MANUAL_SCENARIO_WORKERS", raising=False)
    assert _scenario_workers_source() == "default:8"


def test_scenario_workers_source_env(monkeypatch):
    monkeypatch.setenv("OMNIX_MANUAL_SCENARIO_WORKERS", "5")
    assert _scenario_workers_source() == "env:OMNIX_MANUAL_SCENARIO_WORKERS=5"


@pytest.mark.parametrize(
    "requested_workers,scenario_count,parallel,expected",
    [
        (8, 1, True, 1),  # scenario_count=1 => 1
        (8, 4, True, 4),  # scenario_count=4, requested=8 => 4
        (8, 20, True, 8),  # scenario_count=20, requested=8 => 8
        (8, 10, False, 1),  # parallel=False => 1
    ],
)
def test_effective_scenario_workers(requested_workers, scenario_count, parallel, expected):
    assert _effective_scenario_workers(requested_workers, scenario_count, parallel=parallel) == expected