from __future__ import annotations

import asyncio
import threading
from datetime import date, datetime, time, timezone
from decimal import Decimal

import pytest

from app.apps.trading.strategies.models import OvernightArmConfig, OvernightShadowConfig
from app.apps.trading.strategies.registrations import STRATEGY_REGISTRY
from app.apps.trading.strategy_monitor import strategy_monitor_owns
from app.apps.trading.strategy_overnight_monitor import (
    EVENT_OUTCOME,
    EVENT_PICK,
    EVENT_SCAN,
    EVENT_SCORECARD,
    OVERNIGHT_SHADOW_ACCOUNT_ID,
    OvernightShadowMonitor,
    overnight_shadow_document,
    provision_overnight_shadow_strategy,
)
from app.apps.trading.strategy_overnight_scan import OvernightScanResult, is_common_stock
from app.apps.trading.strategy_overnight_shadow import (
    OVERNIGHT_BENCHMARKS,
    OVERNIGHT_TRADING_STRATEGY_ID,
    OvernightBar,
    OvernightBenchmark,
    OvernightSocialMention,
    build_benchmark,
    build_candidate,
    label_benchmark,
    label_outcome,
    population,
    select_arm_picks,
)
from app.apps.trading.strategy_repository import TradingStrategyConfigDocument
from app.apps.trading.strategy_universe_archiver import archive_daily_universe_if_due
from app.apps.trading.us_equity_calendar import EASTERN as ET

D = Decimal
SESSION = date(2026, 10, 13)      # Tuesday
NEXT = date(2026, 10, 14)


def _bar(day: date, hh: int, mm: int, o, h, l, c, v) -> OvernightBar:
    return OvernightBar(datetime.combine(day, time(hh, mm), tzinfo=ET), D(str(o)), D(str(h)), D(str(l)), D(str(c)), D(str(v)))


def _candidate(symbol="RUNR", *, change="0.40", price="4.20", close_location="0.9", volume_ratio="8", dollar_volume="5000000"):
    from app.apps.trading.strategy_overnight_shadow import OvernightCandidate
    prior = D(price) / (1 + D(change))
    return OvernightCandidate(
        symbol=symbol, instrument_id=f"equity:NASDAQ:{symbol}", prior_close=prior, price=D(price), change=D(change),
        high=D(price), low=prior, close_location=D(close_location), volume=D("1000000"), adv=D("100000"),
        volume_ratio=None if volume_ratio is None else D(volume_ratio), dollar_volume=D(dollar_volume),
    )


# ------------------------------------------------------------ config and registry
def test_overnight_kind_is_registered_shadow_only_and_not_strategy_monitor_owned() -> None:
    entry = STRATEGY_REGISTRY.get("overnight_shadow_v1")
    assert entry.allowed_modes == ("off", "shadow")
    doc = overnight_shadow_document("acct")
    assert doc.strategy_id == OVERNIGHT_TRADING_STRATEGY_ID and doc.mode == "shadow"
    payload = doc.model_dump(mode="python")
    payload["mode"] = "auto_paper"
    with pytest.raises(ValueError, match="overnight_shadow_is_shadow_only"):
        TradingStrategyConfigDocument.model_validate(payload)
    assert strategy_monitor_owns(doc) is False
    gap = TradingStrategyConfigDocument(strategy_id="g", account_id="a")
    assert strategy_monitor_owns(gap) is True


def test_overnight_config_rejects_inconsistent_times_and_duplicate_arms() -> None:
    with pytest.raises(ValueError, match="data_cutoff_et < decision_et < entry_et"):
        OvernightShadowConfig(decision_et=time(15, 56))
    arm = OvernightArmConfig(arm_id="day2-runner", min_change=D("0.3"), min_volume_ratio=D("5"), min_close_location=D("0.8"))
    with pytest.raises(ValueError, match="unique"):
        OvernightShadowConfig(arms=(arm, arm))
    with pytest.raises(ValueError, match="max_change must exceed min_change"):
        OvernightArmConfig(arm_id="strong-close", min_change=D("0.3"), max_change=D("0.1"),
                           min_volume_ratio=D("3"), min_close_location=D("0.9"))


def test_universe_archiver_skips_kinds_without_a_gapper_universe() -> None:
    assert archive_daily_universe_if_due(overnight_shadow_document("acct"), repository=None) is None


# ------------------------------------------------------------ pure logic
def test_build_candidate_uses_only_bars_ended_by_the_cutoff() -> None:
    bars = [
        _bar(SESSION, 9, 30, 2.0, 2.5, 1.9, 2.4, 100_000),
        _bar(SESSION, 15, 0, 2.4, 3.0, 2.3, 2.9, 200_000),
        _bar(SESSION, 15, 30, 2.9, 9.0, 0.5, 8.0, 999_999),  # ends 16:00: unknown at decision time
    ]
    c = build_candidate(symbol="ABC", instrument_id="equity:NASDAQ:ABC", prior_close=D("2"), bars=bars,
                        adv_volumes=[D("30000")] * 20, session_date=SESSION, config=OvernightShadowConfig())
    assert c is not None
    assert c.price == D("2.9") and c.high == D("3.0") and c.low == D("1.9")
    assert c.change == D("0.450000")
    assert c.volume == D("300000") and c.volume_ratio == D("10.000000")
    short = build_candidate(symbol="ABC", instrument_id="x", prior_close=D("2"), bars=bars[:2],
                            adv_volumes=[D("1")] * 5, session_date=SESSION, config=OvernightShadowConfig())
    assert short is not None and short.adv is None and short.volume_ratio is None  # < min_adv_sessions
    assert short.prior_return_5d is None and short.prior_up_days_5d is None       # no prior closes given


