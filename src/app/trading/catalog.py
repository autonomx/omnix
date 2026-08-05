from __future__ import annotations

from decimal import Decimal

from .models import (
    AssetClass,
    CanonicalInstrument,
    FeedType,
    InstrumentType,
    ProviderBinding,
    ProviderPolicy,
    UsageScope,
)


BINANCE_POLICY = ProviderPolicy(
    usage_scope=UsageScope.PERSONAL_LOCAL,
    redistribution_allowed=False,
    authentication_required=False,
    is_official_api=True,
    realtime_scope="public spot market data",
    terms_reference="Binance public market-data API terms",
    supported_asset_classes=(AssetClass.CRYPTO,),
    supported_intervals=("1m", "5m", "15m", "1h", "4h", "1d"),
    history_depth="provider_defined",
    rate_limit_policy="weighted request limits with bounded Omnix concurrency",
)


def _crypto(base: str) -> CanonicalInstrument:
    return CanonicalInstrument(
        instrument_id=f"crypto:BINANCE:spot:{base}-USDT",
        asset_class=AssetClass.CRYPTO,
        instrument_type=InstrumentType.SPOT,
        venue="BINANCE",
        venue_symbol=f"{base}-USDT",
        display_symbol=f"{base}USDT",
        base_currency=base,
        quote_currency="USDT",
        exchange_timezone="UTC",
        session_calendar="24x7",
        price_scale=100,
        minimum_tick=Decimal("0.01"),
    )


INSTRUMENTS = tuple(_crypto(base) for base in ("BTC", "ETH", "SOL"))
BINDINGS = tuple(
    ProviderBinding(
        binding_id=f"binance:rest-ws:{item.instrument_id}",
        instrument_id=item.instrument_id,
        provider="binance",
        provider_symbol=item.display_symbol,
        feed_type=FeedType.WEBSOCKET_AND_REST,
        realtime_scope="public spot klines",
        supported_intervals=BINANCE_POLICY.supported_intervals,
        usage_scope=BINANCE_POLICY.usage_scope,
        is_official_api=True,
    )
    for item in INSTRUMENTS
)


def search_instruments(query: str = "") -> list[CanonicalInstrument]:
    clean = query.strip().upper()
    if not clean:
        return list(INSTRUMENTS)
    return [
        item
        for item in INSTRUMENTS
        if clean in item.display_symbol or clean in item.venue_symbol or clean in item.instrument_id.upper()
    ]


def instrument_by_id(instrument_id: str) -> CanonicalInstrument | None:
    return next((item for item in INSTRUMENTS if item.instrument_id == instrument_id), None)


def binding_by_id(binding_id: str) -> ProviderBinding | None:
    return next((item for item in BINDINGS if item.binding_id == binding_id), None)
