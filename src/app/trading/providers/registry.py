from __future__ import annotations

import inspect
import threading
from collections.abc import Callable
from typing import Any

from app.trading.cache import TradingMarketDataCache
from app.trading.catalog import POLICIES, all_bindings, binding_by_id, default_binding
from app.trading.execution import (
    ExecutionEligibilityPolicy,
    ExecutionObservation,
    assess_execution_observation,
    execution_observation_from_quote,
)
from app.trading.models import BarsResponse, ProviderBinding

from .additional_crypto import AdditionalCryptoProvider
from .aggregation import (
    aggregate_market_bars,
    aggregated_dataset_fingerprint,
    aggregation_plan,
)
from .alpaca_iex import AlpacaIexExecutionProvider, alpaca_iex_configured
from .binance import BinanceMarketDataProvider
from .coinmarketcap import CoinMarketCapProvider, coinmarketcap_configured
from .equity import StooqEquityProvider, YahooEquityProvider
from .equity_execution import yahoo_execution_observation
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
            "alpaca_iex": lambda: AlpacaIexExecutionProvider(),
            "stooq": lambda: StooqEquityProvider(cache=self.cache),
            "coinbase": lambda: AdditionalCryptoProvider("coinbase", cache=self.cache),
            "kraken": lambda: AdditionalCryptoProvider("kraken", cache=self.cache),
            "hyperliquid": lambda: AdditionalCryptoProvider("hyperliquid", cache=self.cache),
            "coinmarketcap": lambda: CoinMarketCapProvider(cache=self.cache),
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

    def resolve_execution_binding(
        self,
        instrument_id: str,
        binding_id: str | None = None,
    ) -> ProviderBinding:
        """Resolve the authoritative paper-execution feed without changing chart history.

        Equity charts and strategy bars continue to use Yahoo/Stooq bindings. Any
        equity execution request is overlaid onto the official Alpaca IEX binding.
        Missing Alpaca credentials then fail closed at quote fetch time rather than
        silently falling back to Yahoo or a caller supplied price.
        """
        requested = self.resolve_binding(instrument_id, binding_id)
        if instrument_id.startswith("equity:") and requested.provider in {
            "yahoo",
            "stooq",
            "alpaca_iex",
        }:
            alpaca = next(
                (
                    item
                    for item in all_bindings()
                    if item.instrument_id == instrument_id and item.provider == "alpaca_iex"
                ),
                None,
            )
            if alpaca is not None:
                return alpaca
        return requested

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

    def _bars_for_interval(
        self,
        provider: Any,
        binding: ProviderBinding,
        instrument_id: str,
        interval: str,
        limit: int,
        cancellation: threading.Event | None,
    ) -> BarsResponse:
        plan = aggregation_plan(interval, binding.supported_intervals)
        if plan is None:
            return self._bars(provider, instrument_id, interval, limit, cancellation)

        base_interval, factor = plan
        base_limit = min(5_000, max(1, limit * factor + factor - 1))
        base_response = self._bars(
            provider,
            instrument_id,
            base_interval,
            base_limit,
            cancellation,
        )
        bars = aggregate_market_bars(
            base_response.bars,
            target_interval=interval,
            base_interval=base_interval,
            factor=factor,
        )
        provenance = base_response.provenance.model_copy(
            update={
                "as_of": bars[-1].end_time if bars else base_response.provenance.as_of,
                "dataset_fingerprint": aggregated_dataset_fingerprint(
                    base_response.provenance.dataset_fingerprint,
                    target_interval=interval,
                    base_interval=base_interval,
                    factor=factor,
                ),
                "history_complete": base_response.provenance.history_complete,
            }
        )
        return base_response.model_copy(
            update={
                "interval": interval,
                "bars": bars,
                "provenance": provenance,
            }
        )

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
            return self._bars_for_interval(
                self.provider(requested.provider),
                requested,
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
                    for item in all_bindings()
                    if item.instrument_id == instrument_id and item.provider == "stooq"
                ),
                None,
            )
            if fallback is None:
                raise
            result = self._bars_for_interval(
                self.provider("stooq"),
                fallback,
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

    def execution_observation(
        self,
        instrument_id: str,
        binding_id: str | None = None,
        *,
        policy: ExecutionEligibilityPolicy | None = None,
        cancellation: threading.Event | None = None,
    ) -> ExecutionObservation:
        requested = self.resolve_binding(instrument_id, binding_id)
        binding = self.resolve_execution_binding(instrument_id, requested.binding_id)
        provider = self.provider(binding.provider)
        if binding.provider == "alpaca_iex":
            observation = provider.execution_observation(
                instrument_id,
                policy=policy,
                cancellation=cancellation,
            )
            if requested.binding_id != binding.binding_id:
                observation = observation.model_copy(update={"binding_id": requested.binding_id})
            return observation
        if binding.provider == "yahoo":
            return yahoo_execution_observation(
                provider,
                instrument_id,
                policy=policy,
                cancellation=cancellation,
            )
        quote = self.quote(instrument_id, binding.binding_id, cancellation)
        observation = execution_observation_from_quote(
            quote,
            binding_id=binding.binding_id,
            provider=binding.provider,
        )
        return assess_execution_observation(observation, policy)

    def currency_rate(
        self,
        base_currency: str,
        quote_currency: str,
        cancellation: threading.Event | None = None,
    ) -> dict[str, object]:
        provider = self.provider("yahoo")
        method = getattr(provider, "get_currency_rate", None)
        if not callable(method):
            raise ValueError("Yahoo provider does not support currency conversion")
        if self._supports_cancellation(method):
            return method(base_currency, quote_currency, cancellation=cancellation)
        return method(base_currency, quote_currency)

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
            configured = (
                alpaca_iex_configured()
                if provider_id == "alpaca_iex"
                else coinmarketcap_configured()
                if provider_id == "coinmarketcap"
                else True
            )
            descriptors.append(
                {
                    "provider": provider_id,
                    "display_name": (
                        "Alpaca IEX"
                        if provider_id == "alpaca_iex"
                        else "CoinMarketCap"
                        if provider_id == "coinmarketcap"
                        else provider_id.title()
                    ),
                    "enabled": configured,
                    "status": (
                        snapshot.status if configured and snapshot is not None else "unconfigured"
                        if not configured
                        else "ready"
                    ),
                    "policy": policy,
                    "bindings": [
                        binding for binding in all_bindings() if binding.provider == provider_id
                    ],
                    "runtime": runtime_payload,
                }
            )
        return descriptors
