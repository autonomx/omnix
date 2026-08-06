from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import FastAPI

from .alerts import TradingAlertEvaluation, TradingAlertRepository, default_alert_repository
from .service import TradingMarketDataService, default_market_data_service


_MONITOR_STATE_KEY = "_omnix_trading_alert_monitor"


def _env_flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def trading_alert_monitor_enabled() -> bool:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _env_flag("OMNIX_TRADING_ALERT_MONITOR_IN_TESTS", "0")
    return _env_flag("OMNIX_TRADING_ALERT_MONITOR", "1")


def _interval_seconds() -> float:
    try:
        value = float(os.environ.get("OMNIX_TRADING_ALERT_INTERVAL_SECONDS", "30"))
    except ValueError:
        value = 30.0
    return max(5.0, value)


class TradingAlertMonitor:
    def __init__(
        self,
        *,
        repository_factory: Callable[[], TradingAlertRepository] = default_alert_repository,
        market_service_factory: Callable[[], TradingMarketDataService] = default_market_data_service,
        interval_seconds: float | None = None,
    ) -> None:
        self.repository_factory = repository_factory
        self.market_service_factory = market_service_factory
        self.interval_seconds = interval_seconds or _interval_seconds()
        self._task: asyncio.Task[None] | None = None
        self.last_error: str | None = None
        self.last_run_at: datetime | None = None
        self.evaluation_count = 0
        self.trigger_count = 0

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def run_once(self) -> int:
        repository = self.repository_factory()
        alerts = await asyncio.to_thread(repository.list_alerts, 500)
        targets = {
            (alert.instrument_id, alert.binding_id)
            for alert in alerts
            if alert.enabled
        }
        triggered = 0
        service = self.market_service_factory()
        for instrument_id, binding_id in sorted(targets, key=lambda item: (item[0], item[1] or "")):
            try:
                quote = await asyncio.to_thread(
                    service.quote,
                    instrument_id,
                    binding_id,
                )
                observed_at = datetime.fromisoformat(
                    str(quote.get("received_at") or datetime.now(timezone.utc).isoformat())
                    .replace("Z", "+00:00")
                )
                triggers = await asyncio.to_thread(
                    repository.evaluate,
                    TradingAlertEvaluation(
                        instrument_id=instrument_id,
                        observed_price=Decimal(str(quote["price"])),
                        observed_at=observed_at,
                    ),
                )
                self.evaluation_count += 1
                triggered += len(triggers)
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
        self.trigger_count += triggered
        self.last_run_at = datetime.now(timezone.utc)
        return triggered

    def diagnostics(self) -> dict[str, Any]:
        return {
            "enabled": trading_alert_monitor_enabled(),
            "running": self._task is not None,
            "interval_seconds": self.interval_seconds,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_error": self.last_error,
            "evaluation_count": self.evaluation_count,
            "trigger_count": self.trigger_count,
        }

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(self.interval_seconds)


def register_trading_alert_monitor(gateway: FastAPI) -> TradingAlertMonitor:
    existing = getattr(gateway.state, _MONITOR_STATE_KEY, None)
    if isinstance(existing, TradingAlertMonitor):
        return existing
    monitor = TradingAlertMonitor()
    setattr(gateway.state, _MONITOR_STATE_KEY, monitor)

    async def startup() -> None:
        if trading_alert_monitor_enabled():
            monitor.start()

    async def shutdown() -> None:
        await monitor.stop()

    gateway.router.add_event_handler("startup", startup)
    gateway.router.add_event_handler("shutdown", shutdown)
    return monitor
