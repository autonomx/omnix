"""Current-only Finviz Top Gainers discovery for the Omnix gapper workflow.

Finviz is used only to decide *which symbols belong to the morning cohort*.
Candidate prices/volume and instrument metadata are independently enriched from
Yahoo chart/search data so Finviz never becomes execution authority.

The adapter is intentionally current-only. Historical Finviz screener pages are
not reconstructed later because doing so would introduce survivorship/look-ahead
bias. Freeze the returned universe at capture time and reuse that immutable
snapshot for research/backtests.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from html import unescape
from typing import Any
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from .catalog import register_instrument
from .gapper_dataset import GapperCandidate, GapperUniverseSnapshot, freeze_gapper_universe, time_of_day_relative_volume
from .instrument_catalog_service import _dynamic_bindings, _equity_instrument
from .providers.alpaca_iex import AlpacaIexExecutionProvider, alpaca_iex_configured
from .providers.errors import ProviderContractError, ProviderDataUnavailableError
from .providers.http_runtime import ProviderHttpRuntime
from .strategy_data_integrity import (
    FINVIZ_ATOMIC_FIRST_PAGE_MAX,
    finviz_atomic_source_locator,
)


FINVIZ_TOP_GAINERS_URL = "https://finviz.com/screener"
FINVIZ_TOP_GAINERS_SOURCE_URL = "https://finviz.com/screener?v=340&s=ta_topgainers"
FINVIZ_ATOMIC_SOURCE_LOCATOR = finviz_atomic_source_locator(FINVIZ_TOP_GAINERS_SOURCE_URL)
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"

_ET = ZoneInfo("America/New_York")
_PREMARKET_OPEN = time(4, 0)
_REGULAR_OPEN = time(9, 30)
_REGULAR_CLOSE = time(16, 0)
_ALLOWED_DISCOVERY_SKEW_SECONDS = 120
_TICKER_PATHS = {"/quote", "/quote.ashx", "/stock"}
_HREF_RE = re.compile(r"href\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)


def _raw(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("raw")
    return value


def _decimal(value: Any) -> Decimal | None:
    value = _raw(value)
    if value in {None, ""}:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _spread_bps(bid: Decimal | None, ask: Decimal | None) -> Decimal | None:
    if bid is None or ask is None or bid <= 0 or ask <= 0 or bid > ask:
        return None
    midpoint = (bid + ask) / Decimal("2")
    if midpoint <= 0:
        return None
    return (ask - bid) / midpoint * Decimal("10000")


def parse_finviz_top_gainer_symbols(html: str) -> list[str]:
    """Extract the ordered, de-duplicated ticker cohort from a Finviz screener page.

    Finviz changed its screener links from ``quote.ashx?t=...`` to links such as
    ``/stock?b=1&p=d&t=...``.  Parse the href query instead of assuming that the
    ticker is the first query parameter so both page layouts remain supported.
    """

    symbols: list[str] = []
    seen: set[str] = set()
    for match in _HREF_RE.finditer(html or ""):
        href = unescape(match.group(2).strip())
        parsed = urlsplit(href)
        path = f"/{parsed.path.lstrip('/')}".lower()
        if path not in _TICKER_PATHS:
            continue
        values = parse_qs(parsed.query).get("t", [])
        if not values:
            continue
        symbol = values[0].strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
    return symbols


def _finviz_symbols(
    runtime: ProviderHttpRuntime,
    *,
    count: int,
) -> tuple[list[str], datetime]:
    """Capture one immutable first-page Finviz cohort with a single request.

    The old pagination loop could splice together different live screener
    populations. Prospective Finviz evidence is now deliberately bounded to the
    first page so source membership is atomic and auditable.
    """

    response = runtime.get(
        FINVIZ_TOP_GAINERS_URL,
        params={"v": 340, "s": "ta_topgainers", "r": 1},
        headers={
            "User-Agent": "Mozilla/5.0 Omnix local research",
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout=20,
    )
    received_at = datetime.now(timezone.utc)
    page = parse_finviz_top_gainer_symbols(getattr(response, "text", ""))
    if not page:
        raise ProviderDataUnavailableError("Finviz Top Gainers returned no ticker rows")
    effective_count = min(count, FINVIZ_ATOMIC_FIRST_PAGE_MAX)
    return page[:effective_count], received_at


def _yahoo_exact_quote(runtime: ProviderHttpRuntime, symbol: str) -> dict[str, Any] | None:
    try:
        response = runtime.get(
            YAHOO_SEARCH_URL,
            params={"q": symbol, "quotesCount": 10, "newsCount": 0},
            headers={"User-Agent": "Mozilla/5.0 Omnix local research"},
            timeout=10,
        )
        payload = response.json()
    except Exception:
        return None
    quotes = payload.get("quotes") if isinstance(payload, dict) else None
    if not isinstance(quotes, list):
        return None
    for raw in quotes:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("symbol") or "").strip().upper() != symbol:
            continue
        if str(raw.get("quoteType") or "").strip().upper() not in {"EQUITY", "ETF"}:
            continue
        return raw
    return None


def _yahoo_chart_snapshot(
    runtime: ProviderHttpRuntime,
    symbol: str,
    evaluation_time: datetime,
) -> tuple[Decimal, Decimal, Decimal, Decimal | None, dict[str, Any], int, tuple[str, ...]]:
    response = runtime.get(
        YAHOO_CHART_URL.format(symbol=symbol),
        params={
            "range": "5d",
            "interval": "1m",
            "includePrePost": "true",
            "events": "",
        },
        headers={"User-Agent": "Mozilla/5.0 Omnix local research"},
        timeout=20,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderContractError("Yahoo returned invalid Finviz-enrichment chart JSON") from exc

    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not isinstance(result, dict):
        raise ProviderDataUnavailableError(f"Yahoo returned no chart for Finviz symbol {symbol}")
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    if not isinstance(quote, dict):
        raise ProviderContractError("Yahoo Finviz-enrichment chart quote payload is malformed")

    timestamps = result.get("timestamp") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    if not isinstance(timestamps, list) or not isinstance(closes, list) or not isinstance(volumes, list):
        raise ProviderContractError("Yahoo Finviz-enrichment chart arrays are malformed")

    evaluation_et = evaluation_time.astimezone(_ET)
    current_date = evaluation_et.date()
    same_clock = evaluation_et.timetz().replace(tzinfo=None)
    cumulative_by_date: dict[object, Decimal] = defaultdict(lambda: Decimal("0"))
    regular_closes_by_date: dict[object, list[tuple[datetime, Decimal]]] = defaultdict(list)
    latest_current: tuple[datetime, Decimal] | None = None
    premarket_volume = Decimal("0")
    premarket_bar_count = 0
    premarket_volume_missing = False

    for index, raw_timestamp in enumerate(timestamps):
        if index >= len(closes):
            break
        close = _decimal(closes[index])
        raw_volume = volumes[index] if index < len(volumes) else None
        volume = _decimal(raw_volume)
        if close is None or close <= 0:
            continue
        observed = datetime.fromtimestamp(int(raw_timestamp), tz=timezone.utc).astimezone(_ET)
        clock = observed.timetz().replace(tzinfo=None)
        # A Yahoo 1m timestamp is the bar start. Never let an in-progress bar
        # leak into the frozen premarket evidence.
        if observed + timedelta(minutes=1) > evaluation_et:
            continue
        if _PREMARKET_OPEN <= clock <= same_clock:
            cumulative_by_date[observed.date()] += volume or Decimal("0")
        if observed.date() == current_date and _PREMARKET_OPEN <= clock <= same_clock:
            latest_current = (observed, close)
            if clock < _REGULAR_OPEN:
                premarket_bar_count += 1
                if volume is None:
                    premarket_volume_missing = True
                else:
                    premarket_volume += volume
        if observed.date() < current_date and _REGULAR_OPEN <= clock < _REGULAR_CLOSE:
            regular_closes_by_date[observed.date()].append((observed, close))

    if latest_current is None:
        meta_price = _decimal((result.get("meta") or {}).get("regularMarketPrice"))
        if meta_price is None or meta_price <= 0:
            raise ProviderDataUnavailableError(f"Yahoo returned no current price for Finviz symbol {symbol}")
        current_price = meta_price
    else:
        current_price = latest_current[1]

    prior_dates = sorted(regular_closes_by_date)
    previous_close: Decimal | None = None
    if prior_dates:
        previous_close = sorted(regular_closes_by_date[prior_dates[-1]], key=lambda item: item[0])[-1][1]
    if previous_close is None:
        meta = result.get("meta") or {}
        previous_close = _decimal(meta.get("chartPreviousClose")) or _decimal(meta.get("previousClose"))
    if previous_close is None or previous_close <= 0:
        raise ProviderDataUnavailableError(f"Yahoo returned no previous close for Finviz symbol {symbol}")

    current_cumulative = cumulative_by_date.get(current_date, Decimal("0"))
    historical = [
        value
        for session_date, value in sorted(cumulative_by_date.items(), key=lambda item: item[0])
        if session_date < current_date and value > 0
    ]
    tod_rvol = time_of_day_relative_volume(current_cumulative, historical)
    issues: list[str] = []
    if premarket_bar_count == 0:
        issues.append("PREMARKET_BARS_MISSING")
    if premarket_volume_missing:
        issues.append("PREMARKET_VOLUME_MISSING")
    if tod_rvol is None:
        issues.append("TOD_RVOL_MISSING")
    return (
        current_price,
        previous_close,
        premarket_volume,
        tod_rvol,
        result.get("meta") or {},
        premarket_bar_count,
        tuple(issues),
    )


def discover_finviz_gappers(
    *,
    universe_id: str,
    evaluation_time: datetime,
    count: int = 50,
    minimum_gap_pct: Decimal = Decimal("20"),
    minimum_price: Decimal = Decimal("0.50"),
    maximum_price: Decimal = Decimal("20"),
    finviz_runtime: ProviderHttpRuntime | None = None,
    yahoo_runtime: ProviderHttpRuntime | None = None,
    execution_provider: Any | None = None,
) -> GapperUniverseSnapshot:
    """Discover Finviz Top Gainers and freeze Yahoo-enriched point-in-time evidence."""

    if evaluation_time.tzinfo is None:
        raise ValueError("evaluation_time must be timezone-aware")
    if count < 1 or count > 100:
        raise ValueError("Finviz gapper discovery count must be between 1 and 100")
    evaluation = evaluation_time.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if abs((now - evaluation).total_seconds()) > _ALLOWED_DISCOVERY_SKEW_SECONDS:
        raise ValueError("Finviz gapper discovery is current-only; freeze historical universes at capture time")

    finviz = finviz_runtime or ProviderHttpRuntime("finviz_gapper_discovery", max_concurrency=1)
    yahoo = yahoo_runtime or ProviderHttpRuntime("finviz_yahoo_enrichment", max_concurrency=2)
    alpaca = execution_provider
    if alpaca is None and alpaca_iex_configured():
        alpaca = AlpacaIexExecutionProvider()
    symbols, received_at = _finviz_symbols(finviz, count=count)

    candidates: list[GapperCandidate] = []
    for raw_rank, symbol in enumerate(symbols, start=1):
        try:
            (
                price,
                previous_close,
                premarket_volume,
                tod_rvol,
                chart_meta,
                premarket_bar_count,
                chart_issues,
            ) = _yahoo_chart_snapshot(yahoo, symbol, evaluation)
        except Exception:
            # Preserve discovery integrity by skipping symbols whose canonical
            # price/share basis cannot be proven at capture time. The source
            # cohort itself remains observable in provider logs.
            continue

        gap_pct = (price / previous_close - Decimal("1")) * Decimal("100")
        if gap_pct < minimum_gap_pct or not minimum_price <= price <= maximum_price:
            continue

        search_quote = _yahoo_exact_quote(yahoo, symbol)
        enrichment_at = datetime.now(timezone.utc)
        quote_for_instrument = search_quote or {
            "symbol": symbol,
            "quoteType": "EQUITY",
            "exchange": chart_meta.get("exchangeName") or chart_meta.get("exchange") or "YAHOO",
        }
        instrument = _equity_instrument(quote_for_instrument)
        if instrument is None or instrument.session_calendar not in {"XNAS", "XNYS"}:
            continue
        register_instrument(instrument, _dynamic_bindings(instrument))

        bid = _decimal(search_quote.get("bid")) if search_quote else None
        ask = _decimal(search_quote.get("ask")) if search_quote else None
        market_cap = _decimal(search_quote.get("marketCap")) if search_quote else None
        float_shares = _decimal(search_quote.get("floatShares")) if search_quote else None
        spread_bps = _spread_bps(bid, ask)
        data_quality_flags = list(chart_issues)
        evidence_times = {
            "finviz_top_gainers": received_at,
            "yahoo_chart_enrichment": enrichment_at,
        }

        # Yahoo search does not reliably expose a premarket bid/ask for every
        # small-cap name. When Alpaca IEX is configured, capture its point-in-time
        # spread as additional *research evidence*. The observation's eligibility
        # is deliberately ignored here: discovery cannot grant execution authority.
        # AUTO PAPER later fetches a fresh Alpaca IEX observation and fails closed.
        if alpaca is not None:
            try:
                execution = alpaca.execution_observation(instrument.instrument_id)
            except Exception:
                pass
            else:
                if execution.spread_bps is not None:
                    spread_bps = execution.spread_bps
                alpaca_at = datetime.now(timezone.utc)
                evidence_times["alpaca_iex_research_quote"] = alpaca_at
                enrichment_at = max(enrichment_at, alpaca_at)

        if spread_bps is None:
            data_quality_flags.append("SPREAD_MISSING")
        data_quality_flags = list(dict.fromkeys(data_quality_flags))

        candidates.append(
            GapperCandidate(
                instrument_id=instrument.instrument_id,
                binding_id=f"yahoo:historical_polling:{instrument.instrument_id}",
                observed_at=enrichment_at,
                evidence_observed_at=evidence_times,
                previous_close=previous_close,
                premarket_price=price,
                gap_pct=gap_pct,
                premarket_volume=premarket_volume,
                premarket_dollar_volume=premarket_volume * price,
                premarket_bar_count=premarket_bar_count,
                tod_rvol=tod_rvol,
                market_data_complete=not data_quality_flags,
                data_quality_flags=tuple(data_quality_flags),
                market_cap=market_cap if market_cap is not None and market_cap >= 0 else None,
                float_shares=float_shares if float_shares is not None and float_shares > 0 else None,
                spread_bps=spread_bps,
                discovery_rank=raw_rank,
            )
        )

    freeze_time = datetime.now(timezone.utc)
    freeze_et = freeze_time.astimezone(_ET)
    return freeze_gapper_universe(
        universe_id=universe_id,
        session_date=freeze_et.date(),
        evaluation_time=freeze_time,
        discovery_source="finviz",
        source_locator=FINVIZ_ATOMIC_SOURCE_LOCATOR,
        source_candidate_symbols=symbols,
        candidates=candidates,
        allow_empty=not candidates,
    )


__all__ = [
    "FINVIZ_ATOMIC_SOURCE_LOCATOR",
    "FINVIZ_TOP_GAINERS_SOURCE_URL",
    "discover_finviz_gappers",
    "parse_finviz_top_gainer_symbols",
]