def test_build_candidate_records_the_five_session_trend_into_the_decision_day() -> None:
    bars = [_bar(SESSION, 9, 30, 2.0, 2.5, 1.9, 2.4, 100_000)]
    closes = [D(x) for x in ("9", "1.0", "1.1", "1.05", "1.2", "1.3", "1.5")]   # only the last six count
    c = build_candidate(symbol="ABC", instrument_id="x", prior_close=D("1.5"), bars=bars, adv_volumes=[D("1")] * 20,
                        session_date=SESSION, config=OvernightShadowConfig(), prior_closes=closes)
    assert c is not None and c.prior_return_5d == D("0.500000") and c.prior_up_days_5d == 4
    assert c.prior_return_20d is None                                         # seven closes: no 20-session trend
    month = [D("1")] * 20 + [D("1.25")]
    c20 = build_candidate(symbol="ABC", instrument_id="x", prior_close=D("1.25"), bars=bars, adv_volumes=[D("1")] * 20,
                          session_date=SESSION, config=OvernightShadowConfig(), prior_closes=month)
    assert c20 is not None and c20.prior_return_20d == D("0.250000")
    few = build_candidate(symbol="ABC", instrument_id="x", prior_close=D("1.5"), bars=bars, adv_volumes=[D("1")] * 20,
                          session_date=SESSION, config=OvernightShadowConfig(), prior_closes=closes[-5:])
    assert few is not None and few.prior_return_5d is None and few.prior_up_days_5d is None


def test_picks_recorded_before_the_trend_fields_still_validate() -> None:
    from app.apps.trading.strategy_overnight_shadow import OvernightCandidate
    old = _candidate().model_dump(mode="json")
    del old["prior_return_5d"], old["prior_up_days_5d"]
    assert OvernightCandidate.model_validate(old).prior_return_5d is None


def test_social_mentions_follow_pages_and_skip_malformed_rows() -> None:
    from app.apps.trading.strategy_overnight_scan import OvernightMarketData

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class Runtime:
        def __init__(self):
            self.urls = []

        def get(self, url, **kwargs):
            self.urls.append(url)
            page = int(url.rsplit("/", 1)[1])
            rows = {1: [{"rank": 1, "ticker": "spy", "mentions": 87, "upvotes": 984, "rank_24h_ago": 1,
                         "mentions_24h_ago": 55}, {"ticker": "BAD"}],
                    2: [{"rank": 101, "ticker": "RUN1", "mentions": "3", "upvotes": None, "rank_24h_ago": None,
                         "mentions_24h_ago": None}]}[page]
            return Response({"count": 3, "pages": 2, "current_page": page, "results": rows})

    runtime = Runtime()
    mentions = OvernightMarketData(runtime=object(), social_runtime=runtime).social_mentions()
    assert [u.rsplit("/", 1)[1] for u in runtime.urls] == ["1", "2"]
    assert [(m.symbol, m.rank, m.mentions, m.upvotes, m.rank_24h_ago) for m in mentions] == [
        ("SPY", 1, 87, 984, 1), ("RUN1", 101, 3, 0, None)]


def test_arm_selection_applies_rules_and_ranks_by_dollar_volume() -> None:
    cands = [
        _candidate("RUN1", change="0.40", dollar_volume="9000000"),
        _candidate("RUN2", change="0.35", dollar_volume="1000000"),
        _candidate("WEAK", change="0.40", close_location="0.5"),           # fails day2 close location
        _candidate("THIN", change="0.40", volume_ratio="2"),               # fails volume ratio
        _candidate("NOADV", change="0.40", volume_ratio=None),             # no ADV -> never qualifies
        _candidate("MID1", change="0.15", close_location="0.95"),
        _candidate("EDGE", change="0.30", close_location="0.95"),          # max_change is exclusive
        _candidate("PRICY", change="0.40", price="25"),                    # outside price band
    ]
    picks = select_arm_picks(cands, OvernightShadowConfig())
    assert [p.candidate.symbol for p in picks["day2-runner"]] == ["RUN1", "EDGE", "RUN2"]  # $9M, $5M, $1M
    assert [p.rank for p in picks["day2-runner"]] == [1, 2, 3]
    assert [p.candidate.symbol for p in picks["strong-close"]] == ["MID1"]
    assert [c.symbol for c in population(cands, OvernightShadowConfig())] == sorted(
        ["RUN1", "RUN2", "WEAK", "THIN", "NOADV", "MID1", "EDGE"])


