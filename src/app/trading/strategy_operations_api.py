from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from .strategy_monitor import TradingStrategyMonitor, trading_strategy_monitor_enabled
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
    universe_archive_monitor: StrategyRuntimeMonitorStatus
    v2_qualification_monitor: StrategyRuntimeMonitorStatus
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
            execution_authority=False,
        )

    return router


__all__ = [
    "StrategyOperationsStatus",
    "StrategyRuntimeMonitorStatus",
    "create_trading_strategy_operations_router",
]
