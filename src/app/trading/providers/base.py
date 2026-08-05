from __future__ import annotations

from typing import Protocol

from app.trading.models import BarsResponse, CanonicalInstrument, ProviderBinding, ProviderPolicy


class MarketDataProvider(Protocol):
    provider_id: str
    policy: ProviderPolicy

    def search_instruments(self, query: str) -> list[CanonicalInstrument]: ...

    def get_binding(self, instrument_id: str) -> ProviderBinding: ...

    def get_bars(self, instrument_id: str, interval: str, limit: int = 500) -> BarsResponse: ...

    def get_quote(self, instrument_id: str) -> dict[str, object]: ...
