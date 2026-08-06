from __future__ import annotations

from decimal import Decimal

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
    ),
    terms="https://www.binance.com/en/terms",
)
YAHOO_POLICY = _policy(
    scope=UsageScope.PERSONAL_LOCAL,
    official=False,
    realtime="unofficial regular-session polling; availability not guaranteed",
    assets=(AssetClass.EQUITY,),
    intervals=("1m", "5m", "15m", "1h", "1d", "1w"),
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


def search_instruments(query: str = "") -> list[CanonicalInstrument]:
    clean = query.strip().upper()
    if not clean:
        return list(INSTRUMENTS)
    return [
        item
        for item in INSTRUMENTS
        if clean in item.display_symbol
        or clean in item.venue_symbol
        or clean in item.instrument_id.upper()
    ]


def instrument_by_id(instrument_id: str) -> CanonicalInstrument | None:
    return next((item for item in INSTRUMENTS if item.instrument_id == instrument_id), None)


def binding_by_id(binding_id: str) -> ProviderBinding | None:
    return next((item for item in BINDINGS if item.binding_id == binding_id), None)


def bindings_for_instrument(instrument_id: str) -> list[ProviderBinding]:
    return [item for item in BINDINGS if item.instrument_id == instrument_id]


def default_binding(instrument_id: str) -> ProviderBinding | None:
    return next(iter(bindings_for_instrument(instrument_id)), None)
