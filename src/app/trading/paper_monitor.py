from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import FastAPI

from .paper import PaperMarketObservation
from .paper_repository import TradingPaperRepository
from .paper_runtime_repository import default_runtime_paper_repository
from .service import TradingMarketDataService, default_market_data_service


_MONITOR_STATE_KEY = "_omnix_trading_paper_monitor"


def _env_flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def trading_paper_monitor_enabled() -> bool:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _env_flag("OMNIX_TRADING_PAPER_MONITOR_IN_TESTS", "0")
    return _env_flag("OMNIX_TRADING_PAPER_MONITOR", "1")


def _interval_seconds() -> float:
    try:
        value = float(os.environ.get("OMNIX_TRADING_PAPER_INTERVAL_SECONDS", "15"))
    except ValueError:
        value = 15.0
    return max(5.0, value)


class TradingPaperMonitor:
    def __init__(
        self,
        *,
        repository_factory: Callable[[], TradingPaperRepository] = default_runtime_paper_repository,
        market_service_factory: Callable[[], TradingMarketDataService] = default_market_data_service,
        interval_seconds: float | None = None,
    ) -> None:
        self.repository_factory = repository_factory
        self.market_service_factory = market_service_factory
        self.interval_seconds = interval_seconds or _interval_seconds()
        self._task: asyncio.Task[None] | None = None
        self.last_error: str | None = None
        self.last_run_at: datetime | None = None
        self.quote_count = 0
        self.fill_count = 0

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
        accounts = await asyncio.to_thread(repository.list_accounts, 100)
        targets: dict[tuple[str, str | None], set[str]] = defaultdict(set)
        market_references: dict[tuple[str, str | None], list[tuple[str, Decimal]]] = defaultdict(list)
        for account in accounts:
            if not account.enabled:
                continue
            snapshot = await asyncio.to_thread(repository.snapshot, account.account_id)
            for order in snapshot.open_orders:
                targets[(order.instrument_id, order.binding_id)].add(account.account_id)
                if order.order_type == "market" and order.reference_price is not None:
                    market_references[(order.instrument_id, order.binding_id)].append(
                        (account.account_id, order.reference_price)
                    )

        service = self.market_service_factory()
        filled = 0
        for (instrument_id, requested_binding), account_ids in sorted(
            targets.items(), key=lambda item: (item[0][0], item[0][1] or "")
        ):
            try:
                quote = await asyncio.to_thread(
                    service.quote,
                    instrument_id,
                    requested_binding,
                )
                source_time = datetime.fromisoformat(
                    str(quote.get("received_at") or datetime.now(timezone.utc).isoformat())
                    .replace("Z", "+00:00")
                )
                observation = PaperMarketObservation(
                    instrument_id=instrument_id,
                    binding_id=str(quote.get("binding_id") or requested_binding or "") or None,
                    provider=str(quote.get("provider") or "unknown"),
                    price=Decimal(str(quote["price"])),
                    source_time=source_time,
                    evaluated_at=datetime.now(timezone.utc),
                )
                self.quote_count += 1
                for account_id in sorted(account_ids):
                    fills = await asyncio.to_thread(
                        repository.process_observation,
                        account_id,
                        observation,
                    )
                    filled += len(fills)
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                for account_id, reference_price in market_references.get(
                    (instrument_id, requested_binding),
                    [],
                ):
                    now = datetime.now(timezone.utc)
                    fallback_observation = PaperMarketObservation(
                        instrument_id=instrument_id,
                        binding_id=requested_binding,
                        provider="paper-reference",
                        price=reference_price,
                        source_time=now,
                        evaluated_at=now,
                    )
                    fills = await asyncio.to_thread(
                        repository.process_observation,
                        account_id,
                        fallback_observation,
                    )
                    filled += len(fills)
        self.fill_count += filled
        self.last_run_at = datetime.now(timezone.utc)
        return filled

    def diagnostics(self) -> dict[str, Any]:
        return {
            "enabled": trading_paper_monitor_enabled(),
            "running": self._task is not None,
            "interval_seconds": self.interval_seconds,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_error": self.last_error,
            "quote_count": self.quote_count,
            "fill_count": self.fill_count,
        }

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(self.interval_seconds)


def register_trading_paper_monitor(gateway: FastAPI) -> TradingPaperMonitor:
    existing = getattr(gateway.state, _MONITOR_STATE_KEY, None)
    if isinstance(existing, TradingPaperMonitor):
        return existing
    monitor = TradingPaperMonitor()
    setattr(gateway.state, _MONITOR_STATE_KEY, monitor)

    async def startup() -> None:
        if trading_paper_monitor_enabled():
            monitor.start()

    async def shutdown() -> None:
        await monitor.stop()

    gateway.router.add_event_handler("startup", startup)
    gateway.router.add_event_handler("shutdown", shutdown)
    return monitor
