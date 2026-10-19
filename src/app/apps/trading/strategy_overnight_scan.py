"""Market data for ``overnight-trading-strategy-shadow`` (Alpaca SIP, read-only).

The free SIP feed withholds the most recent 15 minutes, so the 15:50 ET decision
reads regular-session 30-minute bars that ended by 15:30 and prior-session daily
bars. One-minute bars for labelling are fetched the next morning, long after the
entry and exit minutes. Nothing here places, sizes or routes an order.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.config.env import env_str

from .corporate_events import AlpacaCorporateActionsSource
from .historical_gapper_reconstruction import _alpaca_assets, _alpaca_bars
from .providers.alpaca_iex import ALPACA_DATA_URL, alpaca_iex_auth_headers
from .providers.errors import ProviderContractError
from .providers.http_runtime import ProviderHttpRuntime
from .strategies.models import OvernightShadowConfig
from .strategy_overnight_shadow import (
    OVERNIGHT_BENCHMARKS,
    OvernightBar,
    OvernightBenchmark,
    OvernightCandidate,
    OvernightHeadline,
    OvernightSocialMention,
    MID_MAX_ADV_DOLLARS,
    MID_MAX_PRICE,
    MID_MIN_ADV_DOLLARS,
    MID_POPULATION_MIN_CHANGE,
    build_benchmark,
    build_candidate,
    off_52w_high,
    population,
)
from app.apps.trading.us_equity_calendar import EASTERN as _ET

logger = logging.getLogger(__name__)

SCAN_BAR_MINUTES = 30
_CHUNK = 200
# Public Reddit mention counts (no key); research context only, never a decision input.
SOCIAL_SOURCE = "apewisdom:all-stocks"
_APEWISDOM_URL = "https://apewisdom.io/api/v1.0/filter/all-stocks/page/{page}"
_APEWISDOM_MAX_PAGES = 20
NEWS_SOURCE = "alpaca:benzinga"
_NEWS_CHUNK = 50
_NEWS_MAX_PAGES = 40
_ETF_EXCHANGES = {"ARCA", "BATS"}
_ETF_NAME = re.compile(
    r"\bETF\b|\bETN\b|exchange traded|index fund|proshares|direxion|ishares|leveraged|inverse| 2x| 3x", re.I
)
_DERIVATIVE_NAME = re.compile(r"warrant|\bwts?\b|\bunits?\b|\brights?\b|preferred|preference", re.I)


def is_common_stock(asset: dict[str, Any]) -> bool:
    """Exclude ETFs/ETNs, and warrants/units/rights/preferreds whose suffix the name confirms."""

    symbol = str(asset.get("symbol") or "").upper()
    name = str(asset.get("name") or "")
    exchange = str(asset.get("exchange") or "").upper()
    if exchange in _ETF_EXCHANGES or _ETF_NAME.search(name):
        return False
    suffix = (
        (exchange == "NASDAQ" and len(symbol) == 5 and symbol[-1] in "WUR")
        or re.search(r"[./ ](WS|U|R|RT|WT)$", symbol) is not None
        or re.search(r"[./ -]P(R)?[A-Z]?$", symbol) is not None
    )
    return not (suffix and _DERIVATIVE_NAME.search(name))


def _bar(raw: dict[str, Any]) -> OvernightBar | None:
    try:
        start = datetime.fromisoformat(str(raw["t"]).replace("Z", "+00:00"))
        return OvernightBar(
            start=start,
            open=Decimal(str(raw["o"])),
            high=Decimal(str(raw["h"])),
            low=Decimal(str(raw["l"])),
            close=Decimal(str(raw["c"])),
            volume=Decimal(str(raw.get("v") or 0)),
        )
    except (KeyError, ValueError, ArithmeticError):
        return None


def _bars(raw: Sequence[dict[str, Any]]) -> list[OvernightBar]:
    return [bar for item in raw if (bar := _bar(item)) is not None]


def _optional_int(value: Any) -> int | None:
    return None if value is None or value == "" else int(value)


def _mention(raw: dict[str, Any]) -> OvernightSocialMention | None:
    try:
        return OvernightSocialMention(
            symbol=str(raw["ticker"]).upper(),
            rank=int(raw["rank"]),
            mentions=int(raw["mentions"]),
            upvotes=int(raw.get("upvotes") or 0),
            rank_24h_ago=_optional_int(raw.get("rank_24h_ago")),
            mentions_24h_ago=_optional_int(raw.get("mentions_24h_ago")),
        )
    except (KeyError, TypeError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class OvernightScanResult:
    session_date: date
    eligible: int
    scanned: int
    candidates: tuple[OvernightCandidate, ...]
    mid_eligible: int = 0


class OvernightMarketData:
    """Alpaca SIP reads for the overnight monitor; the runtime bounds concurrency and retries."""

    def __init__(
        self, runtime: ProviderHttpRuntime | None = None, social_runtime: ProviderHttpRuntime | None = None,
    ) -> None:
        self.runtime = runtime or ProviderHttpRuntime("alpaca_overnight_shadow", max_concurrency=2)
        self.social_runtime = social_runtime or ProviderHttpRuntime("apewisdom_overnight_shadow", max_concurrency=1)

    def _headers(self) -> dict[str, str]:
        return alpaca_iex_auth_headers()

    def scan(self, session_date: date, prior_session: date, config: OvernightShadowConfig) -> OvernightScanResult:
        headers = self._headers()
        assets = {
            str(a["symbol"]).upper(): str(a["exchange"]).upper()
            for a in _alpaca_assets(self.runtime, headers)
            if is_common_stock(a)
        }
        # Prior-session daily bars only: prior close, ADV, and a price prefilter (a stock
        # above max_price / (1 + smallest arm change) cannot qualify today). They are split-adjusted
        # so a split taking effect today or in the trend window is not read as a move; at decision
        # time Alpaca can only know splits through today, so this stays point-in-time.
        min_change = min((arm.min_change for arm in config.arms if arm.enabled), default=Decimal("0"))
        max_prior = config.maximum_price / (1 + min_change)
        daily = _alpaca_bars(
            self.runtime, headers, sorted(assets), timeframe="1Day",
            start=datetime.combine(prior_session - timedelta(days=config.adv_sessions * 2 + 10), time(0), tzinfo=_ET),
            end=datetime.combine(prior_session + timedelta(days=1), time(0), tzinfo=_ET),
            chunk_size=_CHUNK, feed="sip", adjustment="split",
        )
        # The mid-cap research population (PREREG_OVERNIGHT5) adds stocks a $5-$50 price band and the
        # $5M-$50M dollar-ADV band can reach; the small-cap population and arms are unchanged by it.
        max_mid_prior = MID_MAX_PRICE / (1 + MID_POPULATION_MIN_CHANGE)
        history: dict[str, list[OvernightBar]] = {}
        adv_dollars: dict[str, Decimal] = {}
        small = mid = 0
        for symbol, raw in daily.items():
            rows = [b for b in _bars(raw) if b.start.astimezone(_ET).date() <= prior_session]
            if not rows or rows[-1].start.astimezone(_ET).date() != prior_session or rows[-1].close <= 0:
                continue
            recent = rows[-config.adv_sessions:]
            dollars = (sum((b.close * b.volume for b in recent), Decimal("0")) / len(recent)
                       if len(recent) >= config.min_adv_sessions else None)
            is_small = rows[-1].close <= max_prior
            is_mid = (rows[-1].close <= max_mid_prior and dollars is not None
                      and MID_MIN_ADV_DOLLARS <= dollars <= MID_MAX_ADV_DOLLARS)
            if is_small or is_mid:
                history[symbol] = rows
                small += is_small
                mid += is_mid
                if dollars is not None:
                    adv_dollars[symbol] = dollars
        intraday = _alpaca_bars(
            self.runtime, headers, sorted(history), timeframe=f"{SCAN_BAR_MINUTES}Min",
            start=datetime.combine(session_date, time(9, 30), tzinfo=_ET),
            end=datetime.combine(session_date, config.data_cutoff_et, tzinfo=_ET),
            chunk_size=_CHUNK, feed="sip",
        )
        candidates = []
        for symbol, raw in intraday.items():
            rows = history.get(symbol)
            if not rows:
                continue
            candidate = build_candidate(
                symbol=symbol,
                instrument_id=f"equity:{assets[symbol]}:{symbol}",
                prior_close=rows[-1].close,
                bars=_bars(raw),
                adv_volumes=[b.volume for b in rows[-config.adv_sessions:]],
                session_date=session_date,
                config=config,
                bar_minutes=SCAN_BAR_MINUTES,
                prior_closes=[b.close for b in rows[-21:]],
                adv_dollars=adv_dollars.get(symbol),
            )
            if candidate is not None:
                candidates.append(candidate)
        candidates = self._with_52w_high(candidates, headers, session_date, prior_session, config)
        return OvernightScanResult(
            session_date=session_date, eligible=small, scanned=len(intraday),
            candidates=tuple(sorted(candidates, key=lambda c: c.symbol)), mid_eligible=mid,
        )

    def _with_52w_high(
        self, candidates: list[OvernightCandidate], headers: dict[str, str],
        session_date: date, prior_session: date, config: OvernightShadowConfig,
    ) -> list[OvernightCandidate]:
        """Adds ``off_52w_high`` to population stocks only (a year of bars for every stock would be
        too slow for the decision window). Research context: a failure leaves the field empty."""

        wanted = {c.symbol for c in population(candidates, config)}
        if not wanted:
            return candidates
        try:
            daily = _alpaca_bars(
                self.runtime, headers, sorted(wanted), timeframe="1Day",
                start=datetime.combine(prior_session - timedelta(days=370), time(0), tzinfo=_ET),
                end=datetime.combine(prior_session + timedelta(days=1), time(0), tzinfo=_ET),
                chunk_size=_CHUNK, feed="sip", adjustment="split",
            )
        except Exception as exc:
            logger.warning("overnight shadow 52-week highs failed: %s: %s", type(exc).__name__, exc)
            return candidates
        return [
            c.model_copy(update={"off_52w_high": off_52w_high(c, _bars(daily.get(c.symbol, [])), session_date)})
            if c.symbol in wanted else c
            for c in candidates
        ]

    def benchmarks(
        self, session_date: date, prior_session: date, config: OvernightShadowConfig,
    ) -> tuple[OvernightBenchmark, ...]:
        """Broad-market ETFs at the data cutoff, from the same delayed SIP bars as the scan."""

        headers = self._headers()
        symbols = list(OVERNIGHT_BENCHMARKS)
        daily = _alpaca_bars(
            self.runtime, headers, symbols, timeframe="1Day",
            start=datetime.combine(prior_session - timedelta(days=10), time(0), tzinfo=_ET),
            end=datetime.combine(prior_session + timedelta(days=1), time(0), tzinfo=_ET),
            chunk_size=_CHUNK, feed="sip", adjustment="split",
        )
        intraday = _alpaca_bars(
            self.runtime, headers, symbols, timeframe=f"{SCAN_BAR_MINUTES}Min",
            start=datetime.combine(session_date, time(9, 30), tzinfo=_ET),
            end=datetime.combine(session_date, config.data_cutoff_et, tzinfo=_ET),
            chunk_size=_CHUNK, feed="sip",
        )
        built = (
            build_benchmark(
                symbol=symbol, daily=_bars(daily.get(symbol, [])), bars=_bars(intraday.get(symbol, [])),
                session_date=session_date, config=config, bar_minutes=SCAN_BAR_MINUTES,
            )
            for symbol in symbols
        )
        return tuple(b for b in built if b is not None)

    def news(self, symbols: Sequence[str], start: datetime, end: datetime) -> dict[str, list[OvernightHeadline]]:
        """Alpaca (Benzinga) headlines created in ``start..end``, per tagged symbol among ``symbols``."""

        wanted = sorted(set(symbols))
        found: dict[str, dict[str, OvernightHeadline]] = {}
        url = f"{(env_str('OMNIX_ALPACA_DATA_URL') or ALPACA_DATA_URL).rstrip('/')}/v1beta1/news"
        for index in range(0, len(wanted), _NEWS_CHUNK):
            chunk = wanted[index:index + _NEWS_CHUNK]
            token: str | None = None
            for _ in range(_NEWS_MAX_PAGES):
                params: dict[str, Any] = {
                    "symbols": ",".join(chunk), "limit": 50, "sort": "asc", "include_content": "false",
                    "start": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "end": end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                }
                if token:
                    params["page_token"] = token
                payload = self.runtime.get(url, params=params, headers=self._headers(), timeout=30).json()
                if not isinstance(payload, dict) or not isinstance(payload.get("news", []), list):
                    raise ProviderContractError("Alpaca news payload is malformed")
                for raw in payload.get("news") or []:
                    try:
                        headline = OvernightHeadline(
                            id=str(raw["id"]), headline=str(raw.get("headline") or ""),
                            created_at=datetime.fromisoformat(str(raw["created_at"]).replace("Z", "+00:00")),
                        )
                    except (KeyError, TypeError, ValueError):
                        continue
                    for symbol in raw.get("symbols") or []:
                        if str(symbol).upper() in chunk:
                            found.setdefault(str(symbol).upper(), {})[headline.id] = headline
                token = payload.get("next_page_token")
                if not token:
                    break
            else:
                raise ProviderContractError("Alpaca news paging did not finish")
        return {symbol: list(rows.values()) for symbol, rows in found.items()}

    def social_mentions(self) -> tuple[OvernightSocialMention, ...]:
        """Every ticker ApeWisdom currently ranks on stock subreddits (100 per page, one page at a time)."""

        mentions: list[OvernightSocialMention] = []
        page, pages = 1, 1
        while page <= min(pages, _APEWISDOM_MAX_PAGES):
            response = self.social_runtime.get(_APEWISDOM_URL.format(page=page), timeout=20)
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError as exc:
                raise ProviderContractError("ApeWisdom returned invalid JSON") from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                raise ProviderContractError("ApeWisdom payload is malformed")
            mentions += [m for raw in payload["results"] if isinstance(raw, dict) and (m := _mention(raw))]
            pages = int(payload.get("pages") or 1)
            page += 1
        return tuple(mentions)

    def splits(self, symbols: Sequence[str], start: date, end: date) -> list[tuple[str, date, Decimal, Decimal]]:
        """Forward and reverse splits with ex dates in ``start..end``: ``(symbol, ex_date, old_rate, new_rate)``."""

        source = AlpacaCorporateActionsSource(runtime=self.runtime)
        wanted = sorted(set(symbols))
        found: list[tuple[str, date, Decimal, Decimal]] = []
        for index in range(0, len(wanted), 100):
            for symbol, events in source.actions(wanted[index:index + 100], start, end).items():
                found += [
                    (symbol, e.date, Decimal(str(e.split_from)), Decimal(str(e.split_to)))
                    for e in events if e.kind == "split" and e.split_from and e.split_to
                ]
        return found

    def minute_bars(self, symbols: Sequence[str], start: datetime, end: datetime) -> dict[str, list[OvernightBar]]:
        """One-minute SIP bars; ``end`` is capped 16 minutes in the past (free SIP delay)."""

        capped = min(end, datetime.now(timezone.utc) - timedelta(minutes=16))
        if not symbols or capped <= start:
            return {}
        raw = _alpaca_bars(
            self.runtime, self._headers(), sorted(set(symbols)), timeframe="1Min",
            start=start, end=capped, chunk_size=_CHUNK, feed="sip",
        )
        return {symbol: _bars(rows) for symbol, rows in raw.items()}


__all__ = [
    "NEWS_SOURCE", "OvernightMarketData", "OvernightScanResult", "SCAN_BAR_MINUTES", "SOCIAL_SOURCE", "is_common_stock",
]
