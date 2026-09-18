from __future__ import annotations

"""Process-wide IBKR Gateway transport and runtime.

The official IBKR Python client is intentionally optional. Omnix never stores an
IBKR username, password, or API key; authentication remains inside IB Gateway.
Unit tests use FakeIbkrTransport so CI does not require Gateway or IBKR's local
TWS API installation.
"""

import os
import threading
import time as time_module
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol


IBKR_MARKET_DATA_TYPES = {
    1: "LIVE",
    2: "FROZEN",
    3: "DELAYED",
    4: "DELAYED_FROZEN",
}


class IbkrRuntimeError(RuntimeError):
    pass


class IbkrClientUnavailableError(IbkrRuntimeError):
    pass


class IbkrContractUnavailableError(IbkrRuntimeError):
    pass


class IbkrContractAmbiguousError(IbkrRuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class IbkrContractIdentity:
    con_id: int
    symbol: str
    local_symbol: str
    sec_type: str
    currency: str
    exchange: str
    primary_exchange: str
    trading_class: str = ""
    qualified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True, slots=True)
class IbkrQuoteSnapshot:
    contract: IbkrContractIdentity
    bid: Decimal | None = None
    ask: Decimal | None = None
    bid_size: Decimal | None = None
    ask_size: Decimal | None = None
    last: Decimal | None = None
    last_size: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    cumulative_volume: Decimal | None = None
    source_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    market_data_type: str = "UNKNOWN"
    provider_sequence: int | None = None

    @property
    def live_entitled(self) -> bool:
        return self.market_data_type == "LIVE"


@dataclass(frozen=True, slots=True)
class IbkrHistoricalBar:
    start_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class IbkrTransport(Protocol):
    def connect(self, host: str, port: int, client_id: int, timeout_seconds: float = 8.0) -> None: ...
    def disconnect(self) -> None: ...
    def is_connected(self) -> bool: ...
    def qualify_stock(self, symbol: str, *, currency: str = "USD") -> list[IbkrContractIdentity]: ...
    def subscribe_quote(
        self,
        contract: IbkrContractIdentity,
        listener: Callable[[IbkrQuoteSnapshot], None],
    ) -> int: ...
    def unsubscribe_quote(self, token: int) -> None: ...
    def historical_bars(
        self,
        contract: IbkrContractIdentity,
        *,
        end: datetime,
        duration_seconds: int,
        bar_size: str,
        what_to_show: str,
        use_rth: bool,
        timeout_seconds: float = 20.0,
    ) -> list[IbkrHistoricalBar]: ...
    def request_health(self, token: int) -> dict[str, object]: ...
    def diagnostics(self) -> dict[str, object]: ...


def official_ibapi_available() -> bool:
    try:
        import ibapi  # type: ignore[import-not-found]  # noqa: F401
    except Exception:
        return False
    return True


