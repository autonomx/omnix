from __future__ import annotations

import re
from decimal import Decimal
from threading import RLock

from .models import (
    AdjustmentMode,
    AssetClass,
    CanonicalInstrument,
    FeedType,
    InstrumentType,
    ProviderBinding,
    ProviderPolicy,
    UsageScope,
)


def _policy(
    *,
    scope: UsageScope,
    official: bool,
    realtime: str,
    assets: tuple[AssetClass, ...],
    intervals: tuple[str, ...],
    terms: str,
    delay: int = 0,
) -> ProviderPolicy:
    return ProviderPolicy(
        usage_scope=scope,
        redistribution_allowed=False,
        authentication_required=False,
        is_official_api=official,
        realtime_scope=realtime,
        delay_seconds=delay,
        terms_reference=terms,
        supported_asset_classes=assets,
        supported_intervals=intervals,
        history_depth="provider_defined",
        rate_limit_policy=(
            "Omnix bounded provider semaphore with retry-after-aware exponential backoff"
        ),
    )


BINANCE_POLICY = _policy(
    scope=UsageScope.PERSONAL_LOCAL,
    official=True,
    realtime="public spot market data",
    assets=(AssetClass.CRYPTO,),
    intervals=(
        "1m",
        "3m",
        "5m",
        "15m",
        "30m",
        "1h",
        "2h",
        "4h",
        "6h",
        "8h",
        "12h",
        "1d",
        "3d",
        "1w",
        "1mo",
    ),
    terms="https://www.binance.com/en/terms",
)
YAHOO_POLICY = _policy(
    scope=UsageScope.PERSONAL_LOCAL,
    official=False,
    realtime="unofficial regular-session polling; availability not guaranteed",
    assets=(AssetClass.EQUITY,),
    intervals=("1m", "5m", "15m", "1h", "1d", "1w", "1mo"),
    terms="https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html",
)
STOOQ_POLICY = _policy(
    scope=UsageScope.PERSONAL_LOCAL,
    official=False,
    realtime="historical daily only",
    assets=(AssetClass.EQUITY,),
    intervals=("1d",),
    terms="https://stooq.com/",
)
COINBASE_POLICY = _policy(
    scope=UsageScope.PERSONAL_LOCAL,
    official=True,
    realtime="public spot REST market data",
    assets=(AssetClass.CRYPTO,),
    intervals=("1m", "5m", "15m", "1h", "1d"),
    terms="https://docs.cdp.coinbase.com/exchange/docs/welcome",
)
KRAKEN_POLICY = _policy(
    scope=UsageScope.PERSONAL_LOCAL,
    official=True,
    realtime="public spot REST market data",
    assets=(AssetClass.CRYPTO,),
    intervals=("1m", "5m", "15m", "1h", "4h", "1d"),
    terms="https://docs.kraken.com/api/",
)
HYPERLIQUID_POLICY = _policy(
    scope=UsageScope.PERSONAL_LOCAL,
    official=True,
    realtime="public perpetual candle snapshots",
    assets=(AssetClass.CRYPTO,),
    intervals=("1m", "5m", "15m", "1h", "4h", "1d"),
    terms="https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api",
)

POLICIES = {
    "binance": BINANCE_POLICY,
    "yahoo": YAHOO_POLICY,
    "stooq": STOOQ_POLICY,
    "coinbase": COINBASE_POLICY,
    "kraken": KRAKEN_POLICY,
    "hyperliquid": HYPERLIQUID_POLICY,
}


def _crypto(
    venue: str,
    base: str,
    quote: str,
    instrument_type: InstrumentType = InstrumentType.SPOT,
) -> CanonicalInstrument:
    return CanonicalInstrument(
        instrument_id=f"crypto:{venue}:{instrument_type.value}:{base}-{quote}",
        asset_class=AssetClass.CRYPTO,
        instrument_type=instrument_type,
        venue=venue,
        venue_symbol=f"{base}-{quote}",
        display_symbol=f"{base}{quote}",
        base_currency=base,
        quote_currency=quote,
        exchange_timezone="UTC",
        session_calendar="24x7",
        price_scale=100,
        minimum_tick=Decimal("0.01"),
    )


