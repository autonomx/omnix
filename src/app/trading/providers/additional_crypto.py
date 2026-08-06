from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import requests

from app.trading.cache import TradingMarketDataCache
from app.trading.catalog import POLICIES, bindings_for_instrument, instrument_by_id
from app.trading.models import BarsResponse, DatasetProvenance, MarketBar, ProviderBinding


INTERVALS = {
    "coinbase": {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400},
    "kraken": {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440},
    "hyperliquid": {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"},
}


class AdditionalCryptoProvider:
    def __init__(
        self,
        provider_id: str,
        *,
        session: requests.Session | None = None,
        cache: TradingMarketDataCache | None = None,
    ) -> None:
        if provider_id not in INTERVALS:
            raise ValueError(f"unsupported crypto provider: {provider_id}")
        self.provider_id = provider_id
        self.policy = POLICIES[provider_id]
        self.session = session or requests.Session()
        self.cache = cache or TradingMarketDataCache()

    def get_binding(self, instrument_id: str) -> ProviderBinding:
        binding = next((item for item in bindings_for_instrument(instrument_id) if item.provider == self.provider_id), None)
        if binding is None:
            raise ValueError(f"{self.provider_id} does not support instrument: {instrument_id}")
        return binding

    def _rows(self, binding: ProviderBinding, interval: str, limit: int) -> list[list[Any]]:
        provider_interval = INTERVALS[self.provider_id].get(interval)
        if provider_interval is None:
            raise ValueError(f"unsupported {self.provider_id} interval: {interval}")
        if self.provider_id == "coinbase":
            response = self.session.get(
                f"https://api.exchange.coinbase.com/products/{binding.provider_symbol}/candles",
                params={"granularity": provider_interval},
                timeout=20,
            )
            response.raise_for_status()
            return sorted(response.json(), key=lambda row: row[0])[-limit:]
        if self.provider_id == "kraken":
            response = self.session.get(
                "https://api.kraken.com/0/public/OHLC",
                params={"pair": binding.provider_symbol.replace("-", ""), "interval": provider_interval},
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                raise ValueError(str(payload["error"]))
            result = payload.get("result") or {}
            rows = result.get(next((key for key in result if key != "last"), ""), [])
            return rows[-limit:]
        response = self.session.post(
            "https://api.hyperliquid.xyz/info",
            json={"type": "candleSnapshot", "req": {"coin": binding.provider_symbol, "interval": provider_interval, "startTime": 0, "endTime": int(datetime.now(timezone.utc).timestamp() * 1000)}},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()[-limit:]

    def get_bars(self, instrument_id: str, interval: str, limit: int = 500) -> BarsResponse:
        instrument = instrument_by_id(instrument_id)
        binding = self.get_binding(instrument_id)
        if instrument is None:
            raise ValueError(f"unknown instrument: {instrument_id}")
        clean_limit = max(1, min(int(limit), 1_000))
        key = self.cache.key(binding.binding_id, instrument_id, interval, "raw", instrument.session_calendar, clean_limit)
        payload, entry, cached = self.cache.get_or_load(
            key,
            lambda: {"rows": self._rows(binding, interval, clean_limit)},
            ttl_seconds=30,
            source=f"{self.provider_id}_candles",
        )
        received = datetime.now(timezone.utc)
        bars: list[MarketBar] = []
        for row in payload["rows"]:
            if self.provider_id == "coinbase":
                timestamp, low, high, open_value, close, volume = row[:6]
            elif self.provider_id == "kraken":
                timestamp, open_value, high, low, close, _vwap, volume = row[:7]
            else:
                timestamp = int(row["t"]) / 1000
                open_value, high, low, close, volume = row["o"], row["h"], row["l"], row["c"], row["v"]
            start = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
            bars.append(MarketBar(
                instrument_id=instrument_id,
                interval=interval,
                start_time=start,
                end_time=start,
                open=Decimal(str(open_value)), high=Decimal(str(high)), low=Decimal(str(low)), close=Decimal(str(close)), volume=Decimal(str(volume)),
                provider=self.provider_id,
                provider_event_id=str(timestamp),
                received_at=received,
            ))
        return BarsResponse(
            instrument=instrument,
            binding=binding,
            provenance=DatasetProvenance(
                instrument_id=instrument_id,
                requested_binding=binding.binding_id,
                resolved_binding=binding.binding_id,
                dataset_fingerprint=entry.fingerprint,
                freshness_mode="cached" if cached else "polled",
                as_of=bars[-1].start_time if bars else received,
                received_at=received,
                cached=cached,
                history_complete=len(bars) < clean_limit,
            ),
            interval=interval,
            bars=bars,
        )

    def get_quote(self, instrument_id: str) -> dict[str, object]:
        response = self.get_bars(instrument_id, "1m", 1)
        if not response.bars:
            raise ValueError(f"{self.provider_id} returned no bars")
        last = response.bars[-1]
        return {"instrument_id": instrument_id, "binding_id": response.binding.binding_id, "provider": self.provider_id, "price": str(last.close), "received_at": response.provenance.received_at.isoformat(), "freshness_mode": response.provenance.freshness_mode}
