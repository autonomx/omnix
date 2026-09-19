from datetime import datetime, timedelta, timezone
import threading
from decimal import Decimal

import pytest

from app.trading.providers.ibkr_runtime import (
    FakeIbkrTransport,
    IbkrContractAmbiguousError,
    IbkrContractIdentity,
    IbkrHistoricalBar,
    IbkrQuoteSnapshot,
    IbkrRuntime,
    OfficialIbapiTransport,
)


INSTRUMENT = "equity:NASDAQ:AAPL"


def _contract(
    con_id: int = 265598,
    *,
    exchange: str = "SMART",
    primary_exchange: str = "NASDAQ",
) -> IbkrContractIdentity:
    return IbkrContractIdentity(
        con_id=con_id,
        symbol="AAPL",
        local_symbol="AAPL",
        sec_type="STK",
        currency="USD",
        exchange=exchange,
        primary_exchange=primary_exchange,
        trading_class="NMS",
    )


def _runtime(transport: FakeIbkrTransport) -> IbkrRuntime:
    return IbkrRuntime(
        transport=transport,
        enabled=True,
        host="127.0.0.1",
        port=4002,
        client_id=71,
    )


def test_contract_qualification_keeps_unique_conid_and_exchange_identity():
    transport = FakeIbkrTransport(
        contracts={
            "AAPL": [
                _contract(1, primary_exchange="NYSE"),
                _contract(2, primary_exchange="NASDAQ"),
            ]
        }
    )
    runtime = _runtime(transport)

    resolved = runtime.qualify_contract(
        INSTRUMENT,
        symbol="AAPL",
        venue="NASDAQ",
    )

    assert resolved.con_id == 2
    assert resolved.primary_exchange == "NASDAQ"
    assert resolved.local_symbol == "AAPL"


def test_contract_qualification_fails_closed_when_multiple_plausible_rows_remain():
    transport = FakeIbkrTransport(
        contracts={
            "AAPL": [
                _contract(1, primary_exchange="NASDAQ"),
                _contract(2, primary_exchange="NASDAQ"),
            ]
        }
    )
    runtime = _runtime(transport)

    with pytest.raises(IbkrContractAmbiguousError, match="IBKR_CONTRACT_AMBIGUOUS"):
        runtime.qualify_contract(
            INSTRUMENT,
            symbol="AAPL",
            venue="NASDAQ",
        )


def test_quote_subscription_is_deduplicated_across_consumers():
    contract = _contract()
    transport = FakeIbkrTransport(contracts={"AAPL": [contract]})
    runtime = _runtime(transport)
    runtime.connect()
    seen_a = []
    seen_b = []

    token_a = runtime.subscribe_quote(INSTRUMENT, contract=contract, listener=seen_a.append)
    token_b = runtime.subscribe_quote(INSTRUMENT, contract=contract, listener=seen_b.append)

    assert token_a == token_b
    assert len(transport.listeners) == 1
    snapshot = IbkrQuoteSnapshot(
        contract=contract,
        bid=Decimal("100"),
        ask=Decimal("100.02"),
        last=Decimal("100.01"),
        market_data_type="LIVE",
    )
    transport.emit(token_a, snapshot)

    assert seen_a == [snapshot]
    assert seen_b == [snapshot]
    assert runtime.diagnostics()["active_quote_subscriptions"] == 1


def test_gateway_reconnect_invalidates_old_request_ids_quotes_and_resubscribes():
    contract = _contract()
    transport = FakeIbkrTransport(contracts={"AAPL": [contract]})
    runtime = _runtime(transport)
    runtime.connect()
    first = runtime.subscribe_quote(INSTRUMENT, contract=contract)
    assert first in transport.listeners
    stale = IbkrQuoteSnapshot(
        contract=contract,
        bid=Decimal("100"),
        ask=Decimal("100.02"),
        last=Decimal("100.01"),
        source_time=datetime.now(timezone.utc),
        received_at=datetime.now(timezone.utc),
        market_data_type="LIVE",
    )
    transport.emit(first, stale)
    assert runtime.latest_quote(INSTRUMENT) == stale

    transport.disconnect()
    assert runtime.latest_quote(INSTRUMENT) is None

    runtime.connect()
    assert runtime.reconnect_count == 1
    assert runtime.latest_quote(INSTRUMENT) is None
    assert runtime.diagnostics()["active_quote_subscriptions"] == 0

    second = runtime.subscribe_quote(INSTRUMENT, contract=contract)
    assert second != first
    assert second in transport.listeners
    assert runtime.latest_quote(INSTRUMENT) is None


