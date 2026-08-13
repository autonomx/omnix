from __future__ import annotations

import inspect
import threading
from collections.abc import Callable
from typing import Any

from app.trading.cache import TradingMarketDataCache
from app.trading.catalog import BINDINGS, POLICIES, binding_by_id, default_binding
from app.trading.models import BarsResponse, ProviderBinding

from .additional_crypto import AdditionalCryptoProvider
from .binance import BinanceMarketDataProvider
from .equity import StooqEquityProvider, YahooEquityProvider
from .errors import ProviderFallbackEligibleError


class ProviderRegistry:
    def __init__(
        self,
        *,
        cache: TradingMarketDataCache | None = None,
        factories: dict[str, Callable[[], Any]] | None = None,
    ) -> None:
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

    def resolve_binding(
        self,
        instrument_id: str,
        binding_id: str | None = None,
    ) -> ProviderBinding:
        binding = binding_by_id(binding_id) if binding_id else default_binding(instrument_id)
        if binding is None or binding.instrument_id != instrument_id:
            raise ValueError(f"invalid provider binding for {instrument_id}: {binding_id}")
        return binding

    @staticmethod
    def _supports_cancellation(function: Callable[..., Any]) -> bool:
        try:
            return "cancellation" in inspect.signature(function).parameters
        except (TypeError, ValueError):
            return False

    def _bars(
        self,
        provider: Any,
        instrument_id: str,
        interval: str,
        limit: int,
        cancellation: threading.Event | None,
    ) -> BarsResponse:
        if self._supports_cancellation(provider.get_bars):
            return provider.get_bars(
                instrument_id,
                interval,
                limit,
                cancellation=cancellation,
            )
        return provider.get_bars(instrument_id, interval, limit)

    def bars(
        self,
        instrument_id: str,
        interval: str,
        limit: int,
        binding_id: str | None = None,
        cancellation: threading.Event | None = None,
    ) -> BarsResponse:
        requested = self.resolve_binding(instrument_id, binding_id)
        try:
            return self._bars(
                self.provider(requested.provider),
                instrument_id,
                interval,
                limit,
                cancellation,
            )
        except ProviderFallbackEligibleError as primary_error:
            if requested.provider != "yahoo" or interval != "1d":
                raise
            fallback = next(
                (
                    item
                    for item in BINDINGS
                    if item.instrument_id == instrument_id and item.provider == "stooq"
                ),
                None,
            )
            if fallback is None:
                raise
            result = self._bars(
                self.provider("stooq"),
                instrument_id,
                interval,
                limit,
                cancellation,
            )
            result.provenance = result.provenance.model_copy(
                update={
                    "requested_binding": requested.binding_id,
                    "resolved_binding": fallback.binding_id,
                    "fallback_reason": (
                        f"Yahoo whole-dataset fallback: {type(primary_error).__name__}"
                    ),
                    "freshness_mode": "fallback",
                }
            )
            return result

    def quote(
        self,
        instrument_id: str,
        binding_id: str | None = None,
        cancellation: threading.Event | None = None,
    ) -> dict[str, object]:
        binding = self.resolve_binding(instrument_id, binding_id)
        provider = self.provider(binding.provider)
        if self._supports_cancellation(provider.get_quote):
            return provider.get_quote(instrument_id, cancellation=cancellation)
        return provider.get_quote(instrument_id)

    def descriptors(self) -> list[dict[str, object]]:
        descriptors: list[dict[str, object]] = []
        for provider_id, policy in POLICIES.items():
            provider = self.provider(provider_id)
            runtime = getattr(provider, "runtime", None)
            snapshot = runtime.snapshot() if runtime is not None else None
            runtime_payload = (
                {
                    "request_count": snapshot.request_count,
                    "success_count": snapshot.success_count,
                    "failure_count": snapshot.failure_count,
                    "consecutive_failures": snapshot.consecutive_failures,
                    "rate_limit_count": snapshot.rate_limit_count,
                    "in_flight": snapshot.in_flight,
                    "max_concurrency": snapshot.max_concurrency,
                    "last_success_at": snapshot.last_success_at,
                    "last_failure_at": snapshot.last_failure_at,
                    "last_error": snapshot.last_error,
                }
                if snapshot is not None
                else {}
            )
            descriptors.append(
                {
                    "provider": provider_id,
                    "display_name": provider_id.title(),
                    "enabled": True,
                    "status": snapshot.status if snapshot is not None else "ready",
                    "policy": policy,
                    "bindings": [
                        binding for binding in BINDINGS if binding.provider == provider_id
                    ],
                    "runtime": runtime_payload,
                }
            )
        return descriptors
