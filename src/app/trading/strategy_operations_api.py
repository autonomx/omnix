from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from .providers.alpaca_iex_status import (
    AlpacaIexStatusMonitor,
    alpaca_iex_status_monitor_enabled,
)
from .strategy_deep_recovery_monitor import (
    TradingStrategyDeepRecoveryShadowMonitor,
    strategy_deep_recovery_shadow_monitor_enabled,
)
from .strategy_monitor import TradingStrategyMonitor, trading_strategy_monitor_enabled
from .strategy_prospective_economic_monitor import (
    TradingStrategyProspectiveEconomicMonitor,
    strategy_prospective_economic_monitor_enabled,
)
from .strategy_universe_archive_monitor import (
    TradingStrategyUniverseArchiveMonitor,
    strategy_universe_archive_monitor_enabled,
)
from .strategy_v2_qualification_monitor import (
    TradingStrategyV2QualificationMonitor,
    strategy_v2_qualification_monitor_enabled,
)


class StrategyRuntimeMonitorStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    configured_enabled: bool
    registered: bool
    running: bool
    interval_seconds: float | None = None
    last_run_at: datetime | None = None
    last_error: str | None = None
    counters: dict[str, int] = Field(default_factory=dict)


class StrategyOperationsStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    observed_at: datetime
    strategy_monitor: StrategyRuntimeMonitorStatus
    deep_recovery_shadow_monitor: StrategyRuntimeMonitorStatus
    prospective_economic_monitor: StrategyRuntimeMonitorStatus
    universe_archive_monitor: StrategyRuntimeMonitorStatus
    v2_qualification_monitor: StrategyRuntimeMonitorStatus
    alpaca_status_monitor: StrategyRuntimeMonitorStatus
    execution_authority: Literal[False] = False


def _monitor_status(
    monitor: object | None,
    *,
    expected_type: type,
    configured_enabled: bool,
    counter_names: tuple[str, ...],
) -> StrategyRuntimeMonitorStatus:
    registered = isinstance(monitor, expected_type)
    if not registered:
        return StrategyRuntimeMonitorStatus(
            configured_enabled=configured_enabled,
            registered=False,
            running=False,
        )
    task = getattr(monitor, "_task", None)
    running = bool(task is not None and not task.done())
    counters = {
        name: int(getattr(monitor, name, 0) or 0)
        for name in counter_names
    }
    return StrategyRuntimeMonitorStatus(
        configured_enabled=configured_enabled,
        registered=True,
        running=running,
        interval_seconds=float(getattr(monitor, "interval_seconds", 0.0) or 0.0),
        last_run_at=getattr(monitor, "last_run_at", None),
        last_error=getattr(monitor, "last_error", None),
        counters=counters,
    )


def _alpaca_status(monitor: object | None) -> StrategyRuntimeMonitorStatus:
    configured_enabled = alpaca_iex_status_monitor_enabled()
    if not isinstance(monitor, AlpacaIexStatusMonitor):
        return StrategyRuntimeMonitorStatus(
            configured_enabled=configured_enabled,
            registered=False,
            running=False,
        )
    task = getattr(monitor, "_task", None)
    cache_snapshot = monitor.cache.snapshot()
    return StrategyRuntimeMonitorStatus(
        configured_enabled=configured_enabled,
        registered=True,
        running=bool(task is not None and not task.done()),
        interval_seconds=None,
        last_run_at=monitor.last_message_at,
        last_error=monitor.last_error,
        counters={
            "reconnect_count": int(monitor.reconnect_count),
            "disconnect_count": int(cache_snapshot.get("disconnect_count", 0) or 0),
            "known_halts": int(cache_snapshot.get("known_halts", 0) or 0),
            "history_symbols": int(cache_snapshot.get("history_symbols", 0) or 0),
        },
    )


def create_trading_strategy_operations_router() -> APIRouter:
    router = APIRouter(prefix="/api/trading/strategy-operations", tags=["trading-strategy-operations"])

    @router.get("/status", response_model=StrategyOperationsStatus)
    async def strategy_operations_status(request: Request) -> StrategyOperationsStatus:
        state = request.app.state
        return StrategyOperationsStatus(
            observed_at=datetime.now(timezone.utc),
            strategy_monitor=_monitor_status(
                getattr(state, "_omnix_trading_strategy_monitor", None),
                expected_type=TradingStrategyMonitor,
                configured_enabled=trading_strategy_monitor_enabled(),
                counter_names=("evaluation_count", "signal_count", "paper_order_count"),
            ),
            deep_recovery_shadow_monitor=_monitor_status(
                getattr(state, "_omnix_trading_strategy_deep_recovery_shadow_monitor", None),
                expected_type=TradingStrategyDeepRecoveryShadowMonitor,
                configured_enabled=strategy_deep_recovery_shadow_monitor_enabled(),
                counter_names=(
                    "evaluation_count",
                    "state_transition_count",
                    "signal_count",
                    "execution_observation_count",
                ),
            ),
            prospective_economic_monitor=_monitor_status(
                getattr(state, "_omnix_trading_strategy_prospective_economic_monitor", None),
                expected_type=TradingStrategyProspectiveEconomicMonitor,
                configured_enabled=strategy_prospective_economic_monitor_enabled(),
                counter_names=(
                    "candidate_capture_count",
                    "signal_capture_count",
                    "outcome_capture_count",
                    "incomplete_outcome_count",
                ),
            ),
            universe_archive_monitor=_monitor_status(
                getattr(state, "_omnix_trading_strategy_universe_archive_monitor", None),
                expected_type=TradingStrategyUniverseArchiveMonitor,
                configured_enabled=strategy_universe_archive_monitor_enabled(),
                counter_names=("archive_count",),
            ),
            v2_qualification_monitor=_monitor_status(
                getattr(state, "_omnix_trading_strategy_v2_qualification_monitor", None),
                expected_type=TradingStrategyV2QualificationMonitor,
                configured_enabled=strategy_v2_qualification_monitor_enabled(),
                counter_names=("replay_count",),
            ),
            alpaca_status_monitor=_alpaca_status(
                getattr(state, "_omnix_alpaca_iex_status_monitor", None),
            ),
            execution_authority=False,
        )

    return router


__all__ = [
    "StrategyOperationsStatus",
    "StrategyRuntimeMonitorStatus",
    "create_trading_strategy_operations_router",
]