def test_label_outcome_entry_exit_costs_and_missing_bars() -> None:
    c = _candidate("RUN1", price="4.00", change="0.40")
    cfg = OvernightShadowConfig()
    session = [_bar(SESSION, 15, 54, 4.0, 4.0, 4.0, 4.0, 1), _bar(SESSION, 15, 55, 4.10, 4.2, 4.0, 4.1, 1)]
    morning = [_bar(NEXT, 7, 59, 4.8, 4.8, 4.8, 4.9, 1), _bar(NEXT, 9, 30, 5.00, 5.1, 4.9, 5.0, 1),
               _bar(NEXT, 9, 45, 5.2, 5.2, 5.2, 5.2, 1)]
    o = label_outcome(arm_id="day2-runner", candidate=c, session_date=SESSION, next_session_date=NEXT,
                      session_bars=session, next_bars=morning, config=cfg)
    assert o.status == "labelled" and o.entry_price == D("4.10") and o.exit_open == D("5.00")
    assert o.premarket_0800 == D("4.9") and o.price_0945 == D("5.2")
    expected = D("5.00") * (1 - D("0.01")) / (D("4.10") * (1 + D("0.01"))) - 1
    assert o.net_return == expected.quantize(D("0.000001"))
    halted = label_outcome(arm_id="day2-runner", candidate=c, session_date=SESSION, next_session_date=NEXT,
                           session_bars=session, next_bars=[], config=cfg)
    assert halted.status == "no_open" and halted.net_return == D("-0.50")
    no_entry = label_outcome(arm_id="day2-runner", candidate=c, session_date=SESSION, next_session_date=NEXT,
                             session_bars=[], next_bars=morning, config=cfg)
    assert no_entry.status == "no_entry" and no_entry.net_return is None


def test_build_benchmark_uses_prior_closes_and_only_bars_ended_by_the_cutoff() -> None:
    daily = [
        _bar(date(2026, 10, 9), 0, 0, 1, 1, 1, 400, 1),
        _bar(date(2026, 10, 12), 0, 0, 1, 1, 1, 404, 1),   # prior session: +1% vs the 9th
        _bar(SESSION, 0, 0, 1, 1, 1, 999, 1),               # the decision day's own daily bar is ignored
    ]
    bars = [
        _bar(SESSION, 9, 30, 404, 406, 403, 405, 1),
        _bar(SESSION, 15, 0, 405, 410, 404, 408.04, 1),
        _bar(SESSION, 15, 30, 408, 420, 400, 419, 1),       # ends 16:00: unknown at decision time
    ]
    b = build_benchmark(symbol="IWM", daily=daily, bars=bars, session_date=SESSION, config=OvernightShadowConfig())
    assert b == OvernightBenchmark(symbol="IWM", prior_close=D("404"), prior_change=D("0.010000"),
                                   price=D("408.04"), change=D("0.010000"))
    lone = build_benchmark(symbol="IWM", daily=daily[1:2], bars=bars, session_date=SESSION, config=OvernightShadowConfig())
    assert lone is not None and lone.prior_change is None
    assert build_benchmark(symbol="IWM", daily=[], bars=bars, session_date=SESSION, config=OvernightShadowConfig()) is None
    assert build_benchmark(symbol="IWM", daily=daily, bars=bars[2:], session_date=SESSION,
                           config=OvernightShadowConfig()) is None


def test_label_benchmark_uses_the_picks_window_without_costs() -> None:
    cfg = OvernightShadowConfig()
    session = [_bar(SESSION, 15, 54, 499, 499, 499, 499, 1), _bar(SESSION, 15, 55, 500, 501, 499, 500, 1)]
    morning = [_bar(NEXT, 8, 0, 503, 503, 503, 503, 1), _bar(NEXT, 9, 30, 505, 506, 504, 505, 1)]
    b = label_benchmark(symbol="SPY", session_date=SESSION, next_session_date=NEXT, session_bars=session,
                        next_bars=morning, config=cfg)
    assert (b.entry_price, b.exit_open, b.overnight_return) == (D("500"), D("505"), D("0.010000"))
    missing = label_benchmark(symbol="SPY", session_date=SESSION, next_session_date=NEXT, session_bars=session,
                              next_bars=[], config=cfg)
    assert missing.entry_price == D("500") and missing.exit_open is None and missing.overnight_return is None


def test_scan_reads_split_adjusted_daily_history_and_raw_intraday_bars(monkeypatch) -> None:
    from app.apps.trading import strategy_overnight_scan as scan_module

    calls = []

    def fake_bars(runtime, headers, symbols, *, timeframe, start, end, chunk_size, feed="iex", adjustment="raw"):
        calls.append((timeframe, adjustment))
        if timeframe == "1Day":
            return {s: [{"t": f"2026-10-{day:02d}T04:00:00Z", "o": 1, "h": 1, "l": 1, "c": 2, "v": 100}
                        for day in range(1, 13)] for s in symbols}
        return {s: [{"t": "2026-10-13T13:30:00Z", "o": 2, "h": 3, "l": 2, "c": 3, "v": 1000}] for s in symbols}

    monkeypatch.setattr(scan_module, "_alpaca_bars", fake_bars)
    monkeypatch.setattr(scan_module, "_alpaca_assets",
                        lambda runtime, headers: [{"symbol": "ABCD", "name": "Abcd Inc.", "exchange": "NASDAQ"}])
    monkeypatch.setattr(scan_module, "alpaca_iex_auth_headers", lambda: {})
    data = scan_module.OvernightMarketData(runtime=object(), social_runtime=object())
    result = data.scan(SESSION, date(2026, 10, 12), OvernightShadowConfig())
    data.benchmarks(SESSION, date(2026, 10, 12), OvernightShadowConfig())
    assert [c.symbol for c in result.candidates] == ["ABCD"] and result.candidates[0].change == D("0.500000")
    assert result.candidates[0].off_52w_high is None                       # 12 daily bars: no year to compare
    # history, intraday, a year of bars for the population (52-week high), then the benchmarks
    assert calls == [("1Day", "split"), ("30Min", "raw"), ("1Day", "split"), ("1Day", "split"), ("30Min", "raw")]


