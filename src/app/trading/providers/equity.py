from __future__ import annotations

import csv
import threading
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO
from typing import Any

import requests

from app.trading.cache import TradingMarketDataCache
from app.trading.catalog import POLICIES, bindings_for_instrument, instrument_by_id
from app.trading.models import AdjustmentMode, BarsResponse, DatasetProvenance, MarketBar, ProviderBinding

from .bar_semantics import equity_bar_times, equity_session_bounds, is_final_bar
from .errors import ProviderContractError, ProviderDataUnavailableError
from .http_runtime import ProviderHttpRuntime


YAHOO_INTERVALS = {
    "1m": ("1d", "1m"),
    "5m": ("5d", "5m"),
    "15m": ("5d", "15m"),
    "1h": ("3mo", "1h"),
    "1d": ("10y", "1d"),
    "1w": ("10y", "1wk"),
}


class YahooEquityProvider:
    provider_id = "yahoo"
    policy = POLICIES["yahoo"]

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        cache: TradingMarketDataCache | None = None,
        runtime: ProviderHttpRuntime | None = None,
    ) -> None:
        self.runtime = runtime or ProviderHttpRuntime(
            self.provider_id,
            session=session,
            max_concurrency=2,
        )
        self.session = self.runtime.session
        self.cache = cache or TradingMarketDataCache()

    def get_binding(self, instrument_id: str) -> ProviderBinding:
        binding = next(
            (
                item
                for item in bindings_for_instrument(instrument_id)
                if item.provider == self.provider_id
            ),
            None,
        )
        if binding is None:
            raise ValueError(f"Yahoo does not support instrument: {instrument_id}")
        return binding

    def get_bars(
        self,
        instrument_id: str,
        interval: str,
        limit: int = 500,
        cancellation: threading.Event | None = None,
    ) -> BarsResponse:
        instrument = instrument_by_id(instrument_id)
        binding = self.get_binding(instrument_id)
        if instrument is None or interval not in YAHOO_INTERVALS:
            raise ValueError(f"unsupported Yahoo request: {instrument_id} {interval}")
        range_value, provider_interval = YAHOO_INTERVALS[interval]
        clean_limit = max(1, min(int(limit), 2_000))
        key = self.cache.key(
            binding.binding_id,
            instrument_id,
            interval,
            AdjustmentMode.RAW.value,
            instrument.session_calendar,
            clean_limit,
        )

        def load() -> dict[str, Any]:
            response = self.runtime.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{binding.provider_symbol}",
                params={
                    "range": range_value,
                    "interval": provider_interval,
                    "includePrePost": "false",
                    "events": "div,splits",
                },
                headers={"User-Agent": "Mozilla/5.0 Omnix local research"},
                timeout=20,
                cancellation=cancellation,
            )
            try:
                payload = response.json()
            except ValueError as exc:
                raise ProviderContractError("Yahoo returned invalid JSON") from exc
            result = ((payload.get("chart") or {}).get("result") or [None])[0]
            if not isinstance(result, dict):
                raise ProviderDataUnavailableError("Yahoo returned no chart result")
            quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
            if not isinstance(quote, dict):
                raise ProviderContractError("Yahoo quote payload is malformed")
            rows = []
            for index, timestamp in enumerate(result.get("timestamp") or []):
                values = [quote.get(name, []) for name in ("open", "high", "low", "close", "volume")]
                if any(not isinstance(items, list) or index >= len(items) for items in values):
                    continue
                open_value, high, low, close, volume = (items[index] for items in values)
                if None in (open_value, high, low, close):
                    continue
                rows.append([int(timestamp), open_value, high, low, close, volume or 0])
            if not rows:
                raise ProviderDataUnavailableError(
                    f"Yahoo returned no bars for {instrument_id} {interval}"
                )
            return {"rows": rows[-clean_limit:], "history_complete": len(rows) < clean_limit}

        payload, entry, cached = self.cache.get_or_load(
            key,
            load,
            ttl_seconds=60 if interval not in {"1d", "1w"} else 900,
            source="yahoo_chart",
        )
        received = datetime.now(timezone.utc)
        bars: list[MarketBar] = []
        for row in payload["rows"]:
            provider_time = datetime.fromtimestamp(int(row[0]), tz=timezone.utc)
            start, end, session = equity_bar_times(
                provider_time,
                interval,
                instrument.exchange_timezone,
            )
            bars.append(
                MarketBar(
                    instrument_id=instrument_id,
                    interval=interval,
                    start_time=start,
                    end_time=end,
                    open=Decimal(str(row[1])),
                    high=Decimal(str(row[2])),
                    low=Decimal(str(row[3])),
                    close=Decimal(str(row[4])),
                    volume=Decimal(str(row[5])),
                    is_final=is_final_bar(end, received),
                    adjustment_mode=AdjustmentMode.RAW,
                    session=session,
                    provider=self.provider_id,
                    provider_event_id=str(row[0]),
                    received_at=received,
                )
            )
        return BarsResponse(
            instrument=instrument,
            binding=binding,
            provenance=DatasetProvenance(
                instrument_id=instrument_id,
                requested_binding=binding.binding_id,
                resolved_binding=binding.binding_id,
                dataset_fingerprint=entry.fingerprint,
                freshness_mode="cached" if cached else "polled",
                as_of=bars[-1].end_time if bars else received,
                received_at=received,
                cached=cached,
                history_complete=bool(payload.get("history_complete")),
            ),
            interval=interval,
            bars=bars,
        )

    def get_quote(
        self,
        instrument_id: str,
        cancellation: threading.Event | None = None,
    ) -> dict[str, object]:
        response = self.get_bars(instrument_id, "1d", 2, cancellation)
        if not response.bars:
            raise ProviderDataUnavailableError("Yahoo returned no quote bars")
        last = response.bars[-1]
        return {
            "instrument_id": instrument_id,
            "binding_id": response.binding.binding_id,
            "provider": self.provider_id,
            "price": str(last.close),
            "received_at": response.provenance.received_at.isoformat(),
            "source_time": last.end_time.isoformat(),
            "freshness_mode": response.provenance.freshness_mode,
        }


