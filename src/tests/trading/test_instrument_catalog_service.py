from __future__ import annotations

from typing import Any

from app.trading.catalog import (
    binding_by_id,
    bindings_for_instrument,
    default_binding,
    instrument_by_id,
)
from app.trading.instrument_catalog_service import ProviderBackedInstrumentCatalog


class FakeResponse:
    status_code = 200
    headers: dict[str, str] = {}

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeRuntime:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((url, kwargs))
        return FakeResponse(self.payload)


def test_provider_catalog_discovers_binance_spot_symbols_and_registers_binding() -> None:
    binance = FakeRuntime(
        {
            "symbols": [
                {
                    "symbol": "ADAUSDT",
                    "status": "TRADING",
                    "isSpotTradingAllowed": True,
                    "baseAsset": "ADA",
                    "quoteAsset": "USDT",
                    "filters": [{"filterType": "PRICE_FILTER", "tickSize": "0.0001"}],
                },
                {
                    "symbol": "DELISTEDUSDT",
                    "status": "BREAK",
                    "isSpotTradingAllowed": True,
                    "baseAsset": "DELISTED",
                    "quoteAsset": "USDT",
                },
            ]
        }
    )
    yahoo = FakeRuntime({"quotes": []})
    catalog = ProviderBackedInstrumentCatalog(binance_runtime=binance, yahoo_runtime=yahoo)

    results = catalog.search("ADA")

    assert [item.display_symbol for item in results] == ["ADAUSDT"]
    instrument = results[0]
    assert instrument_by_id(instrument.instrument_id) == instrument
    binding = default_binding(instrument.instrument_id)
    assert binding is not None
    assert binding.provider == "binance"
    assert binding.provider_symbol == "ADAUSDT"
    assert binding in bindings_for_instrument(instrument.instrument_id)


def test_provider_catalog_discovers_yahoo_equity_search_results() -> None:
    binance = FakeRuntime({"symbols": []})
    yahoo = FakeRuntime(
        {
            "quotes": [
                {
                    "symbol": "AMD",
                    "quoteType": "EQUITY",
                    "exchange": "NMS",
                    "shortname": "Advanced Micro Devices, Inc.",
                }
            ]
        }
    )
    catalog = ProviderBackedInstrumentCatalog(binance_runtime=binance, yahoo_runtime=yahoo)

    results = catalog.search("AMD")

    assert [item.display_symbol for item in results] == ["AMD"]
    instrument = results[0]
    assert instrument.instrument_id == "equity:NASDAQ:AMD"
    assert instrument.venue == "NASDAQ"
    assert {item.provider for item in bindings_for_instrument(instrument.instrument_id)} == {"yahoo", "stooq"}


def test_short_queries_do_not_hit_provider_catalogs() -> None:
    binance = FakeRuntime({"symbols": []})
    yahoo = FakeRuntime({"quotes": []})
    catalog = ProviderBackedInstrumentCatalog(binance_runtime=binance, yahoo_runtime=yahoo)

    catalog.search("A")

    assert binance.calls == []
    assert yahoo.calls == []


def test_persisted_dynamic_equity_id_rehydrates_bindings() -> None:
    instrument_id = "equity:BTS:SPYI"

    binding = default_binding(instrument_id)

    assert binding is not None
    assert binding.provider == "yahoo"
    assert binding.provider_symbol == "SPYI"
    assert instrument_by_id(instrument_id) is not None
    assert {item.provider for item in bindings_for_instrument(instrument_id)} == {
        "yahoo",
        "stooq",
    }
    assert binding_by_id(binding.binding_id) == binding


def test_persisted_dynamic_equity_binding_id_rehydrates_catalog() -> None:
    binding_id = "stooq:historical_daily:equity:BTS:SPYI"

    binding = binding_by_id(binding_id)

    assert binding is not None
    assert binding.binding_id == binding_id
    assert binding.instrument_id == "equity:BTS:SPYI"