def test_a_failed_52_week_fetch_keeps_the_candidates(monkeypatch) -> None:
    from app.apps.trading import strategy_overnight_scan as scan_module

    daily_calls = []

    def fake_bars(runtime, headers, symbols, *, timeframe, start, end, chunk_size, feed="iex", adjustment="raw"):
        if timeframe == "1Day":
            daily_calls.append(start)
            if len(daily_calls) == 2:
                raise RuntimeError("alpaca busy")
            return {s: [{"t": f"2026-10-{day:02d}T04:00:00Z", "o": 1, "h": 1, "l": 1, "c": 2, "v": 100}
                        for day in range(1, 13)] for s in symbols}
        return {s: [{"t": "2026-10-13T13:30:00Z", "o": 2, "h": 3, "l": 2, "c": 3, "v": 1000}] for s in symbols}

    monkeypatch.setattr(scan_module, "_alpaca_bars", fake_bars)
    monkeypatch.setattr(scan_module, "_alpaca_assets",
                        lambda runtime, headers: [{"symbol": "ABCD", "name": "Abcd Inc.", "exchange": "NASDAQ"}])
    monkeypatch.setattr(scan_module, "alpaca_iex_auth_headers", lambda: {})
    result = scan_module.OvernightMarketData(runtime=object(), social_runtime=object()).scan(
        SESSION, date(2026, 10, 12), OvernightShadowConfig())
    assert [c.symbol for c in result.candidates] == ["ABCD"] and result.candidates[0].off_52w_high is None


def test_off_52w_high_uses_up_to_a_year_of_prior_daily_highs() -> None:
    from datetime import timedelta as td

    from app.apps.trading.strategy_overnight_shadow import OFF_52W_MIN_SESSIONS, off_52w_high
    c = _candidate(price="4.20", change="0.40")                              # prior close 3.00
    start = SESSION - td(days=400)
    bars = [_bar(start + td(days=i), 0, 0, 1, 6.0 if i == 10 else 4.0, 1, 3, 1) for i in range(300)]
    # The 6.00 high is older than the last 250 bars, so the year's high is 4.00.
    assert off_52w_high(c, bars, SESSION) == D("-0.250000")
    assert off_52w_high(c, bars[-(OFF_52W_MIN_SESSIONS - 1):], SESSION) is None
    today = _bar(SESSION, 0, 0, 1, 99, 1, 3, 1)                                # the decision day itself is ignored
    assert off_52w_high(c, [*bars, today], SESSION) == D("-0.250000")


def test_mid_population_uses_price_dollar_volume_and_change_bands() -> None:
    from app.apps.trading.strategy_overnight_shadow import mid_population

    def mid(symbol, price, change, dollars):
        return _candidate(symbol, price=price, change=change).model_copy(
            update={"adv_dollars": None if dollars is None else D(dollars)})

    cands = [mid("IN", "30", "0.05", "10000000"), mid("SLOW", "30", "0.049", "10000000"),
             mid("CHEAP", "4.99", "0.08", "10000000"), mid("DEAR", "50.01", "0.08", "10000000"),
             mid("THIN", "30", "0.08", "4999999"), mid("BIG", "30", "0.08", "50000001"), mid("NOADV", "30", "0.08", None)]
    assert [c.symbol for c in mid_population(cands)] == ["IN"]


def test_news_context_counts_and_uses_the_frozen_categories() -> None:
    from app.apps.trading.strategy_overnight_shadow import NEWS_CATEGORIES, OvernightHeadline, news_context
    assert list(NEWS_CATEGORIES) == ["offering", "reverse_split", "fda_clinical", "deal", "earnings", "theme"]
    at = datetime.combine(SESSION, time(9, 0), tzinfo=ET)
    rows = [OvernightHeadline(id=str(i), created_at=at.replace(minute=i), headline=h) for i, h in enumerate(
        ["Abc reports third quarter results", "Abc signs definitive agreement", "Abc board meeting",
         "x", "y", "z", "Abc announces 1-for-10 reverse stock split"])]
    c = news_context("ABC", rows)
    assert c.articles == 7 and c.categories == ["reverse_split", "deal", "earnings"]
    assert [h.id for h in c.headlines] == ["2", "3", "4", "5", "6"]          # newest five kept
    assert news_context("ABC", []).articles == 0


