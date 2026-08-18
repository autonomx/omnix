from __future__ import annotations

from decimal import Decimal

import pytest

from app.trading.execution import ExecutionEligibilityPolicy
from app.trading.providers.alpaca_iex import AlpacaIexExecutionProvider
from app.trading.providers.errors import ProviderDataUnavailableError
from app.trading.providers.registry import ProviderRegistry


class _FixtureResponse:
    def json(self):
        return {
            "latestQuote": {
                "t": "2026-08-18T14:00:00.100000Z",
                "bp": 9.99,
                "ap": 10.01,
                "bs": 300,
                "as": 400,
            },
            "latestTrade": {
                "t": "2026-08-18T14:00:00.050000Z",
                "p": 10.00,
                "s": 100,
            },
            "dailyBar": {"v": 1_250_000},
        }


class _FixtureRuntime:
    session = object()

    def __init__(self):
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _FixtureResponse()


def _credentials(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_ALPACA_API_KEY_ID", "paper-key")
    monkeypatch.setenv("OMNIX_ALPACA_API_SECRET_KEY", "paper-secret")


def test_alpaca_iex_snapshot_produces_execution_eligible_book(monkeypatch) -> None:
    _credentials(monkeypatch)
    runtime = _FixtureRuntime()
    provider = AlpacaIexExecutionProvider(runtime=runtime)

    value = provider.execution_observation(
        "equity:NASDAQ:AAPL",
        policy=ExecutionEligibilityPolicy(max_age_seconds="300", max_spread_bps="100"),
    )

    assert value.provider == "alpaca_iex"
    assert value.binding_id == "alpaca_iex:rest:equity:NASDAQ:AAPL"
    assert value.bid == Decimal("9.99")
    assert value.ask == Decimal("10.01")
    assert value.last == Decimal("10.0")
    assert value.cumulative_volume == Decimal("1250000")
    assert value.session == "regular"
    assert value.freshness_mode == "live"
    assert value.execution_eligible is True
    assert value.rejection_reasons == ()

    url, request = runtime.calls[0]
    assert url.endswith("/v2/stocks/AAPL/snapshot")
    assert request["params"] == {"feed": "iex"}
    assert request["headers"] == {
        "APCA-API-KEY-ID": "paper-key",
        "APCA-API-SECRET-KEY": "paper-secret",
    }


def test_alpaca_iex_fails_closed_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("OMNIX_ALPACA_API_SECRET_KEY", raising=False)
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)

    provider = AlpacaIexExecutionProvider(runtime=_FixtureRuntime())
    with pytest.raises(ProviderDataUnavailableError, match="credentials are not configured"):
        provider.execution_observation("equity:NASDAQ:AAPL")


def test_yahoo_history_binding_uses_alpaca_iex_for_execution(monkeypatch) -> None:
    _credentials(monkeypatch)
    provider = AlpacaIexExecutionProvider(runtime=_FixtureRuntime())
    registry = ProviderRegistry(factories={"alpaca_iex": lambda: provider})
    yahoo_binding = "yahoo:historical_polling:equity:NASDAQ:AAPL"

    value = registry.execution_observation(
        "equity:NASDAQ:AAPL",
        yahoo_binding,
        policy=ExecutionEligibilityPolicy(max_age_seconds="300", max_spread_bps="100"),
    )

    # The persisted paper order keeps its Yahoo/history binding so old and new
    # orders remain matchable, while provider evidence proves the fill quote came
    # from Alpaca IEX.
    assert value.binding_id == yahoo_binding
    assert value.provider == "alpaca_iex"
    assert value.execution_eligible is True
