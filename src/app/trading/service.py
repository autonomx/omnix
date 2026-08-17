from __future__ import annotations

import threading
from collections.abc import AsyncIterator
from pathlib import Path
from threading import Lock
from typing import Any

from .cache import TradingMarketDataCache
from .models import FeedType
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

    def quote(
        self,
        instrument_id: str,
        binding_id: str | None = None,
        cancellation: threading.Event | None = None,
    ) -> dict[str, object]:
        return self.registry.quote(instrument_id, binding_id, cancellation)

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
