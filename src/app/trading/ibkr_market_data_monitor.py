from __future__ import annotations

"""Shared IBKR quote-demand reconciler and causal observation bridge.

This monitor owns no trading authority. It unions the instruments demanded by
all active strategy configurations, opens one upstream IBKR quote line per
unique instrument, and continuously records quote snapshots into the existing
causal observation plane. The rollout remains zero-authority unless the separate
IBKR LIVE_DATA gate is explicitly enabled.
"""

import asyncio
import os
from contextlib import suppress
from datetime import datetime, timezone
from typing import Callable

from fastapi import FastAPI

from .execution import assess_execution_observation, execution_observation_from_quote
from .execution_observation_plane import (
    ExecutionObservationPlane,
    default_execution_observation_plane,
)
from .providers.ibkr import IbkrEquityProvider
from .service import TradingMarketDataService, default_market_data_service
from .strategy_repository import TradingStrategyRepository, default_strategy_repository
from .strategy_shadow_universe import (
    resolve_stoch_rsi_5m_runtime_archive,
    resolve_v2_runtime_archive,
)
from .streaming.manager import StreamingQuoteUpdate
from .trade_logging import trade_log
from .us_equity_calendar import us_equity_session


_STATE_KEY = "_omnix_trading_ibkr_market_data_monitor"


def _flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def ibkr_market_data_monitor_enabled() -> bool:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _flag("OMNIX_IBKR_MONITOR_IN_TESTS", "0")
    return _flag("OMNIX_IBKR_MONITOR", "1")


def _interval_seconds() -> float:
    try:
        value = float(os.environ.get("OMNIX_IBKR_DEMAND_RECONCILE_SECONDS", "5"))
    except ValueError:
        value = 5.0
    return max(1.0, value)