class OfficialIbapiTransport:
    """Thin adapter around IBKR's locally installed official ibapi package."""

    def __init__(self) -> None:
        try:
            from ibapi.client import EClient  # type: ignore[import-not-found]
            from ibapi.contract import Contract  # type: ignore[import-not-found]
            from ibapi.wrapper import EWrapper  # type: ignore[import-not-found]
        except Exception as exc:
            raise IbkrClientUnavailableError(
                "official IBKR ibapi package is not installed"
            ) from exc

        self._Contract = Contract
        self._lock = threading.RLock()
        self._connected = threading.Event()
        self._next_request_id = 10_000
        self._thread: threading.Thread | None = None
        self._contract_rows: dict[int, list[IbkrContractIdentity]] = {}
        self._contract_events: dict[int, threading.Event] = {}
        self._historical_rows: dict[int, list[IbkrHistoricalBar]] = {}
        self._historical_events: dict[int, threading.Event] = {}
        self._quote_contracts: dict[int, IbkrContractIdentity] = {}
        self._quote_listeners: dict[int, Callable[[IbkrQuoteSnapshot], None]] = {}
        self._quote_values: dict[int, dict[str, object]] = {}
        self._market_data_types: dict[int, str] = {}
        self._request_errors: dict[int, dict[str, object]] = {}
        self._farm_status: dict[str, str] = {}
        self._sequence = 0
        self._last_error: str | None = None
        self._error_count = 0
        self._entitlement_error_count = 0
        owner = self

        class Wrapper(EWrapper):
            def nextValidId(self, orderId):  # noqa: N802
                owner._connected.set()

            def connectionClosed(self):  # noqa: N802
                owner._connected.clear()

            def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):  # noqa: N802
                code = int(errorCode)
                request_id = int(reqId)
                message = str(errorString)
                owner._error_count += 1
                owner._last_error = f"{request_id}:{code}:{message}"

                entitlement_denied = code in {354, 10089, 10167, 10168}
                if entitlement_denied:
                    owner._entitlement_error_count += 1
                if request_id >= 0:
                    owner._request_errors[request_id] = {
                        "code": code,
                        "message": message,
                        "entitlement_denied": entitlement_denied,
                        "observed_at": datetime.now(timezone.utc).isoformat(),
                    }

                farm_names = {
                    2103: ("market_data", "DISCONNECTED"),
                    2104: ("market_data", "READY"),
                    2105: ("historical_data", "DISCONNECTED"),
                    2106: ("historical_data", "READY"),
                    2157: ("sec_def", "DISCONNECTED"),
                    2158: ("sec_def", "READY"),
                }
                farm = farm_names.get(code)
                if farm is not None:
                    owner._farm_status[farm[0]] = farm[1]

            def contractDetails(self, reqId, details):  # noqa: N802
                contract = details.contract
                row = IbkrContractIdentity(
                    con_id=int(getattr(contract, "conId", 0) or 0),
                    symbol=str(getattr(contract, "symbol", "") or "").upper(),
                    local_symbol=str(getattr(contract, "localSymbol", "") or "").upper(),
                    sec_type=str(getattr(contract, "secType", "") or "").upper(),
                    currency=str(getattr(contract, "currency", "") or "").upper(),
                    exchange=str(getattr(contract, "exchange", "") or "").upper(),
                    primary_exchange=str(getattr(contract, "primaryExchange", "") or "").upper(),
                    trading_class=str(getattr(contract, "tradingClass", "") or "").upper(),
                )
                owner._contract_rows.setdefault(int(reqId), []).append(row)

            def contractDetailsEnd(self, reqId):  # noqa: N802
                event = owner._contract_events.get(int(reqId))
                if event is not None:
                    event.set()

            def marketDataType(self, reqId, marketDataType):  # noqa: N802
                owner._market_data_types[int(reqId)] = IBKR_MARKET_DATA_TYPES.get(
                    int(marketDataType), "UNKNOWN"
                )
                owner._emit_quote(int(reqId))

            def tickPrice(self, reqId, tickType, price, attrib):  # noqa: N802
                mapping = {1: "bid", 2: "ask", 4: "last", 6: "high", 7: "low"}
                field_name = mapping.get(int(tickType))
                if field_name and price is not None and float(price) > 0:
                    owner._quote_values.setdefault(int(reqId), {})[field_name] = Decimal(str(price))
                    owner._emit_quote(int(reqId))

            def tickSize(self, reqId, tickType, size):  # noqa: N802
                mapping = {0: "bid_size", 3: "ask_size", 5: "last_size", 8: "cumulative_volume"}
                field_name = mapping.get(int(tickType))
                if field_name and size is not None:
                    owner._quote_values.setdefault(int(reqId), {})[field_name] = Decimal(str(size))
                    owner._emit_quote(int(reqId))

            def tickString(self, reqId, tickType, value):  # noqa: N802
                if int(tickType) == 45:
                    try:
                        parsed = datetime.fromtimestamp(float(value), tz=timezone.utc)
                    except Exception:
                        return
                    owner._quote_values.setdefault(int(reqId), {})["source_time"] = parsed
                    owner._emit_quote(int(reqId))

            def historicalData(self, reqId, bar):  # noqa: N802
                raw_date = getattr(bar, "date", "")
                try:
                    start = datetime.fromtimestamp(float(raw_date), tz=timezone.utc)
                except Exception:
                    text = str(raw_date)
                    parsed = None
                    for fmt in ("%Y%m%d  %H:%M:%S", "%Y%m%d-%H:%M:%S", "%Y%m%d"):
                        try:
                            parsed = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
                            break
                        except ValueError:
                            continue
                    if parsed is None:
                        return
                    start = parsed
                owner._historical_rows.setdefault(int(reqId), []).append(
                    IbkrHistoricalBar(
                        start_time=start,
                        open=Decimal(str(bar.open)),
                        high=Decimal(str(bar.high)),
                        low=Decimal(str(bar.low)),
                        close=Decimal(str(bar.close)),
                        volume=Decimal(str(bar.volume)),
                    )
                )

            def historicalDataEnd(self, reqId, start, end):  # noqa: N802
                event = owner._historical_events.get(int(reqId))
                if event is not None:
                    event.set()

        self._wrapper = Wrapper()
        self._client = EClient(self._wrapper)

    def _request_id(self) -> int:
        with self._lock:
            self._next_request_id += 1
            return self._next_request_id

    def _emit_quote(self, req_id: int) -> None:
        contract = self._quote_contracts.get(req_id)
        listener = self._quote_listeners.get(req_id)
        values = self._quote_values.get(req_id, {})
        if contract is None or listener is None:
            return
        self._sequence += 1
        now = datetime.now(timezone.utc)
        snapshot = IbkrQuoteSnapshot(
            contract=contract,
            bid=values.get("bid"),
            ask=values.get("ask"),
            bid_size=values.get("bid_size"),
            ask_size=values.get("ask_size"),
            last=values.get("last"),
            last_size=values.get("last_size"),
            high=values.get("high"),
            low=values.get("low"),
            cumulative_volume=values.get("cumulative_volume"),
            source_time=values.get("source_time") or now,
            received_at=now,
            market_data_type=self._market_data_types.get(req_id, "UNKNOWN"),
            provider_sequence=self._sequence,
        )
        try:
            listener(snapshot)
        except Exception:
            # A consumer failure must never kill the IBKR network thread.
            return

    def connect(self, host: str, port: int, client_id: int, timeout_seconds: float = 8.0) -> None:
        if self.is_connected():
            return
        self._client.connect(host, int(port), clientId=int(client_id))
        self._thread = threading.Thread(
            target=self._client.run,
            name="omnix-ibkr-api",
            daemon=True,
        )
        self._thread.start()
        if not self._connected.wait(timeout_seconds):
            self.disconnect()
            raise IbkrRuntimeError("ibkr_gateway_handshake_timeout")

    def disconnect(self) -> None:
        try:
            self._client.disconnect()
        finally:
            self._connected.clear()

    def is_connected(self) -> bool:
        return bool(self._client.isConnected()) and self._connected.is_set()

    def _stock_contract(self, symbol: str):
        contract = self._Contract()
        contract.symbol = symbol.upper()
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"
        return contract

    def _qualified_contract(self, identity: IbkrContractIdentity):
        contract = self._Contract()
        contract.conId = identity.con_id
        contract.symbol = identity.symbol
        contract.localSymbol = identity.local_symbol
        contract.secType = identity.sec_type
        contract.exchange = "SMART"
        contract.primaryExchange = identity.primary_exchange
        contract.currency = identity.currency
        if identity.trading_class:
            contract.tradingClass = identity.trading_class
        return contract

    def qualify_stock(self, symbol: str, *, currency: str = "USD") -> list[IbkrContractIdentity]:
        if not self.is_connected():
            raise IbkrRuntimeError("ibkr_gateway_disconnected")
        req_id = self._request_id()
        event = threading.Event()
        self._contract_events[req_id] = event
        self._contract_rows[req_id] = []
        contract = self._stock_contract(symbol)
        contract.currency = currency.upper()
        self._client.reqContractDetails(req_id, contract)
        if not event.wait(10.0):
            raise IbkrRuntimeError("ibkr_contract_details_timeout")
        rows = list(self._contract_rows.pop(req_id, []))
        self._contract_events.pop(req_id, None)
        return rows

    def subscribe_quote(
        self,
        contract: IbkrContractIdentity,
        listener: Callable[[IbkrQuoteSnapshot], None],
    ) -> int:
        if not self.is_connected():
            raise IbkrRuntimeError("ibkr_gateway_disconnected")
        req_id = self._request_id()
        self._quote_contracts[req_id] = contract
        self._quote_listeners[req_id] = listener
        self._quote_values[req_id] = {}
        self._client.reqMarketDataType(1)
        self._client.reqMktData(
            req_id,
            self._qualified_contract(contract),
            "",
            False,
            False,
            [],
        )
        return req_id

    def unsubscribe_quote(self, token: int) -> None:
        req_id = int(token)
        try:
            self._client.cancelMktData(req_id)
        finally:
            self._quote_contracts.pop(req_id, None)
            self._quote_listeners.pop(req_id, None)
            self._quote_values.pop(req_id, None)
            self._market_data_types.pop(req_id, None)

    def historical_bars(
        self,
        contract: IbkrContractIdentity,
        *,
        end: datetime,
        duration_seconds: int,
        bar_size: str,
        what_to_show: str,
        use_rth: bool,
        timeout_seconds: float = 20.0,
    ) -> list[IbkrHistoricalBar]:
        if not self.is_connected():
            raise IbkrRuntimeError("ibkr_gateway_disconnected")
        if end.tzinfo is None:
            raise ValueError("ibkr historical end must be timezone-aware")
        req_id = self._request_id()
        event = threading.Event()
        self._historical_events[req_id] = event
        self._historical_rows[req_id] = []
        seconds = max(1, int(duration_seconds))
        duration = f"{seconds} S" if seconds <= 86_400 else f"{max(1, (seconds + 86_399) // 86_400)} D"
        end_text = end.astimezone(timezone.utc).strftime("%Y%m%d %H:%M:%S UTC")
        self._client.reqHistoricalData(
            req_id,
            self._qualified_contract(contract),
            end_text,
            duration,
            bar_size,
            what_to_show,
            1 if use_rth else 0,
            2,
            False,
            [],
        )
        if not event.wait(timeout_seconds):
            try:
                self._client.cancelHistoricalData(req_id)
            except Exception:
                pass
            raise IbkrRuntimeError("ibkr_historical_data_timeout")
        rows = list(self._historical_rows.pop(req_id, []))
        self._historical_events.pop(req_id, None)
        return rows

    def request_health(self, token: int) -> dict[str, object]:
        request_id = int(token)
        error = self._request_errors.get(request_id)
        return {
            "request_id": request_id,
            "market_data_type": self._market_data_types.get(request_id, "UNKNOWN"),
            "error": dict(error) if error is not None else None,
            "entitlement_denied": bool(error and error.get("entitlement_denied")),
        }

    def diagnostics(self) -> dict[str, object]:
        recent_errors = {
            str(key): dict(value)
            for key, value in sorted(self._request_errors.items())[-20:]
        }
        return {
            "transport": "official_ibapi",
            "connected": self.is_connected(),
            "active_quote_subscriptions": len(self._quote_listeners),
            "last_error": self._last_error,
            "error_count": self._error_count,
            "entitlement_error_count": self._entitlement_error_count,
            "farm_status": dict(self._farm_status),
            "recent_request_errors": recent_errors,
        }


