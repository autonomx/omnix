from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from datetime import datetime, timezone

from fastapi import FastAPI

from .strategy_repository import TradingStrategyRepository, default_strategy_repository
from .strategy_universe_archiver import archive_daily_universe_if_due
from .trade_logging import trade_log


_STATE_KEY = "_omnix_trading_strategy_universe_archive_monitor"


def _flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def strategy_universe_archive_monitor_enabled() -> bool:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _flag("OMNIX_TRADING_UNIVERSE_ARCHIVER_IN_TESTS", "0")
    return _flag("OMNIX_TRADING_UNIVERSE_ARCHIVER", "1")


def _interval_seconds() -> float:
    try:
        value = float(os.environ.get("OMNIX_TRADING_UNIVERSE_ARCHIVER_INTERVAL_SECONDS", "30"))
    except ValueError:
        value = 30.0
    return max(5.0, value)


class TradingStrategyUniverseArchiveMonitor:
    """Evidence-only morning scanner archive; never changes execution authority."""

    def __init__(self, *, interval_seconds: float | None = None) -> None:
        self.interval_seconds = interval_seconds or _interval_seconds()
        self._task: asyncio.Task[None] | None = None
        self.last_run_at: datetime | None = None
        self.last_error: str | None = None
        self.archive_count = 0

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def run_once(self) -> int:
        repository: TradingStrategyRepository = default_strategy_repository()
        # Archive research evidence even while a saved strategy is Off. Execution
        # mode is irrelevant here; the per-strategy archiver still requires the
        # strategy itself to be enabled and auto-archive configured.
        configs = await asyncio.to_thread(repository.list_configs, active_only=False)
        archived = 0
        now = datetime.now(timezone.utc)
        for config in configs:
            try:
                snapshot = await asyncio.to_thread(
                    archive_daily_universe_if_due,
                    config,
                    repository,
                    now=now,
                )
                if snapshot is not None:
                    archived += 1
            except Exception as exc:
                self.last_error = f"{config.strategy_id}: {type(exc).__name__}: {exc}"
                trade_log(
                    "auto_trading",
                    "daily_universe_archive_error",
                    strategy_id=config.strategy_id,
                    observed_at=now,
                    error_type=type(exc).__name__,
                    detail=str(exc),
                    execution_authority=False,
                )
        self.archive_count += archived
        self.last_run_at = datetime.now(timezone.utc)
        return archived

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                trade_log(
                    "auto_trading",
                    "daily_universe_archive_monitor_error",
                    error_type=type(exc).__name__,
                    detail=str(exc),
                    execution_authority=False,
                )
            await asyncio.sleep(self.interval_seconds)


def register_trading_strategy_universe_archive_monitor(gateway: FastAPI) -> TradingStrategyUniverseArchiveMonitor:
    existing = getattr(gateway.state, _STATE_KEY, None)
    if isinstance(existing, TradingStrategyUniverseArchiveMonitor):
        return existing
    monitor = TradingStrategyUniverseArchiveMonitor()
    setattr(gateway.state, _STATE_KEY, monitor)

    async def startup() -> None:
        if strategy_universe_archive_monitor_enabled():
            monitor.start()

    async def shutdown() -> None:
        await monitor.stop()

    gateway.router.add_event_handler("startup", startup)
    gateway.router.add_event_handler("shutdown", shutdown)
    return monitor


__all__ = [
    "TradingStrategyUniverseArchiveMonitor",
    "register_trading_strategy_universe_archive_monitor",
    "strategy_universe_archive_monitor_enabled",
]
