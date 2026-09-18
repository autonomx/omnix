from __future__ import annotations

"""Background causal quote capture for paper/shadow and live-data observation.

Execution-purpose observations still use the existing provider-neutral polling
surface. IBKR LIVE_DATA observations are different: one shared streaming
subscription per demanded instrument continuously updates the same causal plane
without granting brokerage/order authority.
"""

import asyncio
import os
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import FastAPI

from .binding_authority import binding_can_execute
from .execution import assess_execution_observation, execution_observation_from_quote
from .execution_observation_plane import (
    ExecutionObservationPlane,
    default_execution_observation_plane,
)
from .providers.ibkr_runtime import IbkrQuoteSnapshot
from .service import TradingMarketDataService, default_market_data_service
from .strategy_repository import (
    TradingStrategyRepository,
    default_strategy_repository,
)
from .strategy_shadow_universe import (
    resolve_stoch_rsi_5m_runtime_archive,
    resolve_v2_runtime_archive,
)
from .streaming.manager import StreamingQuoteUpdate
from .trade_logging import trade_log
from .us_equity_calendar import us_equity_session


_STATE_KEY = "_omnix_trading_execution_observation_monitor"


def _flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def execution_observation_monitor_enabled() -> bool:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _flag("OMNIX_TRADING_EXECUTION_OBSERVATION_MONITOR_IN_TESTS", "0")
    return _flag("OMNIX_TRADING_EXECUTION_OBSERVATION_MONITOR", "1")


def _interval_seconds() -> float:
    try:
        value = float(os.environ.get("OMNIX_TRADING_EXECUTION_OBSERVATION_INTERVAL_SECONDS", "1"))
    except ValueError:
        value = 1.0
    return max(0.25, value)