class FakeIbkrTransport:
    """Deterministic transport for provider/runtime unit tests."""

    def __init__(
        self,
        *,
        contracts: dict[str, list[IbkrContractIdentity]] | None = None,
        history: dict[int, list[IbkrHistoricalBar]] | None = None,
    ) -> None:
        self.contracts = contracts or {}
        self.history = history or {}
        self.connected = False
        self.listeners: dict[int, tuple[IbkrContractIdentity, Callable[[IbkrQuoteSnapshot], None]]] = {}
        self.request_health_by_token: dict[int, dict[str, object]] = {}
        self._next_token = 1

    def connect(self, host: str, port: int, client_id: int, timeout_seconds: float = 8.0) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False
        self.listeners.clear()

    def is_connected(self) -> bool:
        return self.connected

    def qualify_stock(self, symbol: str, *, currency: str = "USD") -> list[IbkrContractIdentity]:
        return list(self.contracts.get(symbol.upper(), ()))

    def subscribe_quote(
        self,
        contract: IbkrContractIdentity,
        listener: Callable[[IbkrQuoteSnapshot], None],
    ) -> int:
        token = self._next_token
        self._next_token += 1
        self.listeners[token] = (contract, listener)
        return token

    def unsubscribe_quote(self, token: int) -> None:
        self.listeners.pop(int(token), None)

    def emit(self, token: int, snapshot: IbkrQuoteSnapshot) -> None:
        _, listener = self.listeners[int(token)]
        listener(snapshot)

    def historical_bars(
        self,
        contract: IbkrContractIdentity,
        *,
        end: datetime,
        duration_seconds: int,
        bar_size: str,
        what_to_show: str,
        use_rth: bool,
        timeout_seconds: float = 20.0,
    ) -> list[IbkrHistoricalBar]:
        start = end.astimezone(timezone.utc).timestamp() - max(1, int(duration_seconds))
        return [
            row
            for row in self.history.get(contract.con_id, ())
            if start <= row.start_time.astimezone(timezone.utc).timestamp() < end.astimezone(timezone.utc).timestamp()
        ]

    def request_health(self, token: int) -> dict[str, object]:
        return dict(
            self.request_health_by_token.get(
                int(token),
                {
                    "request_id": int(token),
                    "market_data_type": "UNKNOWN",
                    "error": None,
                    "entitlement_denied": False,
                },
            )
        )

    def diagnostics(self) -> dict[str, object]:
        return {
            "transport": "fake",
            "connected": self.connected,
            "active_quote_subscriptions": len(self.listeners),
            "request_health": {
                str(key): dict(value)
                for key, value in self.request_health_by_token.items()
            },
        }