class StooqEquityProvider:
    provider_id = "stooq"
    policy = POLICIES["stooq"]

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        cache: TradingMarketDataCache | None = None,
        runtime: ProviderHttpRuntime | None = None,
    ) -> None:
        self.runtime = runtime or ProviderHttpRuntime(
            self.provider_id,
            session=session,
            max_concurrency=2,
        )
        self.session = self.runtime.session
        self.cache = cache or TradingMarketDataCache()

    def get_binding(self, instrument_id: str) -> ProviderBinding:
        binding = next(
            (
                item
                for item in bindings_for_instrument(instrument_id)
                if item.provider == self.provider_id
            ),
            None,
        )
        if binding is None:
            raise ValueError(f"Stooq does not support instrument: {instrument_id}")
        return binding

    def get_bars(
        self,
        instrument_id: str,
        interval: str,
        limit: int = 500,
        cancellation: threading.Event | None = None,
    ) -> BarsResponse:
        if interval != "1d":
            raise ValueError("Stooq supports daily bars only")
        instrument = instrument_by_id(instrument_id)
        binding = self.get_binding(instrument_id)
        if instrument is None:
            raise ValueError(f"unknown instrument: {instrument_id}")
        clean_limit = max(1, min(int(limit), 5_000))
        key = self.cache.key(
            binding.binding_id,
            instrument_id,
            interval,
            AdjustmentMode.RAW.value,
            instrument.session_calendar,
            clean_limit,
        )

        def load() -> dict[str, Any]:
            response = self.runtime.get(
                "https://stooq.com/q/d/l/",
                params={"s": binding.provider_symbol.lower(), "i": "d"},
                timeout=20,
                cancellation=cancellation,
            )
            rows = list(csv.DictReader(StringIO(response.text)))
            required = {"Date", "Open", "High", "Low", "Close"}
            rows = [row for row in rows if required.issubset(row) and row.get("Date")]
            if not rows:
                raise ProviderDataUnavailableError(
                    f"Stooq returned no bars for {instrument_id}"
                )
            return {"rows": rows[-clean_limit:], "history_complete": len(rows) < clean_limit}

        payload, entry, cached = self.cache.get_or_load(
            key,
            load,
            ttl_seconds=3_600,
            source="stooq_daily_csv",
        )
        received = datetime.now(timezone.utc)
        bars: list[MarketBar] = []
        for row in payload["rows"]:
            session_date = datetime.strptime(row["Date"], "%Y-%m-%d").date()
            start, end = equity_session_bounds(
                session_date,
                instrument.exchange_timezone,
            )
            bars.append(
                MarketBar(
                    instrument_id=instrument_id,
                    interval="1d",
                    start_time=start,
                    end_time=end,
                    open=Decimal(row["Open"]),
                    high=Decimal(row["High"]),
                    low=Decimal(row["Low"]),
                    close=Decimal(row["Close"]),
                    volume=Decimal(row.get("Volume") or "0"),
                    is_final=is_final_bar(end, received),
                    adjustment_mode=AdjustmentMode.RAW,
                    session="regular",
                    provider=self.provider_id,
                    provider_event_id=row["Date"],
                    received_at=received,
                )
            )
        return BarsResponse(
            instrument=instrument,
            binding=binding,
            provenance=DatasetProvenance(
                instrument_id=instrument_id,
                requested_binding=binding.binding_id,
                resolved_binding=binding.binding_id,
                dataset_fingerprint=entry.fingerprint,
                freshness_mode="cached" if cached else "polled",
                as_of=bars[-1].end_time if bars else received,
                received_at=received,
                cached=cached,
                history_complete=bool(payload.get("history_complete")),
            ),
            interval="1d",
            bars=bars,
        )

    def get_quote(
        self,
        instrument_id: str,
        cancellation: threading.Event | None = None,
    ) -> dict[str, object]:
        response = self.get_bars(instrument_id, "1d", 1, cancellation)
        if not response.bars:
            raise ProviderDataUnavailableError("Stooq returned no quote bars")
        last = response.bars[-1]
        return {
            "instrument_id": instrument_id,
            "binding_id": response.binding.binding_id,
            "provider": self.provider_id,
            "price": str(last.close),
            "received_at": response.provenance.received_at.isoformat(),
            "source_time": last.end_time.isoformat(),
            "freshness_mode": response.provenance.freshness_mode,
        }