def test_subscription_health_preserves_entitlement_denial():
    contract = _contract()
    transport = FakeIbkrTransport(contracts={"AAPL": [contract]})
    runtime = _runtime(transport)
    token = runtime.subscribe_quote(INSTRUMENT, contract=contract)
    transport.request_health_by_token[token] = {
        "request_id": token,
        "market_data_type": "UNKNOWN",
        "error": {"code": 354, "message": "Not subscribed"},
        "entitlement_denied": True,
    }

    health = runtime.subscription_health(INSTRUMENT)

    assert health["entitlement_denied"] is True
    assert health["error"]["code"] == 354


def test_historical_range_is_clipped_to_requested_window(monkeypatch):
    monkeypatch.setenv("OMNIX_PERSISTENCE_MODE", "legacy_test")
    contract = _contract()
    start = datetime(2026, 9, 17, 13, 30, tzinfo=timezone.utc)
    transport = FakeIbkrTransport(
        contracts={"AAPL": [contract]},
        history={
            contract.con_id: [
                IbkrHistoricalBar(
                    start_time=start - timedelta(minutes=1),
                    open=Decimal("10"),
                    high=Decimal("10"),
                    low=Decimal("10"),
                    close=Decimal("10"),
                    volume=Decimal("10"),
                ),
                IbkrHistoricalBar(
                    start_time=start,
                    open=Decimal("11"),
                    high=Decimal("11"),
                    low=Decimal("11"),
                    close=Decimal("11"),
                    volume=Decimal("11"),
                ),
                IbkrHistoricalBar(
                    start_time=start + timedelta(minutes=1),
                    open=Decimal("12"),
                    high=Decimal("12"),
                    low=Decimal("12"),
                    close=Decimal("12"),
                    volume=Decimal("12"),
                ),
            ]
        },
    )
    runtime = _runtime(transport)

    rows = runtime.historical_bars(
        contract,
        start=start,
        end=start + timedelta(minutes=1),
    )

    assert [row.start_time for row in rows] == [start]
    assert runtime.historical_request_count == 1


def test_official_transport_socket_reset_wakes_waiters_and_clears_request_state():
    transport = OfficialIbapiTransport.__new__(OfficialIbapiTransport)
    transport._lock = threading.RLock()
    transport._connected = threading.Event()
    transport._connected.set()
    contract_event = threading.Event()
    historical_event = threading.Event()
    transport._contract_rows = {1: [_contract()]}
    transport._contract_events = {1: contract_event}
    transport._historical_rows = {
        2: [
            IbkrHistoricalBar(
                start_time=datetime(2026, 9, 17, 13, 30, tzinfo=timezone.utc),
                open=Decimal("1"),
                high=Decimal("1"),
                low=Decimal("1"),
                close=Decimal("1"),
                volume=Decimal("1"),
            )
        ]
    }
    transport._historical_events = {2: historical_event}
    transport._quote_contracts = {3: _contract()}
    transport._quote_listeners = {3: lambda snapshot: None}
    transport._quote_values = {3: {"last": Decimal("100")}}
    transport._market_data_types = {3: "LIVE"}
    transport._request_errors = {2: {"code": 162}}
    transport._farm_status = {"market_data": "READY"}

    transport._reset_socket_state()

    assert not transport._connected.is_set()
    assert contract_event.is_set()
    assert historical_event.is_set()
    assert transport._contract_rows == {}
    assert transport._contract_events == {}
    assert transport._historical_rows == {}
    assert transport._historical_events == {}
    assert transport._quote_contracts == {}
    assert transport._quote_listeners == {}
    assert transport._quote_values == {}
    assert transport._market_data_types == {}
    assert transport._request_errors == {}
    assert transport._farm_status == {}
