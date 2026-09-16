from __future__ import annotations

import threading
from collections.abc import AsyncIterator
from datetime import date, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from .cache import TradingMarketDataCache
from .execution import ExecutionEligibilityPolicy, ExecutionObservation
from .market_data_recovery import (
    RecoveredBars,
    aggregate_complete_bars,
    detect_session_gaps,
    reconcile_recovery,
)
from .models import FeedType, MarketBar
from .providers.binance import BinanceMarketDataProvider
from .providers.registry import ProviderRegistry
from .streaming.binance_stream import BinanceWebSocketStream
from .streaming.manager import SharedSubscriptionManager, StreamingBarUpdate


class TradingMarketDataService:
    def __init__(
        self,
        *,
        provider: BinanceMarketDataProvider | None = None,
        registry: ProviderRegistry | None = None,
        cache: TradingMarketDataCache | None = None,
        subscriptions: SharedSubscriptionManager | None = None,
        stream: BinanceWebSocketStream | None = None,
    ) -> None:
        self.cache = cache or TradingMarketDataCache(
            max_entries=256,
            cache_dir=Path("resources/cache/trading"),
        )
        self.registry = registry or ProviderRegistry(cache=self.cache)
        if provider is not None:
            self.registry._providers["binance"] = provider
        self.provider = self.registry.provider("binance")
        self.subscriptions = subscriptions or SharedSubscriptionManager()
        self.stream = stream or BinanceWebSocketStream()

    def bars(
        self,
        instrument_id: str,
        interval: str,
        limit: int = 500,
        binding_id: str | None = None,
        cancellation: threading.Event | None = None,
    ):
        return self.registry.bars(
            instrument_id,
            interval,
            limit,
            binding_id,
            cancellation,
        )

    def recovered_bars(
        self,
        instrument_id: str,
        interval: str,
        limit: int = 500,
        binding_id: str | None = None,
        *,
        session_date: date,
        as_of: datetime,
        max_primary_attempts: int = 2,
        cancellation: threading.Event | None = None,
    ) -> RecoveredBars:
        """Return a canonical causal tape plus explicit recovery evidence.

        The ladder is shared by every strategy/timeframe that opts into this
        service boundary:

        1. acquire/retry the configured provider (bounded);
        2. preserve every factual primary bar across retries;
        3. fetch causal 1m history from the execution feed as one fallback;
        4. deterministically aggregate complete fallback buckets when the
           requested interval is coarser than 1m;
        5. fill only missing requested-timeframe buckets and leave every
           unrecovered interval explicit in ``RecoveryReport.unresolved_gaps``.

        With the default two primary attempts plus one fallback attempt, no
        evaluation causes more than three provider acquisitions. Nothing here
        interpolates prices or silently upgrades a partial-market feed to
        full-market volume authority.
        """

        attempts = max(1, min(int(max_primary_attempts), 2))
        requested = self.registry.resolve_binding(instrument_id, binding_id)
        primary_provider = requested.provider
        primary_response = None
        primary_bars: list[MarketBar] = []
        primary_error: str | None = None
        primary_attempt_count = 0

        for _ in range(attempts):
            primary_attempt_count += 1
            try:
                response = self.registry.bars(
                    instrument_id,
                    interval,
                    limit,
                    requested.binding_id,
                    cancellation,
                )
            except Exception as exc:
                primary_error = f"{type(exc).__name__}: {exc}"
                continue
            primary_response = response
            primary_bars.extend(list(response.bars))
            gaps = detect_session_gaps(
                primary_bars,
                session_date=session_date,
                interval=interval,
                as_of=as_of,
            )
            if not gaps:
                break

        primary_gaps = detect_session_gaps(
            primary_bars,
            session_date=session_date,
            interval=interval,
            as_of=as_of,
        )

        fallback_attempted = False
        fallback_provider: str | None = None
        fallback_bars: list[MarketBar] = []
        fallback_error: str | None = None
        fallback_binding_id: str | None = None

        if primary_gaps:
            try:
                execution_binding = self.registry.resolve_execution_binding(
                    instrument_id,
                    requested.binding_id,
                )
                fallback_provider = execution_binding.provider
                fallback_binding_id = execution_binding.binding_id
                if fallback_provider != primary_provider:
                    fallback_attempted = True
                    one_minute = self.registry.execution_indicator_bars(
                        instrument_id,
                        requested.binding_id,
                        as_of=as_of,
                        cancellation=cancellation,
                    )
                    if interval == "1m":
                        fallback_bars = list(one_minute)
                    else:
                        fallback_bars = aggregate_complete_bars(
                            one_minute,
                            session_date=session_date,
                            target_interval=interval,
                            as_of=as_of,
                        )
            except Exception as exc:
                fallback_error = f"{type(exc).__name__}: {exc}"

        recovered = reconcile_recovery(
            instrument_id=instrument_id,
            interval=interval,
            session_date=session_date,
            as_of=as_of,
            primary_bars=primary_bars,
            fallback_bars=fallback_bars,
            primary_provider=primary_provider,
            fallback_provider=fallback_provider,
            requested_binding=requested.binding_id,
            resolved_binding=(
                fallback_binding_id
                if fallback_attempted and fallback_bars
                else requested.binding_id
            ),
            primary_attempt_count=primary_attempt_count,
            fallback_attempted=fallback_attempted,
            primary_error=primary_error,
            fallback_error=fallback_error,
            partial_market_fallback=fallback_provider == "alpaca_iex",
            primary_response=primary_response,
        )
        return recovered

    def quote(
        self,
        instrument_id: str,
        binding_id: str | None = None,
        cancellation: threading.Event | None = None,
    ) -> dict[str, object]:
        return self.registry.quote(instrument_id, binding_id, cancellation)

    def execution_observation(
        self,
        instrument_id: str,
        binding_id: str | None = None,
        *,
        policy: ExecutionEligibilityPolicy | None = None,
        cancellation: threading.Event | None = None,
    ) -> ExecutionObservation:
        return self.registry.execution_observation(
            instrument_id,
            binding_id,
            policy=policy,
            cancellation=cancellation,
        )

    def execution_indicator_bars(
        self,
        instrument_id: str,
        binding_id: str | None = None,
        *,
        as_of: datetime,
        cancellation: threading.Event | None = None,
    ) -> list[MarketBar]:
        return self.registry.execution_indicator_bars(
            instrument_id,
            binding_id,
            as_of=as_of,
            cancellation=cancellation,
        )

    def currency_rate(
        self,
        base_currency: str,
        quote_currency: str,
        cancellation: threading.Event | None = None,
    ) -> dict[str, object]:
        return self.registry.currency_rate(base_currency, quote_currency, cancellation)

    async def stream_updates(
        self,
        instrument_id: str,
        interval: str,
        binding_id: str | None = None,
    ) -> AsyncIterator[StreamingBarUpdate]:
        binding = self.registry.resolve_binding(instrument_id, binding_id)
        if binding.provider != "binance" or binding.feed_type is not FeedType.WEBSOCKET_AND_REST:
            raise ValueError(
                f"binding does not support Omnix live streaming: {binding.binding_id}"
            )
        async for update in self.stream.messages(
            provider_symbol=binding.provider_symbol,
            binding_id=binding.binding_id,
            instrument_id=instrument_id,
            interval=interval,
        ):
            yield update

    def provider_descriptors(self) -> list[dict[str, object]]:
        return self.registry.descriptors()

    def diagnostics(self) -> dict[str, Any]:
        providers = self.provider_descriptors()
        return {
            "providers": [
                {
                    "provider": item["provider"],
                    "status": item["status"],
                    "binding_count": len(item["bindings"]),
                    "official": item["policy"].is_official_api,
                    "usage_scope": item["policy"].usage_scope,
                    "runtime": item.get("runtime", {}),
                }
                for item in providers
            ],
            "cache": {
                "authority": False,
                "disposable": True,
                "directory": str(self.cache.cache_dir) if self.cache.cache_dir else None,
                "max_entries": self.cache.max_entries,
                "disk_bounded": True,
                "atomic_writes": True,
            },
            "execution": {
                "policy_version": ExecutionEligibilityPolicy().policy_version,
                "fail_closed": True,
                "synthetic_reference_prices_allowed": False,
            },
            "streams": self.subscriptions.status(),
            "upstream_subscription_count": self.subscriptions.upstream_subscription_count,
        }


_default_service: TradingMarketDataService | None = None
_default_lock = Lock()


def default_market_data_service() -> TradingMarketDataService:
    global _default_service
    if _default_service is None:
        with _default_lock:
            if _default_service is None:
                _default_service = TradingMarketDataService()
    return _default_service
