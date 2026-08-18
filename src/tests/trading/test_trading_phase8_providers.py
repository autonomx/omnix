from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.trading.api import create_trading_router
from app.trading.catalog import (
    POLICIES,
    binding_by_id,
    bindings_for_instrument,
    instrument_by_id,
)
from app.trading.models import BarsResponse, DatasetProvenance, MarketBar
from app.trading.providers.errors import ProviderUnavailableError
from app.trading.providers.registry import ProviderRegistry
from app.trading.service import TradingMarketDataService


AAPL = "equity:NASDAQ:AAPL"


def bars_response(instrument_id: str, provider_id: str) -> BarsResponse:
    instrument = instrument_by_id(instrument_id)
    binding = next(
        item
        for item in bindings_for_instrument(instrument_id)
        if item.provider == provider_id
    )
    assert instrument is not None
    now = datetime(2026, 8, 5, tzinfo=timezone.utc)
    bar = MarketBar(
        instrument_id=instrument_id,
        interval="1d",
        start_time=now,
        end_time=now,
        open=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("99"),
        close=Decimal("101"),
        volume=Decimal("1000"),
        provider=provider_id,
        provider_event_id=f"{provider_id}-1",
        received_at=now,
    )
    return BarsResponse(
        instrument=instrument,
        binding=binding,
        provenance=DatasetProvenance(
            instrument_id=instrument_id,
            requested_binding=binding.binding_id,
            resolved_binding=binding.binding_id,
            dataset_fingerprint=f"{provider_id}-fingerprint",
            freshness_mode="polled",
            as_of=now,
            received_at=now,
            cached=False,
            history_complete=True,
        ),
        interval="1d",
        bars=[bar],
    )


class FixtureProvider:
    def __init__(self, provider_id: str, *, fail: bool = False) -> None:
        self.provider_id = provider_id
        self.policy = POLICIES[provider_id]
        self.fail = fail
        self.calls = 0

    def get_bars(self, instrument_id: str, interval: str, limit: int = 500):
        self.calls += 1
        if self.fail:
            raise ProviderUnavailableError(f"{self.provider_id} unavailable")
        return bars_response(instrument_id, self.provider_id)

    def get_quote(self, instrument_id: str):
        result = self.get_bars(instrument_id, "1d", 1)
        return {
            "instrument_id": instrument_id,
            "binding_id": result.binding.binding_id,
            "provider": self.provider_id,
            "price": str(result.bars[-1].close),
            "received_at": result.provenance.received_at.isoformat(),
            "freshness_mode": result.provenance.freshness_mode,
        }


def registry_with_fixtures() -> ProviderRegistry:
    providers = {
        provider_id: FixtureProvider(provider_id)
        for provider_id in POLICIES
    }
    providers["yahoo"] = FixtureProvider("yahoo", fail=True)
    return ProviderRegistry(
        factories={
            provider_id: (lambda provider=provider: provider)
            for provider_id, provider in providers.items()
        }
    )


def test_equity_bindings_preserve_one_canonical_instrument() -> None:
    bindings = bindings_for_instrument(AAPL)
    assert {item.provider for item in bindings} == {"yahoo", "alpaca_iex", "stooq"}
    assert {item.instrument_id for item in bindings} == {AAPL}
    assert POLICIES["yahoo"].is_official_api is False
    assert POLICIES["yahoo"].usage_scope.value == "personal_local"
    assert POLICIES["alpaca_iex"].is_official_api is True
    assert POLICIES["alpaca_iex"].authentication_required is True
    assert next(item for item in bindings if item.provider == "yahoo").adjustment_capabilities == ("raw",)


def test_yahoo_failure_uses_a_whole_stooq_dataset() -> None:
    registry = registry_with_fixtures()
    yahoo = next(item for item in bindings_for_instrument(AAPL) if item.provider == "yahoo")
    result = registry.bars(AAPL, "1d", 100, yahoo.binding_id)

    assert result.instrument.instrument_id == AAPL
    assert result.binding.provider == "stooq"
    assert result.provenance.requested_binding == yahoo.binding_id
    assert result.provenance.resolved_binding == result.binding.binding_id
    assert result.provenance.freshness_mode == "fallback"
    assert result.provenance.fallback_reason
    assert {bar.provider for bar in result.bars} == {"stooq"}


def test_programming_failure_does_not_silently_fallback() -> None:
    class BrokenProvider(FixtureProvider):
        def get_bars(self, instrument_id: str, interval: str, limit: int = 500):
            raise TypeError("adapter bug")

    providers = {provider_id: FixtureProvider(provider_id) for provider_id in POLICIES}
    providers["yahoo"] = BrokenProvider("yahoo")
    registry = ProviderRegistry(
        factories={
            provider_id: (lambda provider=provider: provider)
            for provider_id, provider in providers.items()
        }
    )
    yahoo = next(item for item in bindings_for_instrument(AAPL) if item.provider == "yahoo")
    with pytest.raises(TypeError, match="adapter bug"):
        registry.bars(AAPL, "1d", 100, yahoo.binding_id)


def test_provider_routes_forward_binding_and_expose_policy() -> None:
    registry = registry_with_fixtures()
    service = TradingMarketDataService(registry=registry)
    app = FastAPI()
    app.include_router(create_trading_router(market_service_factory=lambda: service))
    client = TestClient(app)

    providers = client.get("/api/trading/providers/status")
    assert providers.status_code == 200
    payload = providers.json()["providers"]
    assert {item["provider"] for item in payload} == set(POLICIES)
    yahoo = next(item for item in payload if item["provider"] == "yahoo")
    assert yahoo["policy"]["is_official_api"] is False

    yahoo_binding = next(
        item for item in bindings_for_instrument(AAPL) if item.provider == "yahoo"
    )
    response = client.get(
        "/api/trading/bars",
        params={
            "instrument_id": AAPL,
            "interval": "1d",
            "limit": 50,
            "binding_id": yahoo_binding.binding_id,
        },
    )
    assert response.status_code == 200
    assert response.json()["instrument"]["instrument_id"] == AAPL
    assert response.json()["binding"]["provider"] == "stooq"


def test_non_websocket_binding_is_rejected_by_stream_boundary() -> None:
    registry = registry_with_fixtures()
    service = TradingMarketDataService(registry=registry)
    stooq = next(item for item in bindings_for_instrument(AAPL) if item.provider == "stooq")

    async def first_update():
        return await service.stream_updates(AAPL, "1d", stooq.binding_id).__anext__()

    with pytest.raises(ValueError, match="does not support"):
        asyncio.run(first_update())


def test_binding_validation_rejects_cross_instrument_binding() -> None:
    registry = registry_with_fixtures()
    bitcoin = "crypto:BINANCE:spot:BTC-USDT"
    foreign = binding_by_id(
        next(item for item in bindings_for_instrument(AAPL) if item.provider == "stooq").binding_id
    )
    assert foreign is not None
    with pytest.raises(ValueError, match="invalid provider binding"):
        registry.resolve_binding(bitcoin, foreign.binding_id)
