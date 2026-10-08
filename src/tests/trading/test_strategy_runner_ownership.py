"""Gap pullback execution ownership: monitor, runner shadow, runner (strategy runner WP)."""
from __future__ import annotations

import asyncio

import pytest

from app.apps.trading.strategies.models import GapPullbackConfig
from app.apps.trading.strategy_runner_pass import (
    RunnerOwnedConfigs,
    _DiscardingStrategyRepository,
    _ReadOnlyPaperRepository,
)
from app.apps.trading.strategy_v2_qualification import (
    FROZEN_V2_PROFILE_FINGERPRINT,
    frozen_v2_config,
    v2_profile_fingerprint,
)


def test_the_monitor_owns_a_configuration_by_default() -> None:
    assert GapPullbackConfig().execution_owner == "monitor"
    with pytest.raises(ValueError):
        GapPullbackConfig(execution_owner="broker")


def test_moving_a_configuration_keeps_its_qualified_profile() -> None:
    for owner in ("runner_shadow", "runner"):
        moved = frozen_v2_config().model_copy(update={"execution_owner": owner})
        assert v2_profile_fingerprint(moved) == FROZEN_V2_PROFILE_FINGERPRINT


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append(name)
            return name

        return call


def test_the_parity_pass_cannot_write() -> None:
    strategy = _Recorder()
    discarding = _DiscardingStrategyRepository(strategy)
    assert discarding.append_event(object()) is True
    assert discarding.recent_events("s", 10) == "recent_events"
    # Only the known reads pass; a write added later is refused too.
    for write in ("save_protection", "save_universe", "update_config", "create_config", "delete_config", "save_x"):
        with pytest.raises(PermissionError):
            getattr(discarding, write)
    assert strategy.calls == ["recent_events"]

    paper = _Recorder()
    read_only = _ReadOnlyPaperRepository(paper)
    assert read_only.snapshot("account") == "snapshot"
    for write in ("place_order", "cancel_order", "replace_order", "process_observation", "create_account"):
        with pytest.raises(PermissionError):
            getattr(read_only, write)
    assert paper.calls == ["snapshot"]


def test_the_monitor_switch_also_stops_runner_owned_configurations() -> None:
    def unused():
        raise AssertionError("a disabled runner must not open repositories")

    owned = RunnerOwnedConfigs(
        strategy_repository_factory=unused,
        paper_repository_factory=unused,
        market_service_factory=unused,
        enabled=lambda: False,
    )
    assert asyncio.run(owned.run_once()) == 0
