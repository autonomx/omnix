from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.trading.cache import TradingMarketDataCache
from app.trading.catalog import BINDINGS, POLICIES, binding_by_id, default_binding
from app.trading.models import BarsResponse, ProviderBinding

from .additional_crypto import AdditionalCryptoProvider
from .binance import BinanceMarketDataProvider
from .equity import StooqEquityProvider, YahooEquityProvider


class ProviderRegistry:
    def __init__(self, *, cache: TradingMarketDataCache | None = None, factories: dict[str, Callable[[], Any]] | None = None) -> None:
        self.cache = cache or TradingMarketDataCache()
        self._factories = factories or {
            "binance": lambda: BinanceMarketDataProvider(cache=self.cache),
            "yahoo": lambda: YahooEquityProvider(cache=self.cache),
            "stooq": lambda: StooqEquityProvider(cache=self.cache),
            "coinbase": lambda: AdditionalCryptoProvider("coinbase", cache=self.cache),
            "kraken": lambda: AdditionalCryptoProvider("kraken", cache=self.cache),
            "hyperliquid": lambda: AdditionalCryptoProvider("hyperliquid", cache=self.cache),
        }
        self._providers: dict[str, Any] = {}

    def provider(self, provider_id: str):
        if provider_id not in self._factories:
            raise ValueError(f"unknown Trading provider: {provider_id}")
        return self._providers.setdefault(provider_id, self._factories[provider_id]())

    def resolve_binding(self, instrument_id: str, binding_id: str | None = None) -> ProviderBinding:
        binding = binding_by_id(binding_id) if binding_id else default_binding(instrument_id)
        if binding is None or binding.instrument_id != instrument_id:
            raise ValueError(f"invalid provider binding for {instrument_id}: {binding_id}")
        return binding

    def bars(self, instrument_id: str, interval: str, limit: int, binding_id: str | None = None) -> BarsResponse:
        requested = self.resolve_binding(instrument_id, binding_id)
        try:
            return self.provider(requested.provider).get_bars(instrument_id, interval, limit)
        except Exception as primary_error:
            if requested.provider != "yahoo" or interval != "1d":
                raise
            fallback = next((item for item in BINDINGS if item.instrument_id == instrument_id and item.provider == "stooq"), None)
            if fallback is None:
                raise
            result = self.provider("stooq").get_bars(instrument_id, interval, limit)
            result.provenance = result.provenance.model_copy(update={
                "requested_binding": requested.binding_id,
                "resolved_binding": fallback.binding_id,
                "fallback_reason": f"Yahoo whole-dataset fallback: {type(primary_error).__name__}",
                "freshness_mode": "fallback",
            })
            return result

    def quote(self, instrument_id: str, binding_id: str | None = None) -> dict[str, object]:
        binding = self.resolve_binding(instrument_id, binding_id)
        return self.provider(binding.provider).get_quote(instrument_id)

    def descriptors(self) -> list[dict[str, object]]:
        return [
            {
                "provider": provider_id,
                "display_name": provider_id.title(),
                "enabled": True,
                "status": "ready",
                "policy": policy,
                "bindings": [binding for binding in BINDINGS if binding.provider == provider_id],
            }
            for provider_id, policy in POLICIES.items()
        ]