def _equity(venue: str, symbol: str) -> CanonicalInstrument:
    return CanonicalInstrument(
        instrument_id=f"equity:{venue}:{symbol}",
        asset_class=AssetClass.EQUITY,
        instrument_type=InstrumentType.EQUITY,
        venue=venue,
        venue_symbol=symbol,
        display_symbol=symbol,
        base_currency=None,
        quote_currency="USD",
        exchange_timezone="America/New_York",
        session_calendar="XNYS",
        price_scale=100,
        minimum_tick=Decimal("0.01"),
    )


INSTRUMENTS = (
    *tuple(_crypto("BINANCE", base, "USDT") for base in ("BTC", "ETH", "SOL")),
    *tuple(_crypto("COINBASE", base, "USD") for base in ("BTC", "ETH")),
    *tuple(_crypto("KRAKEN", base, "USD") for base in ("BTC", "ETH")),
    *tuple(
        _crypto("HYPERLIQUID", base, "USD", InstrumentType.PERPETUAL)
        for base in ("BTC", "ETH")
    ),
    _equity("NASDAQ", "AAPL"),
    _equity("NASDAQ", "NVDA"),
    _equity("NASDAQ", "TSLA"),
    _equity("ARCA", "SPY"),
)


def _binding(
    instrument: CanonicalInstrument,
    provider: str,
    provider_symbol: str,
    feed_type: FeedType,
    *,
    adjustments: tuple[AdjustmentMode, ...] = (AdjustmentMode.RAW,),
) -> ProviderBinding:
    policy = POLICIES[provider]
    return ProviderBinding(
        binding_id=f"{provider}:{feed_type.value}:{instrument.instrument_id}",
        instrument_id=instrument.instrument_id,
        provider=provider,
        provider_symbol=provider_symbol,
        feed_type=feed_type,
        realtime_scope=policy.realtime_scope,
        delay_seconds=policy.delay_seconds,
        adjustment_capabilities=adjustments,
        supported_intervals=policy.supported_intervals,
        usage_scope=policy.usage_scope,
        is_official_api=policy.is_official_api,
    )


BINDINGS: tuple[ProviderBinding, ...] = tuple(
    binding
    for instrument in INSTRUMENTS
    for binding in (
        (
            _binding(
                instrument,
                "binance",
                instrument.display_symbol,
                FeedType.WEBSOCKET_AND_REST,
            ),
        )
        if instrument.venue == "BINANCE"
        else (
            _binding(
                instrument,
                "coinbase",
                instrument.venue_symbol,
                FeedType.REST,
            ),
        )
        if instrument.venue == "COINBASE"
        else (
            _binding(
                instrument,
                "kraken",
                instrument.venue_symbol.replace("BTC", "XBT"),
                FeedType.REST,
            ),
        )
        if instrument.venue == "KRAKEN"
        else (
            _binding(
                instrument,
                "hyperliquid",
                instrument.base_currency or "",
                FeedType.REST,
            ),
        )
        if instrument.venue == "HYPERLIQUID"
        else (
            _binding(
                instrument,
                "yahoo",
                instrument.display_symbol,
                FeedType.HISTORICAL_POLLING,
                adjustments=(AdjustmentMode.RAW,),
            ),
            _binding(
                instrument,
                "stooq",
                f"{instrument.display_symbol}.US",
                FeedType.HISTORICAL_DAILY,
            ),
        )
    )
)

_catalog_lock = RLock()
_dynamic_instruments: dict[str, CanonicalInstrument] = {}
_dynamic_bindings: dict[str, ProviderBinding] = {}
_CANONICAL_EQUITY_TOKEN = re.compile(r"^[A-Z0-9._^=-]+$")


