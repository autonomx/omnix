from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from threading import Lock
from typing import Any

from .cache import TradingMarketDataCache
from .providers.binance import BinanceMarketDataProvider
from .streaming.binance_stream import BinanceWebSocketStream
from .streaming.manager import SharedSubscriptionManager, StreamingBarUpdate


class TradingMarketDataService:
    def __init__(
        self,
        *,
        provider: BinanceMarketDataProvider | None = None,
        cache: TradingMarketDataCache | None = None,
        subscriptions: SharedSubscriptionManager | None = None,
        stream: BinanceWebSocketStream | None = None,
    ) -> None:
        self.cache = cache or TradingMarketDataCache(
            max_entries=256,
            cache_dir=Path("resources/cache/trading"),
        )
        self.provider = provider or BinanceMarketDataProvider(cache=self.cache)
        self.subscriptions = subscriptions or SharedSubscriptionManager()
        self.stream = stream or BinanceWebSocketStream()

    def bars(self, instrument_id: str, interval: str, limit: int = 500):
        return self.provider.get_bars(instrument_id, interval, limit)

    def quote(self, instrument_id: str) -> dict[str, object]:
        return self.provider.get_quote(instrument_id)

    async def stream_updates(
        self,
        instrument_id: str,
        interval: str,
    ) -> AsyncIterator[StreamingBarUpdate]:
        binding = self.provider.get_binding(instrument_id)
        async for update in self.stream.messages(
            provider_symbol=binding.provider_symbol,
            binding_id=binding.binding_id,
            instrument_id=instrument_id,
            interval=interval,
        ):
            yield update

    def diagnostics(self) -> dict[str, Any]:
        return {
            "provider": self.provider.provider_id,
            "provider_policy": self.provider.policy.model_dump(mode="json"),
            "cache": {
                "authority": False,
                "disposable": True,
                "directory": str(self.cache.cache_dir) if self.cache.cache_dir else None,
                "max_entries": self.cache.max_entries,
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