def _bool_env(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


class IbkrRuntime:
    """Connection, contract identity, subscription and diagnostics authority."""

    def __init__(
        self,
        *,
        transport: IbkrTransport | None = None,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.host = host or os.environ.get("OMNIX_IBKR_HOST", "127.0.0.1")
        self.port = int(port or os.environ.get("OMNIX_IBKR_PORT", "4002"))
        self.client_id = int(client_id or os.environ.get("OMNIX_IBKR_CLIENT_ID", "71"))
        self.enabled = _bool_env("OMNIX_IBKR_ENABLED", "0") if enabled is None else bool(enabled)
        self.transport = transport
        self._lock = threading.RLock()
        self._connect_lock = threading.Lock()
        self._historical_lock = threading.Lock()
        self._contract_cache: dict[str, IbkrContractIdentity] = {}
        self._quote_tokens: dict[str, int] = {}
        self._latest_quotes: dict[str, IbkrQuoteSnapshot] = {}
        self._quote_listeners: dict[str, list[Callable[[IbkrQuoteSnapshot], None]]] = {}
        self.connect_count = 0
        self.connect_failure_count = 0
        self.reconnect_count = 0
        self.contract_failure_count = 0
        self.historical_request_count = 0
        self._next_connect_attempt_monotonic = 0.0
        self._last_historical_request_monotonic = 0.0
        self.subscription_count = 0
        self.last_error: str | None = None
        self.last_connected_at: datetime | None = None

    @property
    def live_authority_enabled(self) -> bool:
        return _bool_env("OMNIX_IBKR_LIVE_AUTHORITY", "0")

    @property
    def recovery_authority_enabled(self) -> bool:
        return _bool_env("OMNIX_IBKR_RECOVERY_AUTHORITY", "0")

    def _ensure_transport(self) -> IbkrTransport:
        if self.transport is not None:
            return self.transport
        self.transport = OfficialIbapiTransport()
        return self.transport

    def connect(self) -> None:
        if not self.enabled:
            raise IbkrRuntimeError("ibkr_provider_disabled")
        with self._connect_lock:
            transport = self._ensure_transport()
            if transport.is_connected():
                return
            now_mono = time_module.monotonic()
            if now_mono < self._next_connect_attempt_monotonic:
                raise IbkrRuntimeError("ibkr_reconnect_backoff")
            prior = self.connect_count > 0
            try:
                transport.connect(self.host, self.port, self.client_id)
            except Exception as exc:
                self.connect_failure_count += 1
                backoff = max(
                    0.25,
                    float(os.environ.get("OMNIX_IBKR_RECONNECT_BACKOFF_SECONDS", "1")),
                )
                self._next_connect_attempt_monotonic = time_module.monotonic() + backoff
                self.last_error = f"{type(exc).__name__}: {exc}"
                raise
            self._next_connect_attempt_monotonic = 0.0
            self.connect_count += 1
            if prior:
                self.reconnect_count += 1
                # Request IDs from the prior socket are no longer valid. Preserve
                # listeners but force the next demand reconciliation to recreate
                # every upstream market-data line on the new connection.
                with self._lock:
                    self._quote_tokens.clear()
                    self.subscription_count = 0
            self.last_connected_at = datetime.now(timezone.utc)
            self.last_error = None

    def disconnect(self) -> None:
        if self.transport is not None:
            self.transport.disconnect()
        with self._lock:
            self._quote_tokens.clear()
            self._latest_quotes.clear()
            self.subscription_count = 0

    def is_connected(self) -> bool:
        return bool(self.transport is not None and self.transport.is_connected())

    @staticmethod
    def _venue_aliases(venue: str) -> set[str]:
        normalized = venue.upper()
        aliases = {
            "NASDAQ": {"NASDAQ", "ISLAND", "NASDAQOM"},
            "NYSE": {"NYSE"},
            "ARCA": {"ARCA"},
            "AMEX": {"AMEX", "NYSEMKT"},
        }
        return aliases.get(normalized, {normalized})

    def qualify_contract(
        self,
        instrument_id: str,
        *,
        symbol: str,
        venue: str,
        currency: str = "USD",
    ) -> IbkrContractIdentity:
        with self._lock:
            cached = self._contract_cache.get(instrument_id)
            if cached is not None:
                return cached
        self.connect()
        assert self.transport is not None
        rows = [
            row
            for row in self.transport.qualify_stock(symbol, currency=currency)
            if row.sec_type == "STK"
            and row.currency == currency.upper()
            and row.symbol == symbol.upper()
            and row.con_id > 0
        ]
        if not rows:
            self.contract_failure_count += 1
            raise IbkrContractUnavailableError(f"IBKR_CONTRACT_UNAVAILABLE:{symbol}")
        if len(rows) > 1:
            aliases = self._venue_aliases(venue)
            narrowed = [
                row
                for row in rows
                if row.primary_exchange in aliases or row.exchange in aliases
            ]
            if len(narrowed) == 1:
                rows = narrowed
            else:
                self.contract_failure_count += 1
                raise IbkrContractAmbiguousError(
                    f"IBKR_CONTRACT_AMBIGUOUS:{symbol}:{len(rows)}"
                )
        selected = rows[0]
        with self._lock:
            self._contract_cache[instrument_id] = selected
        return selected

    def subscribe_quote(
        self,
        instrument_id: str,
        *,
        contract: IbkrContractIdentity,
        listener: Callable[[IbkrQuoteSnapshot], None] | None = None,
    ) -> int:
        self.connect()
        assert self.transport is not None
        with self._lock:
            if listener is not None:
                listeners = self._quote_listeners.setdefault(instrument_id, [])
                if not any(item is listener for item in listeners):
                    listeners.append(listener)
            existing = self._quote_tokens.get(instrument_id)
            if existing is not None:
                return existing

        def on_quote(snapshot: IbkrQuoteSnapshot) -> None:
            with self._lock:
                self._latest_quotes[instrument_id] = snapshot
                listeners = tuple(self._quote_listeners.get(instrument_id, ()))
            for callback in listeners:
                try:
                    callback(snapshot)
                except Exception:
                    continue

        token = self.transport.subscribe_quote(contract, on_quote)
        with self._lock:
            self._quote_tokens[instrument_id] = token
            self.subscription_count = len(self._quote_tokens)
        return token

    def unsubscribe_quote(
        self,
        instrument_id: str,
        *,
        listener: Callable[[IbkrQuoteSnapshot], None] | None = None,
    ) -> None:
        with self._lock:
            if listener is not None:
                rows = self._quote_listeners.get(instrument_id, [])
                self._quote_listeners[instrument_id] = [item for item in rows if item is not listener]
                if self._quote_listeners[instrument_id]:
                    return
            token = self._quote_tokens.pop(instrument_id, None)
            self._quote_listeners.pop(instrument_id, None)
            self.subscription_count = len(self._quote_tokens)
        if token is not None and self.transport is not None:
            self.transport.unsubscribe_quote(token)

    def latest_quote(self, instrument_id: str) -> IbkrQuoteSnapshot | None:
        with self._lock:
            return self._latest_quotes.get(instrument_id)

    def subscription_health(self, instrument_id: str) -> dict[str, object]:
        with self._lock:
            token = self._quote_tokens.get(instrument_id)
        if token is None or self.transport is None:
            return {
                "request_id": None,
                "market_data_type": "UNKNOWN",
                "error": None,
                "entitlement_denied": False,
            }
        try:
            return self.transport.request_health(token)
        except Exception as exc:
            return {
                "request_id": token,
                "market_data_type": "UNKNOWN",
                "error": {"message": f"{type(exc).__name__}: {exc}"},
                "entitlement_denied": False,
            }

    def wait_for_quote(self, instrument_id: str, timeout_seconds: float = 3.0) -> IbkrQuoteSnapshot | None:
        deadline = time_module.monotonic() + max(0.0, timeout_seconds)
        while time_module.monotonic() <= deadline:
            snapshot = self.latest_quote(instrument_id)
            if snapshot is not None and snapshot.last is not None:
                return snapshot
            time_module.sleep(0.02)
        return self.latest_quote(instrument_id)

    def historical_bars(
        self,
        contract: IbkrContractIdentity,
        *,
        start: datetime,
        end: datetime,
        bar_size: str = "1 min",
        what_to_show: str = "TRADES",
        use_rth: bool = False,
    ) -> list[IbkrHistoricalBar]:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("ibkr historical range must be timezone-aware")
        if end <= start:
            raise ValueError("ibkr historical end must follow start")
        self.connect()
        assert self.transport is not None
        duration = int((end.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds())
        min_interval = (
            0.0
            if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test"
            else max(
                0.0,
                float(os.environ.get("OMNIX_IBKR_HISTORICAL_MIN_INTERVAL_SECONDS", "0.25")),
            )
        )
        with self._historical_lock:
            elapsed = time_module.monotonic() - self._last_historical_request_monotonic
            if elapsed < min_interval:
                time_module.sleep(min_interval - elapsed)
            rows = self.transport.historical_bars(
                contract,
                end=end.astimezone(timezone.utc),
                duration_seconds=max(60, duration),
                bar_size=bar_size,
                what_to_show=what_to_show,
                use_rth=use_rth,
            )
            self._last_historical_request_monotonic = time_module.monotonic()
            self.historical_request_count += 1
        start_utc = start.astimezone(timezone.utc)
        end_utc = end.astimezone(timezone.utc)
        return [row for row in rows if start_utc <= row.start_time < end_utc]

    def diagnostics(self) -> dict[str, object]:
        transport_diagnostics = self.transport.diagnostics() if self.transport is not None else {}
        return {
            "enabled": self.enabled,
            "host": self.host,
            "port": self.port,
            "client_id": self.client_id,
            "official_ibapi_available": official_ibapi_available(),
            "connected": self.is_connected(),
            "live_authority_enabled": self.live_authority_enabled,
            "recovery_authority_enabled": self.recovery_authority_enabled,
            "connect_count": self.connect_count,
            "connect_failure_count": self.connect_failure_count,
            "reconnect_count": self.reconnect_count,
            "qualified_contract_count": len(self._contract_cache),
            "active_quote_subscriptions": len(self._quote_tokens),
            "contract_failure_count": self.contract_failure_count,
            "historical_request_count": self.historical_request_count,
            "last_error": self.last_error,
            "last_connected_at": self.last_connected_at.isoformat() if self.last_connected_at else None,
            "transport": transport_diagnostics,
        }


_DEFAULT_RUNTIME: IbkrRuntime | None = None
_DEFAULT_LOCK = threading.Lock()


def default_ibkr_runtime() -> IbkrRuntime:
    global _DEFAULT_RUNTIME
    if _DEFAULT_RUNTIME is None:
        with _DEFAULT_LOCK:
            if _DEFAULT_RUNTIME is None:
                _DEFAULT_RUNTIME = IbkrRuntime()
    return _DEFAULT_RUNTIME


__all__ = [
    "FakeIbkrTransport",
    "IbkrClientUnavailableError",
    "IbkrContractAmbiguousError",
    "IbkrContractIdentity",
    "IbkrContractUnavailableError",
    "IbkrHistoricalBar",
    "IbkrQuoteSnapshot",
    "IbkrRuntime",
    "IbkrRuntimeError",
    "IbkrTransport",
    "OfficialIbapiTransport",
    "default_ibkr_runtime",
    "official_ibapi_available",
]