def _restore_dynamic_equity(instrument_id: str) -> CanonicalInstrument | None:
    """Rehydrate a discovered equity saved in a workspace after a restart.

    Provider-discovered catalog entries are process-local, but workspace documents
    persist their canonical IDs.  Equity bindings are deterministic from that ID,
    so a saved symbol can be restored without requiring a search request first.
    """
    parts = instrument_id.split(":")
    if len(parts) != 3 or parts[0] != "equity":
        return None
    _, venue, symbol = parts
    if not venue or not symbol or any(
        not _CANONICAL_EQUITY_TOKEN.fullmatch(value)
        for value in (venue, symbol)
    ):
        return None

    instrument = CanonicalInstrument(
        instrument_id=instrument_id,
        asset_class=AssetClass.EQUITY,
        instrument_type=InstrumentType.EQUITY,
        venue=venue,
        venue_symbol=symbol,
        display_symbol=symbol,
        base_currency=None,
        quote_currency="USD",
        exchange_timezone="America/New_York",
        session_calendar="XNYS",
        price_scale=100,
        minimum_tick=Decimal("0.01"),
        status="active",
    )
    register_instrument(
        instrument,
        (
            _binding(
                instrument,
                "yahoo",
                symbol,
                FeedType.HISTORICAL_POLLING,
            ),
            _binding(
                instrument,
                "stooq",
                f"{symbol}.US",
                FeedType.HISTORICAL_DAILY,
            ),
        ),
    )
    return instrument


def register_instrument(
    instrument: CanonicalInstrument,
    bindings: tuple[ProviderBinding, ...] = (),
) -> CanonicalInstrument:
    """Register provider-discovered metadata for the lifetime of this process."""
    with _catalog_lock:
        if not any(item.instrument_id == instrument.instrument_id for item in INSTRUMENTS):
            _dynamic_instruments[instrument.instrument_id] = instrument
        for binding in bindings:
            if binding.instrument_id != instrument.instrument_id:
                raise ValueError("binding instrument_id must match the registered instrument")
            _dynamic_bindings[binding.binding_id] = binding
    return instrument


def all_instruments() -> list[CanonicalInstrument]:
    with _catalog_lock:
        return [*INSTRUMENTS, *_dynamic_instruments.values()]


def all_bindings() -> list[ProviderBinding]:
    with _catalog_lock:
        return [*BINDINGS, *_dynamic_bindings.values()]


def search_instruments(query: str = "") -> list[CanonicalInstrument]:
    clean = query.strip().upper()
    instruments = all_instruments()
    if not clean:
        return instruments
    return [
        item
        for item in instruments
        if clean in item.display_symbol
        or clean in item.venue_symbol
        or clean in item.instrument_id.upper()
    ]


def instrument_by_id(instrument_id: str) -> CanonicalInstrument | None:
    if instrument_id in _dynamic_instruments:
        return _dynamic_instruments[instrument_id]
    return next((item for item in INSTRUMENTS if item.instrument_id == instrument_id), None)


def binding_by_id(binding_id: str) -> ProviderBinding | None:
    if binding_id in _dynamic_bindings:
        return _dynamic_bindings[binding_id]
    binding = next((item for item in BINDINGS if item.binding_id == binding_id), None)
    if binding is not None:
        return binding

    # A persisted workspace may contain an explicit binding for a symbol that was
    # discovered in a previous process lifetime.  Recreate the dynamic catalog
    # entry before looking up that binding.
    parts = binding_id.split(":", 2)
    if len(parts) == 3 and parts[0] in {"yahoo", "stooq"}:
        _restore_dynamic_equity(parts[2])
    return _dynamic_bindings.get(binding_id)


def bindings_for_instrument(instrument_id: str) -> list[ProviderBinding]:
    bindings = [item for item in all_bindings() if item.instrument_id == instrument_id]
    if bindings:
        return bindings
    _restore_dynamic_equity(instrument_id)
    return [item for item in all_bindings() if item.instrument_id == instrument_id]


def default_binding(instrument_id: str) -> ProviderBinding | None:
    return next(iter(bindings_for_instrument(instrument_id)), None)