def test_news_reads_pages_and_keeps_only_requested_symbols() -> None:
    from app.apps.trading.strategy_overnight_scan import OvernightMarketData

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class Runtime:
        def __init__(self):
            self.params = []

        def get(self, url, params=None, **kwargs):
            assert url.endswith("/v1beta1/news")
            self.params.append(dict(params))
            if "page_token" not in params:
                return Response({"news": [{"id": 1, "created_at": "2026-10-13T13:00:00Z", "headline": "A and B",
                                           "symbols": ["ABC", "OTHER"]}], "next_page_token": "p2"})
            return Response({"news": [{"id": 2, "created_at": "2026-10-13T14:00:00Z", "headline": "B again",
                                       "symbols": ["XYZ"]}, {"bad": True}], "next_page_token": None})

    runtime = Runtime()
    data = OvernightMarketData(runtime=runtime, social_runtime=object())
    data._headers = lambda: {}
    found = data.news(["XYZ", "ABC"], datetime(2026, 10, 12, 20, tzinfo=timezone.utc),
                      datetime(2026, 10, 13, 19, 30, tzinfo=timezone.utc))
    assert {s: [h.id for h in rows] for s, rows in found.items()} == {"ABC": ["1"], "XYZ": ["2"]}
    assert runtime.params[0]["symbols"] == "ABC,XYZ" and runtime.params[1]["page_token"] == "p2"