class TradingExecutionObservationMonitor:
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
        self._ibkr_streams: dict[str, dict[str, object]] = {}
        self.last_run_at: datetime | None = None
        self.last_error: str | None = None
        self.capture_count = 0
        self.capture_error_count = 0
        self.live_data_capture_count = 0
        self.live_data_capture_error_count = 0
        self.skipped_non_execution_binding_count = 0
        self.last_demand_count = 0

    @staticmethod
    def _candidate_key(candidate: Any) -> str | None:
        value = str(getattr(candidate, "instrument_id", "") or "").strip()
        return value or None

    def _active_candidates(
        self,
        repository: TradingStrategyRepository,
        configs: list[Any],
        *,
        now: datetime,
    ) -> dict[str, Any]:
        """Union instruments demanded by every active strategy/universe we know."""

        candidates: dict[str, Any] = {}
        for config in configs:
            universe = None
            active_universe_id = getattr(config, "active_universe_id", None)
            if active_universe_id:
                try:
                    universe = repository.get_universe(active_universe_id)
                except Exception:
                    universe = None
            if universe is None:
                for resolver in (
                    resolve_v2_runtime_archive,
                    resolve_stoch_rsi_5m_runtime_archive,
                ):
                    try:
                        universe = resolver(config, repository, now=now)
                    except Exception:
                        universe = None
                    if universe is not None:
                        break
            if universe is None:
                continue
            for candidate in getattr(universe, "candidates", ()):
                instrument_id = self._candidate_key(candidate)
                if instrument_id is not None:
                    candidates[instrument_id] = candidate
        return candidates

    def _record_ibkr_update(self, update: StreamingQuoteUpdate) -> None:
        if update.last is None:
            return
        freshness = "live" if update.market_data_type == "LIVE" else "delayed"
        quote: dict[str, object] = {
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
            "market_data_type": update.market_data_type,
            "live_entitled": update.live_entitled,
            "contract_id": update.contract_id,
        }
        try:
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
                self.live_data_capture_count += 1
        except Exception as exc:
            self.live_data_capture_error_count += 1
            self.last_error = (
                f"{update.instrument_id}: {type(exc).__name__}: {exc}"
            )

    @staticmethod
    def _stream_update(
        *,
        binding_id: str,
        instrument_id: str,
        snapshot: IbkrQuoteSnapshot,
    ) -> StreamingQuoteUpdate:
        return StreamingQuoteUpdate(
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

    def _sync_ibkr_streams(
        self,
        market_service: TradingMarketDataService,
        candidates: dict[str, Any],
    ) -> None:
        """Reconcile shared IBKR subscriptions to the union of active demand."""

        try:
            provider = market_service.registry.provider("ibkr")
        except Exception:
            return
        runtime = getattr(provider, "runtime", None)
        if runtime is None or not getattr(runtime, "enabled", False):
            self._teardown_ibkr_streams(market_service)
            return

        desired = {
            instrument_id
            for instrument_id in candidates
            if instrument_id.startswith("equity:")
        }
        existing = set(self._ibkr_streams)

        for instrument_id in sorted(existing - desired):
            state = self._ibkr_streams.pop(instrument_id)
            key = str(state["key"])
            listener_id = str(state["listener_id"])
            bridge = state["bridge"]
            close_upstream = market_service.subscriptions.unsubscribe(key, listener_id)
            if close_upstream:
                with suppress(Exception):
                    provider.unsubscribe_quote(
                        instrument_id,
                        listener=bridge,
                    )

        for instrument_id in sorted(desired - existing):
            try:
                binding = provider.get_binding(instrument_id)
                listener_id = f"execution-observation-plane:{instrument_id}"
                key, _ = market_service.subscriptions.subscribe_quote(
                    listener_id=listener_id,
                    binding_id=binding.binding_id,
                    instrument_id=instrument_id,
                    listener=self._record_ibkr_update,
                )

                def bridge(
                    snapshot: IbkrQuoteSnapshot,
                    *,
                    _binding_id: str = binding.binding_id,
                    _instrument_id: str = instrument_id,
                ) -> None:
                    market_service.subscriptions.publish_quote(
                        self._stream_update(
                            binding_id=_binding_id,
                            instrument_id=_instrument_id,
                            snapshot=snapshot,
                        )
                    )

                provider.subscribe_quote(instrument_id, bridge)
                market_service.subscriptions.mark_connected(key)
                self._ibkr_streams[instrument_id] = {
                    "key": key,
                    "listener_id": listener_id,
                    "bridge": bridge,
                    "binding_id": binding.binding_id,
                }
            except Exception as exc:
                self.live_data_capture_error_count += 1
                self.last_error = (
                    f"ibkr_stream:{instrument_id}: {type(exc).__name__}: {exc}"
                )
                trade_log(
                    "auto_trading",
                    "ibkr_live_data_subscription_error",
                    instrument_id=instrument_id,
                    error_type=type(exc).__name__,
                    detail=str(exc),
                    execution_authority=False,
                )

    def _teardown_ibkr_streams(
        self,
        market_service: TradingMarketDataService,
    ) -> None:
        if not self._ibkr_streams:
            return
        try:
            provider = market_service.registry.provider("ibkr")
        except Exception:
            provider = None
        for instrument_id, state in list(self._ibkr_streams.items()):
            key = str(state["key"])
            listener_id = str(state["listener_id"])
            bridge = state["bridge"]
            close_upstream = market_service.subscriptions.unsubscribe(key, listener_id)
            if close_upstream and provider is not None:
                with suppress(Exception):
                    provider.unsubscribe_quote(
                        instrument_id,
                        listener=bridge,
                    )
            self._ibkr_streams.pop(instrument_id, None)

    async def _capture_one(self, market_service, candidate):
        binding_id = str(getattr(candidate, "binding_id", "") or "")
        instrument_id = str(getattr(candidate, "instrument_id", "") or "")
        if not instrument_id:
            return None
        if not binding_can_execute(binding_id):
            self.skipped_non_execution_binding_count += 1
            return None
        try:
            observation = await asyncio.to_thread(
                market_service.execution_observation,
                instrument_id,
                binding_id,
            )
        except Exception as exc:
            self.capture_error_count += 1
            self.last_error = (
                f"{instrument_id}: {type(exc).__name__}: {exc}"
            )
            trade_log(
                "auto_trading",
                "execution_observation_capture_error",
                instrument_id=instrument_id,
                binding_id=binding_id,
                error_type=type(exc).__name__,
                detail=str(exc),
                execution_authority=False,
            )
            return None
        if self.plane.record(observation):
            self.capture_count += 1
        return observation

    async def run_once(self) -> int:
        now = self.now_factory()
        if now.tzinfo is None:
            raise ValueError("execution observation monitor clock must be timezone-aware")
        repository = self.strategy_repository_factory()
        market_service = self.market_service_factory()
        configs = await asyncio.to_thread(repository.list_configs, active_only=True)
        candidates = await asyncio.to_thread(
            self._active_candidates,
            repository,
            list(configs),
            now=now,
        )
        self.last_demand_count = len(candidates)

        # IBKR is streaming and purpose-bound to LIVE_DATA. This is safe even
        # during zero-authority rollout because the observation carries no
        # brokerage execution authority.
        await asyncio.to_thread(
            self._sync_ibkr_streams,
            market_service,
            candidates,
        )

        before = self.capture_count
        await asyncio.gather(
            *[
                self._capture_one(market_service, candidate)
                for candidate in candidates.values()
            ]
        )
        self.last_run_at = now
        return self.capture_count - before

    def diagnostics(self) -> dict[str, object]:
        return {
            "enabled": execution_observation_monitor_enabled(),
            "running": self._task is not None,
            "interval_seconds": self.interval_seconds,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_error": self.last_error,
            "active_demand_count": self.last_demand_count,
            "capture_count": self.capture_count,
            "capture_error_count": self.capture_error_count,
            "live_data_capture_count": self.live_data_capture_count,
            "live_data_capture_error_count": self.live_data_capture_error_count,
            "active_ibkr_streams": len(self._ibkr_streams),
            "ibkr_stream_instruments": tuple(sorted(self._ibkr_streams)),
            "skipped_non_execution_binding_count": self.skipped_non_execution_binding_count,
            "causal_fill_policy": "first_source_and_recorded_quote_after_actionable_at",
            "ibkr_binding_purpose": "LIVE_DATA",
            "ibkr_broker_execution_authority": False,
        }

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
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
            service = self.market_service_factory()
            await asyncio.to_thread(self._teardown_ibkr_streams, service)
        except Exception:
            pass


def register_trading_execution_observation_monitor(
    gateway: FastAPI,
) -> TradingExecutionObservationMonitor:
    existing = getattr(gateway.state, _STATE_KEY, None)
    if isinstance(existing, TradingExecutionObservationMonitor):
        return existing
    monitor = TradingExecutionObservationMonitor()
    setattr(gateway.state, _STATE_KEY, monitor)

    async def startup() -> None:
        if execution_observation_monitor_enabled():
            monitor.start()

    async def shutdown() -> None:
        await monitor.stop()

    gateway.router.add_event_handler("startup", startup)
    gateway.router.add_event_handler("shutdown", shutdown)
    return monitor


__all__ = [
    "TradingExecutionObservationMonitor",
    "execution_observation_monitor_enabled",
    "register_trading_execution_observation_monitor",
]
