from __future__ import annotations

"""Replay the interday SHADOW AI arms over a past session, on the real monitor code.

Research only. This imports no broker execution client, creates no paper or live order and never opens the Omnix
database: ``main`` removes ``OMNIX_DATABASE_URL`` first and every repository here is in memory.

The AI arms (C/D every-minute and event-driven, V2's four arms, V3) are the production monitors, unchanged, driven
by a simulated clock. What the replay supplies instead of the live services:

* The 09:15 cohort is rebuilt from Alpaca SIP: the top premarket gainers as of 09:15 ET, known at 09:15. It is a
  reconstruction of the discovery step, not the list the live Finviz screener showed.
* Minute bars are SIP bars, cut at the simulated clock, so no arm can see a later bar. A minute with no trades is a
  flat zero-volume bar, as a consolidated tape has nothing for it.
* Quotes are historical SIP NBBO: the last one known for decisions, the first one after the decision for fills.
* News is Alpaca's archive, cut at each headline's publication time. Live web research is switched off, because it
  would read today's internet.

The model call happens in real time and its latency moves the simulated clock for that decision. Monitors run one
after another, so a replay does not reproduce the queueing of a live five-minute mark.
"""

import argparse
import asyncio
import csv
import hashlib
import json
import logging
import os
import sys
import time as time_module
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import requests

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
for import_root in (SOURCE_ROOT, REPOSITORY_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from app.apps.trading.execution import ExecutionObservation  # noqa: E402
from app.apps.trading.execution_observation_plane import (  # noqa: E402
    CausalExecutionSelection,
    ExecutionObservationEnvelope,
)
from app.apps.trading.gapper_dataset import GapperCandidate, freeze_gapper_universe  # noqa: E402
from app.apps.trading.market_data_recovery import RecoveredBars, RecoveryReport  # noqa: E402
from app.apps.trading.models import MarketBar  # noqa: E402
from app.apps.trading.providers.alpaca_iex import ALPACA_DATA_URL, alpaca_iex_auth_headers  # noqa: E402
from app.apps.trading.research.contracts import TradingEvidence  # noqa: E402

ET = ZoneInfo("America/New_York")
UTC = timezone.utc
PROVIDER = "alpaca_sip_replay"
DEFAULT_CACHE_ROOT = Path("resources/cache/interday-ai-replay")
ASSETS_FILE = Path("resources/cache/overnight-pit/assets.json")
LISTED_EXCHANGES = frozenset({"NASDAQ", "NYSE", "AMEX"})
EXCLUDED_NAME_WORDS = ("warrant", "right", " unit", "etf", "etn", "fund", "preferred", "depositary")
MIN_PREMARKET_DOLLAR_VOLUME = Decimal("100000")
MIN_PREMARKET_PRICE = Decimal("0.50")
COHORT_SIZE = 5
MAX_QUOTE_SPREAD_BPS = Decimal("150")
QUOTE_LOOKBACK = timedelta(minutes=30)
QUOTE_LOOKAHEAD = timedelta(seconds=60)
QUOTE_BUCKET_SECONDS = 15
ORDER_LATENCY = timedelta(milliseconds=250)  # PaperExecutionPolicy.latency_ms


def utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class AlpacaArchive:
    """Rate-limited, cached historical Alpaca SIP requests: one worker, about one request a second."""

    def __init__(self, cache_dir: Path, *, min_interval_seconds: float = 1.05, session: Any = None) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval_seconds = min_interval_seconds
        self.session = session or requests.Session()
        self.request_count = 0
        self._last_request = 0.0

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(6):
            wait = self.min_interval_seconds - (time_module.monotonic() - self._last_request)
            if wait > 0:
                time_module.sleep(wait)
            self._last_request = time_module.monotonic()
            self.request_count += 1
            response = self.session.get(
                f"{ALPACA_DATA_URL}{path}", params=params, headers=alpaca_iex_auth_headers(), timeout=45
            )
            if response.status_code != 429:
                response.raise_for_status()
                return response.json()
            time_module.sleep(min(float(response.headers.get("Retry-After") or 2 ** attempt), 30.0))
        raise RuntimeError(f"alpaca rate limited {path} after retries")

    def _cached(self, kind: str, key_parts: dict[str, Any], fetch) -> Any:
        digest = hashlib.sha256(json.dumps(key_parts, sort_keys=True, default=str).encode()).hexdigest()[:24]
        path = self.cache_dir / f"{kind}-{digest}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        value = fetch()
        path.write_text(json.dumps(value), encoding="utf-8")
        return value

    def bars(
        self, symbols: list[str], *, timeframe: str, start: datetime, end: datetime, adjustment: str = "raw"
    ) -> dict[str, list[dict[str, Any]]]:
        ordered = sorted(set(symbols))
        key = {"symbols": ordered, "timeframe": timeframe, "start": utc_iso(start), "end": utc_iso(end), "adj": adjustment}

        def fetch() -> dict[str, list[dict[str, Any]]]:
            output: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for index in range(0, len(ordered), 200):
                params: dict[str, Any] = {
                    "symbols": ",".join(ordered[index:index + 200]), "timeframe": timeframe, "start": utc_iso(start),
                    "end": utc_iso(end), "adjustment": adjustment, "feed": "sip", "sort": "asc", "limit": 10000,
                }
                while True:
                    payload = self._get("/v2/stocks/bars", params)
                    for symbol, rows in (payload.get("bars") or {}).items():
                        output[symbol].extend(rows)
                    token = payload.get("next_page_token")
                    if not token:
                        break
                    params["page_token"] = token
            return dict(output)

        return self._cached("bars", key, fetch)

    def news(self, symbols: list[str], *, start: datetime, end: datetime) -> list[dict[str, Any]]:
        key = {"symbols": sorted(symbols), "start": utc_iso(start), "end": utc_iso(end)}

        def fetch() -> list[dict[str, Any]]:
            params: dict[str, Any] = {
                "symbols": ",".join(sorted(symbols)), "start": utc_iso(start), "end": utc_iso(end),
                "sort": "asc", "limit": 50, "include_content": "false",
            }
            rows: list[dict[str, Any]] = []
            while True:
                payload = self._get("/v1beta1/news", params)
                rows.extend(payload.get("news") or [])
                token = payload.get("next_page_token")
                if not token:
                    return rows
                params["page_token"] = token

        return self._cached("news", key, fetch)

    def quote(self, symbol: str, *, after: datetime | None = None, before: datetime | None = None) -> dict[str, Any] | None:
        """The first usable NBBO at or after ``after``, or the last at or before ``before``."""
        if (after is None) == (before is None):
            raise ValueError("quote needs exactly one of after or before")
        if after is not None:
            start, end, sort = after, after + QUOTE_LOOKAHEAD, "asc"
        else:
            assert before is not None
            start, end, sort = before - QUOTE_LOOKBACK, before, "desc"
        key = {"symbol": symbol, "start": utc_iso(start), "end": utc_iso(end), "sort": sort}

        def fetch() -> list[dict[str, Any]]:
            payload = self._get(
                "/v2/stocks/quotes",
                {"symbols": symbol, "start": utc_iso(start), "end": utc_iso(end), "feed": "sip", "sort": sort, "limit": 25},
            )
            return list((payload.get("quotes") or {}).get(symbol) or [])

        for row in self._cached("quote", key, fetch):
            if row.get("bp") and row.get("ap") and Decimal(str(row["ap"])) >= Decimal(str(row["bp"])):
                return row
        return None


def listed_common_symbols(assets_file: Path = ASSETS_FILE) -> list[str]:
    payload = json.loads(assets_file.read_text(encoding="utf-8"))
    symbols: list[str] = []
    for asset in payload.get("assets") or []:
        name = str(asset.get("name") or "").casefold()
        symbol = str(asset.get("symbol") or "")
        if (
            asset.get("exchange") in LISTED_EXCHANGES
            and asset.get("status") == "active"
            and symbol.isalpha()
            and not any(word in name for word in EXCLUDED_NAME_WORDS)
        ):
            symbols.append(symbol)
    return sorted(set(symbols))


@dataclass(frozen=True)
class Gainer:
    symbol: str
    previous_close: Decimal
    premarket_price: Decimal
    gap_pct: Decimal
    premarket_volume: Decimal
    premarket_dollar_volume: Decimal
    premarket_bar_count: int


def rank_premarket_gainers(
    previous_close: dict[str, Decimal],
    premarket_bars: dict[str, list[dict[str, Any]]],
    *,
    cutoff: datetime,
    size: int = COHORT_SIZE,
) -> list[Gainer]:
    """The biggest premarket gainers using only bars finished by ``cutoff``, liquid enough to have a real price."""
    gainers: list[Gainer] = []
    for symbol, rows in premarket_bars.items():
        base = previous_close.get(symbol)
        known = [row for row in rows if parse_time(row["t"]) + timedelta(minutes=5) <= cutoff]
        if not base or not known:
            continue
        price = Decimal(str(known[-1]["c"]))
        volume = sum((Decimal(str(row["v"])) for row in known), Decimal("0"))
        dollars = sum((Decimal(str(row["v"])) * Decimal(str(row.get("vw") or row["c"])) for row in known), Decimal("0"))
        if price < MIN_PREMARKET_PRICE or dollars < MIN_PREMARKET_DOLLAR_VOLUME:
            continue
        gainers.append(
            Gainer(symbol, base, price, (price / base - 1) * 100, volume, dollars, len(known))
        )
    return sorted(gainers, key=lambda item: (-item.gap_pct, item.symbol))[:size]


def session_bounds(session: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(session, time(9, 30), tzinfo=ET).astimezone(UTC),
        datetime.combine(session, time(16, 0), tzinfo=ET).astimezone(UTC),
    )


def build_minute_tape(symbol: str, instrument_id: str, rows: list[dict[str, Any]], *, session: date, previous_close: Decimal) -> list[MarketBar]:
    """Premarket bars as traded, then one bar for every regular-session minute (flat and empty when nothing traded)."""
    opening, closing = session_bounds(session)
    by_start = {parse_time(row["t"]): row for row in rows}
    premarket_start = datetime.combine(session, time(4, 0), tzinfo=ET).astimezone(UTC)

    def market_bar(start: datetime, values: dict[str, Any], label: str) -> MarketBar:
        return MarketBar(
            instrument_id=instrument_id, interval="1m", start_time=start, end_time=start + timedelta(minutes=1),
            open=Decimal(str(values["o"])), high=Decimal(str(values["h"])), low=Decimal(str(values["l"])),
            close=Decimal(str(values["c"])), volume=Decimal(str(values["v"])), session=label, provider=PROVIDER,
        )

    tape = [market_bar(start, row, "premarket") for start, row in sorted(by_start.items()) if premarket_start <= start < opening]
    last_close = tape[-1].close if tape else previous_close
    cursor = opening
    while cursor < closing:
        row = by_start.get(cursor)
        if row is None:
            row = {"o": last_close, "h": last_close, "l": last_close, "c": last_close, "v": 0}
        bar = market_bar(cursor, row, "regular")
        last_close = bar.close
        tape.append(bar)
        cursor += timedelta(minutes=1)
    return tape


class SimClock:
    """Simulated time: set to a step, then advanced by the real time spent on that monitor's model calls."""

    def __init__(self, start: datetime) -> None:
        self.set(start)

    def set(self, value: datetime) -> None:
        self.base = value.astimezone(UTC)
        self._started = time_module.monotonic()

    def now(self) -> datetime:
        return self.base + timedelta(seconds=time_module.monotonic() - self._started)


class ReplayRepository:
    """The strategy repository the AI monitors use, in memory."""

    def __init__(self, config: Any, universe: Any) -> None:
        self.config = config
        self.universe = universe
        self.events: list[Any] = []
        self._keys: set[str] = set()
        self.on_append = None

    def list_configs(self, *, active_only: bool = False) -> list[Any]:
        return [self.config]

    def get_config(self, strategy_id: str) -> Any:
        if strategy_id != self.config.strategy_id:
            raise ValueError("strategy_config_not_found")
        return self.config

    def get_universe(self, universe_id: str) -> Any:
        return self.universe

    def append_event(self, event: Any) -> bool:
        if event.idempotency_key in self._keys:
            return False
        self._keys.add(event.idempotency_key)
        self.events.append(event)
        if self.on_append is not None:
            self.on_append(event)
        return True

    def recent_events(self, strategy_id: str, limit: int = 200) -> list[Any]:
        rows = [event for event in self.events if event.strategy_id == strategy_id]
        return sorted(rows, key=lambda event: event.observed_at, reverse=True)[:limit]

    def events_by_types_between(
        self, strategy_id: str, *, event_types: Any, start_time: datetime, end_time: datetime, limit: int = 10_000
    ) -> list[Any]:
        wanted = set(event_types)
        rows = [
            event for event in self.events
            if event.strategy_id == strategy_id and event.event_type in wanted and start_time <= event.observed_at <= end_time
        ]
        return sorted(rows, key=lambda event: event.observed_at)[-limit:]


class ReplayTriggerRepository:
    def __init__(self) -> None:
        self.plans: dict[str, Any] = {}

    def create(self, plan: Any) -> Any:
        self.plans[plan.trigger_plan_id] = plan
        return plan

    def active_for_strategy(self, strategy_id: str) -> list[Any]:
        return [
            plan for plan in self.plans.values()
            if plan.strategy_id == strategy_id and plan.status in {"ARMED", "TRIGGERED", "EXECUTION_CHECK"}
        ]

    def save_transition(self, current: Any, updated: Any) -> Any:
        self.plans[updated.trigger_plan_id] = updated
        return updated


class ReplayResearchRepository:
    """Archived headlines, each visible only from its own publication time."""

    def __init__(self, news: dict[str, list[TradingEvidence]]) -> None:
        self.news = news

    def latest_report_as_of(self, instrument_id: str, as_of: datetime) -> None:
        return None

    def list_evidence_as_of(self, instrument_id: str, as_of: datetime, limit: int = 200) -> list[TradingEvidence]:
        known = [item for item in self.news.get(instrument_id, []) if item.omnix_known_at <= as_of]
        return known[-limit:]


def news_evidence(rows: list[dict[str, Any]], instruments: dict[str, str]) -> dict[str, list[TradingEvidence]]:
    output: dict[str, list[TradingEvidence]] = defaultdict(list)
    for row in rows:
        published = parse_time(str(row["created_at"]))
        title = str(row.get("headline") or "").strip()
        if not title:
            continue
        content = f"{title}\n{str(row.get('summary') or '').strip()}".strip()
        digest = hashlib.sha256(content.encode()).hexdigest()
        for symbol in row.get("symbols") or []:
            instrument = instruments.get(symbol)
            if instrument is None:
                continue
            output[instrument].append(
                TradingEvidence(
                    evidence_id=f"alpaca-news-{row['id']}-{symbol}", instrument_id=instrument, evidence_type="news_headline",
                    source_type="news", source_locator=str(row.get("url") or f"alpaca-news:{row['id']}"),
                    source_authority_tier=3, source_published_at=published, source_available_at=published,
                    captured_at=published, omnix_known_at=published, title=title, content=content, content_hash=digest,
                    extraction_status="snippet", metadata={"source": row.get("source"), "replay": True},
                    immutable_fingerprint=hashlib.sha256(f"{row['id']}:{symbol}:{digest}".encode()).hexdigest(),
                )
            )
    return {key: sorted(value, key=lambda item: item.omnix_known_at) for key, value in output.items()}


@dataclass
class ReplayMarket:
    """Bars and quotes bounded by the simulated clock: the only market data an arm can reach."""

    clock: SimClock
    archive: Any
    tapes: dict[str, list[MarketBar]]
    bindings: dict[str, str]
    symbols: dict[str, str]
    session: date
    errors: Counter = field(default_factory=Counter)

    def _known(self, instrument_id: str, as_of: datetime | None = None) -> list[MarketBar]:
        cutoff = min(as_of.astimezone(UTC), self.clock.now()) if as_of is not None else self.clock.now()
        return [bar for bar in self.tapes.get(instrument_id, []) if bar.end_time <= cutoff]

    def bars(self, instrument_id, interval, limit=500, binding_id=None, cancellation=None, **_):
        if interval != "1m":
            raise ValueError(f"replay serves 1m bars only, not {interval}")
        return SimpleNamespace(bars=self._known(instrument_id)[-max(int(limit or 500), 1000):], provenance=None)

    def recovered_bars(
        self, instrument_id, interval, limit=500, binding_id=None, *, session_date, as_of,
        max_primary_attempts=2, cancellation=None, knowledge_mode="live", knowledge_cutoff=None,
    ) -> RecoveredBars:
        known = self._known(instrument_id, as_of)[-max(int(limit or 500), 1000):]
        empty = tuple(bar.start_time for bar in known if bar.session == "regular" and bar.volume == 0)
        report = RecoveryReport(
            instrument_id=instrument_id, interval=interval, session_date=session_date, as_of=as_of,
            knowledge_mode=knowledge_mode, knowledge_cutoff=knowledge_cutoff, primary_provider=PROVIDER,
            primary_attempt_count=1, expected_bar_count=len(known), primary_bar_count=len(known),
            canonical_bar_count=len(known), confirmed_nontrading_starts=empty, source_providers=(PROVIDER,),
            dataset_fingerprint=hashlib.sha256(f"{instrument_id}:{utc_iso(as_of)}:{len(known)}".encode()).hexdigest(),
        )
        return RecoveredBars(bars=tuple(known), report=report, primary_response=SimpleNamespace(bars=list(known), provenance=None))

    def execution_indicator_bars(self, instrument_id, binding_id=None, *, as_of=None, **_):
        return self._known(instrument_id, as_of)

    def _observation(self, instrument_id: str, quote: dict[str, Any]) -> ExecutionObservation:
        quoted_at = parse_time(str(quote["t"]))
        bid, ask = Decimal(str(quote["bp"])), Decimal(str(quote["ap"]))
        traded = [bar for bar in self.tapes.get(instrument_id, []) if bar.end_time <= quoted_at]
        last = traded[-1].close if traded else (bid + ask) / 2
        spread = (ask - bid) / ((ask + bid) / 2) * 10_000
        eligible = spread <= MAX_QUOTE_SPREAD_BPS
        open_at, close_at = session_bounds(self.session)
        return ExecutionObservation(
            instrument_id=instrument_id, binding_id=self.bindings[instrument_id], provider=PROVIDER, bid=bid, ask=ask,
            bid_size=Decimal(str(quote.get("bs") or 0)), ask_size=Decimal(str(quote.get("as") or 0)), last=last,
            source_time=quoted_at, received_at=quoted_at,
            session="regular" if open_at <= quoted_at < close_at else "extended_pre",
            freshness_mode="live", market_data_type="HISTORICAL_SIP_NBBO", market_data_eligible=True,
            paper_fill_eligible=eligible, execution_eligible=eligible,
            rejection_reasons=() if eligible else ("REPLAY_SPREAD_ABOVE_LIMIT",),
        )

    def observation_as_of(self, instrument_id: str, as_of: datetime, *, bucket_seconds: int = QUOTE_BUCKET_SECONDS) -> ExecutionObservation | None:
        seconds = int(as_of.timestamp())
        bucket = datetime.fromtimestamp(seconds - seconds % bucket_seconds, UTC)
        quote = self.archive.quote(self.symbols[instrument_id], before=bucket)
        return None if quote is None else self._observation(instrument_id, quote)

    def execution_observation(self, instrument_id, binding_id=None, **_):
        # V2 fills from this quote: it must be current, or it predates the decision it is meant to fill.
        observation = self.observation_as_of(instrument_id, self.clock.now(), bucket_seconds=1)
        if observation is None:
            raise ValueError("replay_quote_unavailable")
        return observation

    # The execution-observation plane the monitors read.
    def latest(self, instrument_id: str, *, as_of: datetime | None = None) -> ExecutionObservationEnvelope | None:
        observation = self.observation_as_of(instrument_id, min(as_of or self.clock.now(), self.clock.now()))
        return None if observation is None else ExecutionObservationEnvelope(observation=observation, recorded_at=observation.source_time)

    def first_causal_after(
        self, instrument_id, *, decision_completed_at, actionable_at=None, market_snapshot_as_of=None, binding_id=None, purpose="EXECUTION",
    ) -> CausalExecutionSelection | None:
        actionable = actionable_at or decision_completed_at
        # An order works from its paper latency on.
        earliest = max(decision_completed_at, actionable) + ORDER_LATENCY
        quote = self.archive.quote(self.symbols[instrument_id], after=earliest)
        if quote is None:
            return None
        observation = self._observation(instrument_id, quote)
        return CausalExecutionSelection(
            instrument_id=instrument_id, binding_id=observation.binding_id, provider=observation.provider,
            market_snapshot_as_of=market_snapshot_as_of or earliest, decision_completed_at=decision_completed_at,
            actionable_at=actionable, first_post_decision_quote_at=observation.source_time,
            quote_source_at=observation.source_time, quote_received_at=observation.source_time,
            capture_lag_seconds=Decimal(str(max((observation.source_time - earliest).total_seconds(), 0))),
            observation=observation,
        )


def replay_steps(session: date, *, until: time | None = None) -> list[datetime]:
    """Before the open for the morning catalyst freeze, each finished minute, then after the close for the summaries."""
    moments = [time(9, 16, 5), time(9, 20, 5), time(9, 25, 5)]
    cursor = datetime.combine(session, time(9, 31, 5))
    while cursor.time() <= time(16, 0, 5):
        moments.append(cursor.time())
        cursor += timedelta(minutes=1)
    moments += [time(16, 5, 5), time(16, 20, 5), time(16, 40, 5)]
    return [
        datetime.combine(session, moment, tzinfo=ET).astimezone(UTC)
        for moment in moments
        if until is None or moment <= until
    ]


def build_cohort(
    archive: AlpacaArchive, session: date, previous_session: date, *, assets_file: Path = ASSETS_FILE, size: int = COHORT_SIZE,
) -> list[Gainer]:
    symbols = listed_common_symbols(assets_file)
    day = lambda value: datetime.combine(value, time(0), tzinfo=ET)  # noqa: E731
    adjusted = archive.bars(symbols, timeframe="1Day", start=day(previous_session), end=day(session) + timedelta(days=1), adjustment="split")
    raw = archive.bars(symbols, timeframe="1Day", start=day(session), end=day(session) + timedelta(days=1), adjustment="raw")
    previous_close: dict[str, Decimal] = {}
    for symbol, rows in adjusted.items():
        by_day = {parse_time(row["t"]).astimezone(ET).date(): row for row in rows}
        before, today, raw_today = by_day.get(previous_session), by_day.get(session), (raw.get(symbol) or [None])[0]
        # A split after this session would make today's adjusted bars differ from what traded; that history is unusable.
        if before and today and raw_today and Decimal(str(today["c"])) == Decimal(str(raw_today["c"])):
            previous_close[symbol] = Decimal(str(before["c"]))
    start = datetime.combine(session, time(4, 0), tzinfo=ET)
    cutoff = datetime.combine(session, time(9, 15), tzinfo=ET)
    premarket = archive.bars(sorted(previous_close), timeframe="5Min", start=start, end=cutoff, adjustment="raw")
    return rank_premarket_gainers(previous_close, premarket, cutoff=cutoff.astimezone(UTC), size=size)


def freeze_cohort(gainers: list[Gainer], session: date, config: Any) -> Any:
    evaluation = datetime.combine(session, time(9, 15), tzinfo=ET).astimezone(UTC)
    candidates = [
        GapperCandidate(
            instrument_id=f"equity:US:{gainer.symbol}", binding_id=f"{PROVIDER}:{gainer.symbol}", observed_at=evaluation,
            previous_close=gainer.previous_close, premarket_price=gainer.premarket_price, gap_pct=gainer.gap_pct,
            premarket_volume=gainer.premarket_volume, premarket_dollar_volume=gainer.premarket_dollar_volume,
            premarket_bar_count=gainer.premarket_bar_count, tod_rvol=None, market_data_complete=True,
            data_quality_flags=(), spread_bps=None, discovery_rank=rank,
        )
        for rank, gainer in enumerate(gainers, 1)
    ]
    return freeze_gapper_universe(
        universe_id=f"replay-{session.isoformat()}-0915", session_date=session, evaluation_time=evaluation,
        discovery_source="import", candidates=candidates, source_locator=f"alpaca-sip-premarket#{session.isoformat()}",
        source_candidate_symbols=tuple(gainer.symbol for gainer in gainers),
    )


def deterministic_on_tape(universe: Any, tapes: dict[str, list[MarketBar]], config: Any, session: date) -> dict[str, Any]:
    """The arms the older replay refuses when a minute is missing, on this tape where an empty minute is a flat bar."""
    from app.apps.trading.paper import PaperExecutionPolicy
    from app.apps.trading.strategies.models import StochRsi5mConfig
    from app.apps.trading.strategy_backtest import freeze_backtest_session, run_gap_pullback_backtest
    from app.apps.trading.strategy_stoch_rsi_5m import evaluate_stoch_rsi_5m
    from app.apps.trading.strategy_timeframes import resample_final_bars

    regular = {instrument: [bar for bar in tape if bar.session == "regular"] for instrument, tape in tapes.items()}
    dataset = freeze_backtest_session(session_date=session, universe=universe, bars_by_instrument=regular)
    result = run_gap_pullback_backtest(
        dataset, config.config, PaperExecutionPolicy(max_volume_participation_pct=Decimal("1")),
        assumed_spread_bps=Decimal("40"), max_hold_minutes=config.config.v2_max_hold_minutes,
        max_concurrent_positions=config.risk.max_positions, risk_profile=config.risk, initial_cash=Decimal("100000"),
    )
    gap_pullback = [
        {
            "symbol": trade.instrument_id.rsplit(":", 1)[-1],
            "entry_price": str(trade.entry_price), "exit_price": str(trade.exit_price),
            "return_pct": str((trade.exit_price / trade.entry_price - 1) * 100),
        }
        for trade in result.trades
    ]
    decisions = {
        decision.instrument_id.rsplit(":", 1)[-1]: str(getattr(decision, "reason_code", None) or getattr(decision, "state", ""))
        for decision in result.candidate_decisions
    }
    fast = StochRsi5mConfig(rsi_period=9, stochastic_period=9, k_smoothing_period=3, d_smoothing_period=3)
    fast_trades: list[dict[str, str]] = []
    for instrument, bars in regular.items():
        snapshot = evaluate_stoch_rsi_5m(list(resample_final_bars(bars, "5m")), fast)
        fast_trades.extend(
            {"symbol": instrument.rsplit(":", 1)[-1], "entry_time": str(trade.entry_time), "return_pct": str(trade.return_pct)}
            for trade in snapshot.trades
        )
    return {"gap_pullback_v2": {"trades": gap_pullback, "decisions": decisions}, "stoch_rsi_5min_fast": fast_trades}


def install_local_model_route(base_url: str) -> None:
    """Send every trading model call to the model loaded in LM Studio; there is no settings service in a script."""
    import app.settings.effective_defaults as effective_defaults
    from app.apps.trading.model_route import TRADING_ROUTE_KEY
    from app.providers import service as provider_service

    overrides = {TRADING_ROUTE_KEY: {"providerId": "lmstudio", "modelId": ""}}
    effective_defaults.load_effective_profile = lambda: SimpleNamespace(
        global_settings=SimpleNamespace(routing=SimpleNamespace(task_overrides=overrides))
    )
    provider_service.load_settings = lambda *a, **k: {"provider": "lmstudio", "lmstudio": {"base_url": base_url, "model": ""}}
    provider_service.load_secrets = lambda *a, **k: {}
    provider_service._subscribe_provider_cache_invalidation = lambda: None


def build_monitors(clock: SimClock, repository: Any, trigger_repository: Any, research_repository: Any, market: Any) -> dict[str, Any]:
    from app.apps.trading import strategy_ai_shadow_v2_monitor as v2_module
    from app.apps.trading.strategy_ai_shadow_monitor import TradingAIShadowMonitor
    from app.apps.trading.strategy_ai_shadow_v3_monitor import TradingAIShadowV3Monitor

    # Live research reads today's internet. The replay's news is the archive behind the research repository.
    v2_module.run_trading_research = lambda *a, **k: None
    v2_module.create_trading_research_request = lambda *a, **k: None
    common = {"strategy_repository_factory": lambda: repository, "market_service_factory": lambda: market, "now_factory": clock.now}
    return {
        "C/D": TradingAIShadowMonitor(execution_plane=market, **common),
        "V2": v2_module.TradingAIShadowV2Monitor(research_repository_factory=lambda: research_repository, **common),
        "V3": TradingAIShadowV3Monitor(trigger_repository_factory=lambda: trigger_repository, execution_plane=market, **common),
    }


def event_row(event: Any) -> dict[str, Any]:
    return {
        "observed_at": utc_iso(event.observed_at), "event_type": event.event_type, "state": event.state,
        "reason_code": event.reason_code, "instrument_id": event.instrument_id, "payload": event.payload,
    }


async def run_replay(
    monitors: dict[str, Any], clock: SimClock, steps: list[datetime], *, progress=print, concurrent: bool = False,
) -> dict[str, Counter]:
    """Run each step's monitors one after another, or together as the live scheduler does (queueing included)."""
    failures: dict[str, Counter] = {name: Counter() for name in monitors}
    for index, step in enumerate(steps, 1):
        started = time_module.monotonic()
        if concurrent:
            clock.set(step)
            for monitor in monitors.values():
                monitor.last_error = None
            await asyncio.gather(*(monitor.run_once() for monitor in monitors.values()))
        for name, monitor in monitors.items():
            if not concurrent:
                clock.set(step)
                monitor.last_error = None
                await monitor.run_once()
            if monitor.last_error:
                failures[name][str(monitor.last_error)[:200]] += 1
        progress(f"{index}/{len(steps)} {step.astimezone(ET):%H:%M:%S} ET in {time_module.monotonic() - started:.1f}s")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay the interday SHADOW AI arms over a past session on a local model.")
    parser.add_argument("--session", required=True, type=date.fromisoformat)
    parser.add_argument("--previous-session", required=True, type=date.fromisoformat)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--lmstudio-url", default="http://127.0.0.1:1234")
    parser.add_argument("--until", type=time.fromisoformat, default=None, help="stop after this ET time (a short check)")
    parser.add_argument("--cohort-size", type=int, default=COHORT_SIZE, help="stocks in the universe (live reached 14)")
    parser.add_argument("--concurrent", action="store_true", help="run the monitors together, as the live scheduler does")
    args = parser.parse_args()

    # Evidence from a replay must never reach the live database.
    os.environ.pop("OMNIX_DATABASE_URL", None)
    os.environ["OMNIX_TRADING_AI_SHADOW_CIRCUIT_PERSISTENCE"] = "0"
    logging.disable(logging.WARNING)
    from app.apps.trading.strategy_managed_finviz_shadow import managed_finviz_shadow_document

    install_local_model_route(args.lmstudio_url)
    output = args.cache_root / args.session.isoformat()
    archive = AlpacaArchive(output / "alpaca")
    config = managed_finviz_shadow_document("replay")
    gainers = build_cohort(archive, args.session, args.previous_session, size=args.cohort_size)
    if len(gainers) < args.cohort_size:
        raise SystemExit(f"cohort has only {len(gainers)} names")
    universe = freeze_cohort(gainers, args.session, config)
    with (output / "cohort.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["session_date", "rank", "symbol", "gain_pct", "source_url"])
        for rank, gainer in enumerate(gainers, 1):
            writer.writerow([args.session.isoformat(), rank, gainer.symbol, "", "alpaca-sip-premarket-0915"])
    print("cohort:", [(g.symbol, f"{g.gap_pct:.1f}%", f"${g.premarket_price}", f"${g.premarket_dollar_volume:,.0f}") for g in gainers], flush=True)

    start, end = session_bounds(args.session)
    premarket_start = datetime.combine(args.session, time(4, 0), tzinfo=ET)
    symbols = [gainer.symbol for gainer in gainers]
    minute_bars = archive.bars(symbols, timeframe="1Min", start=premarket_start, end=end)
    instruments = {symbol: f"equity:US:{symbol}" for symbol in symbols}
    closes = {gainer.symbol: gainer.previous_close for gainer in gainers}
    tapes = {
        instruments[symbol]: build_minute_tape(symbol, instruments[symbol], minute_bars.get(symbol, []), session=args.session, previous_close=closes[symbol])
        for symbol in symbols
    }
    news_rows = archive.news(symbols, start=premarket_start - timedelta(days=3), end=end)
    deterministic = deterministic_on_tape(universe, tapes, config, args.session)
    (output / "deterministic-on-tape.json").write_text(json.dumps(deterministic, indent=1, default=str), encoding="utf-8")
    print("deterministic on tape:", json.dumps(deterministic, default=str)[:1500], flush=True)
    clock = SimClock(start)
    repository = ReplayRepository(config, universe)
    market = ReplayMarket(
        clock=clock, archive=archive, tapes=tapes, session=args.session,
        bindings={instrument: f"{PROVIDER}:{symbol}" for symbol, instrument in instruments.items()},
        symbols={instrument: symbol for symbol, instrument in instruments.items()},
    )
    events_path = output / ("events.jsonl" if args.until is None else "events-check.jsonl")
    events_file = events_path.open("w", encoding="utf-8")

    def on_append(event: Any) -> None:
        events_file.write(json.dumps(event_row(event), default=str) + "\n")
        events_file.flush()

    repository.on_append = on_append
    monitors = build_monitors(clock, repository, ReplayTriggerRepository(), ReplayResearchRepository(news_evidence(news_rows, instruments)), market)
    steps = replay_steps(args.session, until=args.until)
    failures = asyncio.run(
        run_replay(monitors, clock, steps, progress=lambda line: print(line, flush=True), concurrent=args.concurrent)
    )
    events_file.close()

    summary = {
        "session": args.session.isoformat(),
        "cohort": [
            {"symbol": g.symbol, "gap_pct": str(g.gap_pct), "premarket_price": str(g.premarket_price), "premarket_dollar_volume": str(g.premarket_dollar_volume)}
            for g in gainers
        ],
        "steps": len(steps),
        "alpaca_requests": archive.request_count,
        "headlines": len(news_rows),
        "event_counts": Counter(f"{event.event_type}:{event.state}" for event in repository.events).most_common(),
        "monitor_errors": {name: counter.most_common(12) for name, counter in failures.items()},
        "session_summaries": [
            event_row(event) for event in repository.events
            if event.event_type in {"ai_shadow_session_summary", "ai_v2_session_summary", "shadow_strategy_comparison", "ai_v2_catalyst_lift_summary"}
        ],
    }
    name = "summary.json" if args.until is None else "summary-check.json"
    (output / name).write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("steps", "alpaca_requests", "headlines", "event_counts", "monitor_errors")}, indent=1, default=str)[:6000], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