def test_common_stock_filter() -> None:
    assert is_common_stock({"symbol": "ABCD", "name": "Abcd Inc. Common Stock", "exchange": "NASDAQ"})
    assert not is_common_stock({"symbol": "TQQQ", "name": "ProShares UltraPro QQQ", "exchange": "NASDAQ"})
    assert not is_common_stock({"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "exchange": "ARCA"})
    assert not is_common_stock({"symbol": "ABCDW", "name": "Abcd Inc. Warrant", "exchange": "NASDAQ"})
    assert is_common_stock({"symbol": "SNOWR", "name": "Snowr Holdings Ordinary Shares", "exchange": "NASDAQ"})


# ------------------------------------------------------------ monitor with fakes
class FakeRepository:
    def __init__(self, config=None) -> None:
        self.config = config
        self.events = {}

    def get_config(self, strategy_id):
        if self.config is None or strategy_id != self.config.strategy_id:
            raise ValueError("strategy_config_not_found")
        return self.config

    def create_config(self, document):
        self.config = document
        return document

    def append_event(self, event) -> bool:
        if event.idempotency_key in self.events:
            return False
        self.events[event.idempotency_key] = event
        return True

    def events_by_types_between(self, strategy_id, *, event_types, start_time, end_time, limit=10_000):
        return [e for e in self.events.values() if e.strategy_id == strategy_id and e.event_type in event_types
                and start_time <= e.observed_at < end_time]

    def of(self, event_type):
        return [e for e in self.events.values() if e.event_type == event_type]


class FakeMarketData:
    def __init__(self) -> None:
        self.scans = 0

    def scan(self, session_date, prior_session, config):
        self.scans += 1
        midcap = _candidate("MIDC", price="30.00", change="0.07").model_copy(update={"adv_dollars": D("10000000")})
        return OvernightScanResult(session_date=session_date, eligible=10, scanned=9, mid_eligible=4, candidates=(
            _candidate("RUN1", price="4.00", change="0.40"), _candidate("MID1", change="0.15", close_location="0.95"),
            midcap))

    def benchmarks(self, session_date, prior_session, config):
        return (OvernightBenchmark(symbol="IWM", prior_close=D("200"), prior_change=D("0.01"), price=D("198"),
                                   change=D("-0.01")),)

    def social_mentions(self):
        return (OvernightSocialMention(symbol="SPY", rank=1, mentions=87, upvotes=984, rank_24h_ago=1,
                                       mentions_24h_ago=55),
                OvernightSocialMention(symbol="RUN1", rank=40, mentions=12, upvotes=30, rank_24h_ago=None,
                                       mentions_24h_ago=None))

    def splits(self, symbols, start, end):
        return []

    def news(self, symbols, start, end):
        from app.apps.trading.strategy_overnight_shadow import OvernightHeadline
        self.news_window = (start, end)
        inside = datetime.combine(SESSION, time(9, 0), tzinfo=ET)
        after = datetime.combine(SESSION, time(15, 40), tzinfo=ET)            # past the 15:30 cutoff
        return {"RUN1": [OvernightHeadline(id="1", created_at=inside, headline="Runr announces $5M registered direct offering"),
                         OvernightHeadline(id="2", created_at=after, headline="Runr wins FDA clearance")]}

    def minute_bars(self, symbols, start, end):
        day = start.astimezone(ET).date()
        if day == SESSION:
            return {s: [_bar(SESSION, 15, 55, 4.0, 4, 4, 4, 1)] for s in symbols}
        return {s: [_bar(NEXT, 9, 30, 5.0, 5, 5, 5, 1)] for s in symbols}


class FakeFilings:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = []

    def contexts(self, symbols, *, decided_at):
        from app.apps.trading.strategy_overnight_filings import OvernightFilingContext
        self.calls.append((list(symbols), decided_at))
        if self.error:
            raise self.error
        return [OvernightFilingContext(symbol=s, cik="0000000001", prospectus_count=2) for s in symbols], False


def _monitor(repo, data, clock, filings=None):
    filings = filings or FakeFilings()
    return OvernightShadowMonitor(strategy_repository_factory=lambda: repo, market_data_factory=lambda: data,
                                  filings_factory=lambda: filings, now_factory=lambda: clock[0])


def test_monitor_scans_once_in_window_then_labels_next_morning_once() -> None:
    repo, data = FakeRepository(overnight_shadow_document("acct")), FakeMarketData()
    clock = [datetime.combine(SESSION, time(15, 49), tzinfo=ET).astimezone(timezone.utc)]
    monitor = _monitor(repo, data, clock)
    assert asyncio.run(monitor.run_once()) == 0 and data.scans == 0          # before decision time
    clock[0] = datetime.combine(SESSION, time(15, 51), tzinfo=ET).astimezone(timezone.utc)
    assert asyncio.run(monitor.run_once()) == 1
    assert asyncio.run(monitor.run_once()) == 0 and data.scans == 1          # idempotent per session
    assert len(repo.of(EVENT_SCAN)) == 1
    scan = repo.of(EVENT_SCAN)[0].payload
    assert scan["market"] == [{"symbol": "IWM", "prior_close": "200", "prior_change": "0.01", "price": "198",
                               "change": "-0.01"}]
    assert scan["market_error"] is None
    # Only population stocks are kept (SPY is ranked but not in the population).
    assert scan["social"] == {"source": "apewisdom:all-stocks", "ranked": 2, "error": None, "mentions": [
        {"symbol": "RUN1", "rank": 40, "mentions": 12, "upvotes": 30, "rank_24h_ago": None, "mentions_24h_ago": None}]}
    assert {(e.payload["arm_id"], e.payload["candidate"]["symbol"]) for e in repo.of(EVENT_PICK)} == {
        ("day2-runner", "RUN1"), ("strong-close", "MID1")}
    news = scan["news"]
    assert data.news_window == (datetime(2026, 10, 12, 16, 0, tzinfo=ET), datetime(2026, 10, 13, 15, 30, tzinfo=ET))
    assert news["error"] is None and news["source"] == "alpaca:benzinga"
    by = {c["symbol"]: c for c in news["contexts"]}
    assert set(by) == {"MID1", "RUN1", "MIDC"}                               # both populations, one request
    assert by["MID1"]["articles"] == 0 and by["MID1"]["categories"] == []    # explicit: no headline
    from app.apps.trading.strategy_overnight_monitor import EVENT_MID_POPULATION
    mid_event = repo.of(EVENT_MID_POPULATION)[0].payload
    assert [c["symbol"] for c in mid_event["candidates"]] == ["MIDC"] and mid_event["eligible"] == 4
    assert scan["population"] == 2 and scan["mid_population"] == 1
    assert by["RUN1"]["articles"] == 1 and by["RUN1"]["categories"] == ["offering"]   # 15:40 headline excluded
    clock[0] = datetime.combine(NEXT, time(10, 0), tzinfo=ET).astimezone(timezone.utc)
    assert asyncio.run(monitor.run_once()) == 0                               # before label_after_et
    clock[0] = datetime.combine(NEXT, time(10, 6), tzinfo=ET).astimezone(timezone.utc)
    assert asyncio.run(monitor.run_once()) == 1
    assert asyncio.run(monitor.run_once()) == 0                               # scorecard found: no relabel
    outcomes = repo.of(EVENT_OUTCOME)
    assert len(outcomes) == 2 and all(e.state == "labelled" for e in outcomes)
    card = repo.of(EVENT_SCORECARD)[0].payload
    assert card["execution_authority"] is False and card["population_10pct"]["picks"] == 2
    assert {a["arm_id"]: a["picks"] for a in card["arms"]} == {"day2-runner": 1, "strong-close": 1}
    assert [m["symbol"] for m in card["market"]] == list(OVERNIGHT_BENCHMARKS)
    assert all(m["overnight_return"] == "0.250000" for m in card["market"])   # 4.00 -> 5.00 in the fake


def test_filings_are_recorded_after_the_scan_marker_and_failures_never_block_it() -> None:
    from app.apps.trading.strategy_overnight_monitor import EVENT_FILINGS
    repo, data, filings = FakeRepository(overnight_shadow_document("acct")), FakeMarketData(), FakeFilings()
    clock = [datetime.combine(SESSION, time(15, 51), tzinfo=ET).astimezone(timezone.utc)]
    assert asyncio.run(_monitor(repo, data, clock, filings).run_once()) == 1
    keys = list(repo.events)
    assert repo.events[keys[-1]].event_type == EVENT_FILINGS              # written after the scan marker
    assert repo.events[keys[-2]].event_type == EVENT_SCAN
    payload = repo.of(EVENT_FILINGS)[0].payload
    assert filings.calls == [(["MID1", "RUN1"], clock[0])]                # population, cut at the decision time
    assert payload["error"] is None and payload["truncated"] is False and payload["execution_authority"] is False
    assert [(c["symbol"], c["prospectus_count"]) for c in payload["contexts"]] == [("MID1", 2), ("RUN1", 2)]

    failing_repo = FakeRepository(overnight_shadow_document("acct"))
    failing = FakeFilings(error=RuntimeError("edgar down"))
    assert asyncio.run(_monitor(failing_repo, FakeMarketData(), clock, failing).run_once()) == 1
    assert len(failing_repo.of(EVENT_SCAN)) == 1 and len(failing_repo.of(EVENT_PICK)) == 2
    assert failing_repo.of(EVENT_FILINGS)[0].payload["error"] == "RuntimeError: edgar down"


def test_labelling_adjusts_for_a_split_that_took_effect_overnight() -> None:
    class ReverseSplit(FakeMarketData):
        def minute_bars(self, symbols, start, end):
            if start.astimezone(ET).date() == SESSION:
                return {s: [_bar(SESSION, 15, 55, 4.0, 4, 4, 4, 1)] for s in symbols}
            # RUN1 did a 1-for-10 reverse split: 4.00 entry, 41.00 unadjusted open (+2.5% real).
            return {s: [_bar(NEXT, 9, 30, 41.0 if s == "RUN1" else 5.0, 41, 41, 41, 1)] for s in symbols}

        def splits(self, symbols, start, end):
            assert (start, end) == (SESSION, NEXT) and "RUN1" in symbols
            return [("RUN1", NEXT, D("10"), D("1")), ("OTHER", NEXT, D("10"), D("1"))]

    repo, data = FakeRepository(overnight_shadow_document("acct")), ReverseSplit()
    clock = [datetime.combine(SESSION, time(15, 51), tzinfo=ET).astimezone(timezone.utc)]
    monitor = _monitor(repo, data, clock)
    asyncio.run(monitor.run_once())
    clock[0] = datetime.combine(NEXT, time(10, 6), tzinfo=ET).astimezone(timezone.utc)
    assert asyncio.run(monitor.run_once()) == 1
    by_symbol = {e.payload["symbol"]: e.payload for e in repo.of(EVENT_OUTCOME)}
    assert by_symbol["RUN1"]["exit_open"] == "41.0" and by_symbol["RUN1"]["split_factor"] == "0.1"
    assert by_symbol["RUN1"]["gross_return"] == "0.025000"
    assert by_symbol["MID1"]["split_factor"] is None and by_symbol["MID1"]["gross_return"] == "0.250000"


def test_a_failed_split_lookup_defers_labelling() -> None:
    class NoSplits(FakeMarketData):
        def splits(self, symbols, start, end):
            raise RuntimeError("corporate actions unavailable")

    repo, data = FakeRepository(overnight_shadow_document("acct")), NoSplits()
    clock = [datetime.combine(SESSION, time(15, 51), tzinfo=ET).astimezone(timezone.utc)]
    monitor = _monitor(repo, data, clock)
    asyncio.run(monitor.run_once())
    clock[0] = datetime.combine(NEXT, time(10, 6), tzinfo=ET).astimezone(timezone.utc)
    with pytest.raises(RuntimeError, match="corporate actions unavailable"):
        asyncio.run(monitor.run_once())
    assert not repo.of(EVENT_OUTCOME) and not repo.of(EVENT_SCORECARD)    # retried on a later tick


def test_split_factors_and_label_outcome_use_only_overnight_splits() -> None:
    from app.apps.trading.strategy_overnight_shadow import split_factors
    factors = split_factors([
        ("RS", NEXT, D("10"), D("1")),             # 1-for-10 reverse split overnight
        ("FS", NEXT, D("1"), D("2")),              # 2-for-1 forward split overnight
        ("OLD", SESSION, D("10"), D("1")),         # took effect on the entry day: prices already agree
        ("BAD", NEXT, D("0"), D("1")),
    ], SESSION, NEXT)
    assert factors == {"RS": D("0.1"), "FS": D("2")}
    c = _candidate("RS", price="4.00")
    o = label_outcome(arm_id="day2-runner", candidate=c, session_date=SESSION, next_session_date=NEXT,
                      session_bars=[_bar(SESSION, 15, 55, 4.0, 4, 4, 4, 1)],
                      next_bars=[_bar(NEXT, 9, 30, 44.0, 44, 44, 44, 1)], config=OvernightShadowConfig(),
                      split_factor=factors["RS"])
    assert o.exit_open == D("44.0") and o.gross_return == D("0.100000") and o.gap_return == D("0.100000")
    expected = D("44.0") * D("0.1") * (1 - D("0.005")) / (D("4.0") * (1 + D("0.01"))) - 1
    assert o.net_return == expected.quantize(D("0.000001"))


def test_context_failures_still_record_the_picks() -> None:
    class NoContext(FakeMarketData):
        def benchmarks(self, session_date, prior_session, config):
            raise RuntimeError("benchmarks unavailable")

        def social_mentions(self):
            raise RuntimeError("apewisdom down")

        def news(self, symbols, start, end):
            raise RuntimeError("news down")

    repo, data = FakeRepository(overnight_shadow_document("acct")), NoContext()
    clock = [datetime.combine(SESSION, time(15, 51), tzinfo=ET).astimezone(timezone.utc)]
    assert asyncio.run(_monitor(repo, data, clock).run_once()) == 1
    scan = repo.of(EVENT_SCAN)[0].payload
    assert scan["market"] == [] and scan["market_error"] == "RuntimeError: benchmarks unavailable"
    assert scan["social"] == {"source": "apewisdom:all-stocks", "ranked": None, "mentions": [],
                              "error": "RuntimeError: apewisdom down"}
    assert scan["news"]["contexts"] == [] and scan["news"]["error"] == "RuntimeError: news down"   # unknown, not absent
    assert len(repo.of(EVENT_PICK)) == 2


def test_a_timed_out_scan_is_not_started_twice_and_its_failure_is_logged(monkeypatch) -> None:
    from app.apps.trading import monitor_task
    from app.apps.trading.monitor_task import TradingMonitorTask, scheduled_task_spec

    logged = []
    monkeypatch.setattr(monitor_task, "trade_log", lambda *args, **fields: logged.append((args, fields)))
    started, release = threading.Event(), threading.Event()

    class StalledMarketData(FakeMarketData):
        def scan(self, session_date, prior_session, config):
            self.scans += 1
            started.set()
            release.wait(5)
            raise RuntimeError("alpaca stalled")

    repo, data = FakeRepository(overnight_shadow_document("acct")), StalledMarketData()
    clock = [datetime.combine(SESSION, time(15, 51), tzinfo=ET).astimezone(timezone.utc)]
    monitor = _monitor(repo, data, clock)
    spec = scheduled_task_spec(TradingMonitorTask(name="tests.overnight", monitor=monitor, enabled=lambda: True))
    # The scan window is 15:50-16:00; a timeout retries instead of stopping the monitor.
    assert spec.timeout_seconds == 600.0 and spec.disable_on_timeout is False

    async def scenario():
        first = asyncio.create_task(monitor.run_once())
        assert await asyncio.to_thread(started.wait, 5)
        first.cancel()  # what the scheduler does when the cycle times out
        with pytest.raises(asyncio.CancelledError):
            await first
        assert await monitor.run_once() == 0  # the abandoned scan is still running
        release.set()

    asyncio.run(scenario())  # waits for the abandoned worker thread to exit
    assert data.scans == 1 and not repo.of(EVENT_SCAN)
    assert logged == [(
        ("auto_trading", "overnight_shadow_monitor_error"),
        {"error_type": "RuntimeError", "detail": "alpaca stalled", "execution_authority": False,
         "strategy_id": OVERNIGHT_TRADING_STRATEGY_ID},
    )]


def test_monitor_skips_early_close_off_mode_and_missing_config() -> None:
    data = FakeMarketData()
    early = date(2026, 11, 27)  # day after Thanksgiving: 13:00 close
    clock = [datetime.combine(early, time(15, 51), tzinfo=ET).astimezone(timezone.utc)]
    assert asyncio.run(_monitor(FakeRepository(overnight_shadow_document("a")), data, clock).run_once()) == 0
    off = overnight_shadow_document("a").model_copy(update={"mode": "off"})
    clock[0] = datetime.combine(SESSION, time(15, 51), tzinfo=ET).astimezone(timezone.utc)
    assert asyncio.run(_monitor(FakeRepository(off), data, clock).run_once()) == 0
    assert asyncio.run(_monitor(FakeRepository(None), data, clock).run_once()) == 0
    assert data.scans == 0


# ------------------------------------------------------------ provisioning
class FakePaperRepository:
    def __init__(self) -> None:
        self.accounts = []

    def list_accounts(self, limit=500):
        return [type("A", (), {"account_id": a})() for a in self.accounts]

    def create_account(self, request):
        self.accounts.append(request.account_id)
        self.names = [*getattr(self, "names", []), request.name]


def test_provisioning_creates_once_and_never_overwrites(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_TRADING_OVERNIGHT_SHADOW_AUTOPROVISION", "1")
    monkeypatch.setenv("OMNIX_TRADING_OVERNIGHT_SHADOW_AUTOPROVISION_IN_TESTS", "1")
    repo, paper = FakeRepository(None), FakePaperRepository()
    assert provision_overnight_shadow_strategy(strategy_repository=repo, paper_repository=paper) == "created"
    assert paper.accounts == [OVERNIGHT_SHADOW_ACCOUNT_ID] and repo.config.mode == "shadow"
    repo.config = repo.config.model_copy(update={"mode": "off"})   # operator change survives restart
    assert provision_overnight_shadow_strategy(strategy_repository=repo, paper_repository=paper) == "unchanged"
    assert repo.config.mode == "off" and paper.accounts == [OVERNIGHT_SHADOW_ACCOUNT_ID]


def test_the_shadow_account_carries_the_visible_product_name(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_TRADING_OVERNIGHT_SHADOW_AUTOPROVISION", "1")
    monkeypatch.setenv("OMNIX_TRADING_OVERNIGHT_SHADOW_AUTOPROVISION_IN_TESTS", "1")
    for product, expected in ((None, "Omnix Overnight SHADOW"), ("MarketPulse", "MarketPulse Overnight SHADOW")):
        if product is None:
            monkeypatch.delenv("OMNIX_PRODUCT_NAME", raising=False)
        else:
            monkeypatch.setenv("OMNIX_PRODUCT_NAME", product)
        paper = FakePaperRepository()
        provision_overnight_shadow_strategy(strategy_repository=FakeRepository(None), paper_repository=paper)
        assert paper.names == [expected]