class TradingIbkrMarketDataMonitor:
    def __init__(
        self,
        *,
        strategy_repository_factory: Callable[[], TradingStrategyRepository] = default_strategy_repository,
        market_service_factory: Callable[[], TradingMarketDataService] = default_market_data_service,
        plane: ExecutionObservationPlane | None = None,
        now_factory: Callable[[], datetime] | None = None,
        interval_seconds: float | None = None,
    ) -> None:
        self.strategy_repository_factory = strategy_repository_factory
        self.market_service_factory = market_service_factory
        self.plane = plane or default_execution_observation_plane()
        self.now_factory = now_factory or (lambda: datetime.now(timezone.utc))
        self.interval_seconds = interval_seconds or _interval_seconds()
        self._task: asyncio.Task[None] | None = None
        self._keys: dict[str, str] = {}
        self._callbacks: dict[str, Callable] = {}
        self.last_run_at: datetime | None = None
        self.last_error: str | None = None
        self.demanded_instrument_count = 0
        self.live_event_count = 0
        self.nonlive_event_count = 0
        self.recorded_observation_count = 0
        self.subscription_create_count = 0
        self.subscription_remove_count = 0
        self.subscription_error_count = 0

    def _active_demand(
        self,
        repository: TradingStrategyRepository,
        *,
        now: datetime,
    ) -> set[str]:
        demanded: set[str] = set()
        configs = repository.list_configs(active_only=True)
        for config in configs:
            universe = None
            if config.active_universe_id:
                try:
                    universe = repository.get_universe(config.active_universe_id)
                except Exception:
                    universe = None
            if universe is None:
                try:
                    if config.strategy_kind == "stoch_rsi_5m_v1":
                        universe = resolve_stoch_rsi_5m_runtime_archive(
                            config,
                            repository,
                            now=now,
                        )
                    else:
                        universe = resolve_v2_runtime_archive(
                            config,
                            repository,
                            now=now,
                        )
                except Exception:
                    universe = None
            if universe is None:
                continue
            for candidate in universe.candidates:
                instrument_id = str(candidate.instrument_id)
                if instrument_id.startswith("equity:"):
                    demanded.add(instrument_id)
        return demanded

    def _record_quote(self, update: StreamingQuoteUpdate) -> None:
        if update.last is None:
            return
        freshness = "live" if update.market_data_type == "LIVE" else "delayed"
        quote = {
            "instrument_id": update.instrument_id,
            "binding_id": update.binding_id,
            "provider": update.provider,
            "bid": update.bid,
            "ask": update.ask,
            "bid_size": update.bid_size,
            "ask_size": update.ask_size,
            "last": update.last,
            "high": update.high,
            "low": update.low,
            "cumulative_volume": update.cumulative_volume,
            "source_time": update.source_time,
            "received_at": update.received_at,
            "session": us_equity_session(update.source_time),
            "freshness_mode": freshness,
            "provider_sequence": update.provider_sequence,
        }
        observation = execution_observation_from_quote(
            quote,
            binding_id=update.binding_id,
            provider=update.provider,
            received_at=update.received_at,
        )
        observation = assess_execution_observation(
            observation,
            binding_purpose="LIVE_DATA",
        )
        if self.plane.record(observation, recorded_at=update.received_at):
            self.recorded_observation_count += 1
        if update.market_data_type == "LIVE":
            self.live_event_count += 1
        else:
            self.nonlive_event_count += 1

    def _provider_callback(
        self,
        *,
        market_service: TradingMarketDataService,
        binding_id: str,
        instrument_id: str,
    ):
        def callback(snapshot) -> None:
            update = StreamingQuoteUpdate(
                binding_id=binding_id,
                instrument_id=instrument_id,
                provider="ibkr",
                source_time=snapshot.source_time,
                received_at=snapshot.received_at,
                bid=snapshot.bid,
                ask=snapshot.ask,
                bid_size=snapshot.bid_size,
                ask_size=snapshot.ask_size,
                last=snapshot.last,
                last_size=snapshot.last_size,
                high=snapshot.high,
                low=snapshot.low,
                cumulative_volume=snapshot.cumulative_volume,
                market_data_type=snapshot.market_data_type,
                live_entitled=snapshot.live_entitled,
                contract_id=str(snapshot.contract.con_id),
                provider_sequence=snapshot.provider_sequence,
            )
            market_service.subscriptions.publish_quote(update)

        return callback

    def _ensure_subscription(
        self,
        market_service: TradingMarketDataService,
        provider: IbkrEquityProvider,
        instrument_id: str,
    ) -> None:
        binding = provider.get_binding(instrument_id)
        listener_id = f"ibkr-plane:{instrument_id}"
        if instrument_id not in self._callbacks:
            self._callbacks[instrument_id] = self._provider_callback(
                market_service=market_service,
                binding_id=binding.binding_id,
                instrument_id=instrument_id,
            )
        key, created = market_service.subscriptions.subscribe_quote(
            listener_id=listener_id,
            binding_id=binding.binding_id,
            instrument_id=instrument_id,
            listener=self._record_quote,
        )
        self._keys[instrument_id] = key
        callback = self._callbacks[instrument_id]
        try:
            # Calling this on every reconciliation is intentional: IbkrRuntime
            # deduplicates healthy subscriptions but recreates them after a
            # Gateway reconnect invalidates prior request IDs.
            provider.subscribe_quote(instrument_id, callback)
            market_service.subscriptions.mark_connected(key)
            if created:
                self.subscription_create_count += 1
        except Exception as exc:
            self.subscription_error_count += 1
            self.last_error = f"{instrument_id}: {type(exc).__name__}: {exc}"
            market_service.subscriptions.mark_disconnected(key)

    def _remove_subscription(
        self,
        market_service: TradingMarketDataService,
        provider: IbkrEquityProvider,
        instrument_id: str,
    ) -> None:
        key = self._keys.pop(instrument_id, None)
        callback = self._callbacks.pop(instrument_id, None)
        if key is None:
            return
        listener_id = f"ibkr-plane:{instrument_id}"
        close_upstream = market_service.subscriptions.unsubscribe(key, listener_id)
        if close_upstream:
            try:
                provider.unsubscribe_quote(instrument_id, listener=callback)
            except Exception:
                pass
        self.subscription_remove_count += 1

    async def run_once(self) -> int:
        now = self.now_factory()
        if now.tzinfo is None:
            raise ValueError("IBKR market-data monitor clock must be timezone-aware")
        now = now.astimezone(timezone.utc)
        repository = self.strategy_repository_factory()
        market_service = self.market_service_factory()
        provider = market_service.registry.provider("ibkr")
        if not isinstance(provider, IbkrEquityProvider):
            raise TypeError("IBKR registry provider has unexpected type")

        demanded = await asyncio.to_thread(
            self._active_demand,
            repository,
            now=now,
        )
        self.demanded_instrument_count = len(demanded)

        for instrument_id in sorted(set(self._keys) - demanded):
            self._remove_subscription(market_service, provider, instrument_id)

        if not provider.runtime.enabled:
            self.last_run_at = now
            return 0

        before = self.recorded_observation_count
        for instrument_id in sorted(demanded):
            self._ensure_subscription(
                market_service,
                provider,
                instrument_id,
            )

        self.last_run_at = now
        return self.recorded_observation_count - before

    def diagnostics(self) -> dict[str, object]:
        return {
            "enabled": ibkr_market_data_monitor_enabled(),
            "running": self._task is not None,
            "interval_seconds": self.interval_seconds,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_error": self.last_error,
            "demanded_instrument_count": self.demanded_instrument_count,
            "active_subscription_count": len(self._keys),
            "subscription_create_count": self.subscription_create_count,
            "subscription_remove_count": self.subscription_remove_count,
            "subscription_error_count": self.subscription_error_count,
            "live_event_count": self.live_event_count,
            "nonlive_event_count": self.nonlive_event_count,
            "recorded_observation_count": self.recorded_observation_count,
            "authority_mode": "LIVE_DATA" if os.environ.get("OMNIX_IBKR_LIVE_AUTHORITY", "0") in {"1", "true", "yes", "on"} else "ZERO_AUTHORITY_OBSERVATION",
            "order_execution_authority": False,
        }

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                trade_log(
                    "auto_trading",
                    "ibkr_market_data_monitor_error",
                    error_type=type(exc).__name__,
                    detail=str(exc),
                    execution_authority=False,
                )
            await asyncio.sleep(self.interval_seconds)

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
        try:
            market_service = self.market_service_factory()
            provider = market_service.registry.provider("ibkr")
            for instrument_id in list(self._keys):
                self._remove_subscription(market_service, provider, instrument_id)
        except Exception:
            pass


def register_trading_ibkr_market_data_monitor(
    gateway: FastAPI,
) -> TradingIbkrMarketDataMonitor:
    existing = getattr(gateway.state, _STATE_KEY, None)
    if isinstance(existing, TradingIbkrMarketDataMonitor):
        return existing
    monitor = TradingIbkrMarketDataMonitor()
    setattr(gateway.state, _STATE_KEY, monitor)

    async def startup() -> None:
        if ibkr_market_data_monitor_enabled():
            monitor.start()

    async def shutdown() -> None:
        await monitor.stop()

    gateway.router.add_event_handler("startup", startup)
    gateway.router.add_event_handler("shutdown", shutdown)
    return monitor


__all__ = [
    "TradingIbkrMarketDataMonitor",
    "ibkr_market_data_monitor_enabled",
    "register_trading_ibkr_market_data_monitor",
]
