"""Trend continuation T1: the TREND-1 rule as a daily SHADOW arm."""
from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.apps.trading import strategy_monitor_trend_t1 as t1_monitor
from app.apps.trading.models import MarketBar
from app.apps.trading.strategy_managed_finviz_shadow import INTERDAY_TRADING_STRATEGY_ID
from app.apps.trading.strategy_trend_continuation import evaluate_trend_t1
from app.apps.trading.us_equity_calendar import EASTERN

OPEN = datetime(2026, 10, 20, 13, 30, tzinfo=timezone.utc)  # 09:30 ET
PRIOR = Decimal("1.00")


def _price(minute: int) -> Decimal:
    """Flat at 1.05 until 10:00, up to 1.25 by 11:00, then down to 1.08 by 12:00, flat after."""
    if minute < 30:
        return Decimal("1.05")
    if minute < 90:
        return Decimal("1.05") + Decimal("0.20") * (minute - 30) / 60
    if minute < 150:
        return Decimal("1.25") - Decimal("0.17") * (minute - 90) / 60
    return Decimal("1.08")


def _bars(last_minute: int = 389, holes: tuple[int, ...] = ()) -> list[MarketBar]:
    bars = []
    for minute in range(last_minute + 1):
        if minute in holes:
            continue
        start = OPEN + timedelta(minutes=minute)
        price = _price(minute).quantize(Decimal("0.0001"))
        bars.append(MarketBar(
            instrument_id="equity:AMEX:HOST", interval="1m", start_time=start, end_time=start + timedelta(minutes=1),
            open=price, high=price + Decimal("0.002"), low=price - Decimal("0.002"), close=price,
            volume=Decimal("100000"), is_final=True, session="regular", provider="fixture", received_at=start,
        ))
    return bars


def _et(value: datetime) -> time:
    return value.astimezone(EASTERN).time()


def test_t1_enters_on_a_trending_new_high_and_exits_on_a_close_below_vwap() -> None:
    snap = evaluate_trend_t1(_bars(), prior_close=PRIOR)

    assert snap.state == "exited" and snap.exit_reason_code == "TREND_T1_CLOSE_BELOW_VWAP"
    assert snap.signal.gain_pct >= 10 and snap.signal.close > snap.signal.vwap
    assert snap.entry_time == snap.signal.signal_time  # the next 5m bar's open
    assert time(10, 0) <= _et(snap.entry_time) <= time(11, 0)
    assert time(11, 0) < _et(snap.exit_time) < time(12, 0)
    assert snap.execution_authority is False


def test_t1_is_causal_on_a_session_prefix() -> None:
    full = evaluate_trend_t1(_bars(), prior_close=PRIOR)
    entry_minute = int((full.entry_time - OPEN).total_seconds() // 60)
    exit_minute = int((full.exit_time - OPEN).total_seconds() // 60)

    assert evaluate_trend_t1(_bars(entry_minute - 1), prior_close=PRIOR).state == "waiting_signal"
    active = evaluate_trend_t1(_bars(exit_minute - 6), prior_close=PRIOR)
    assert active.state == "long_active" and active.entry_time == full.entry_time
    assert evaluate_trend_t1(_bars(exit_minute), prior_close=PRIOR).exit_time == full.exit_time


def test_trade_free_minutes_do_not_block_t1() -> None:
    # Thin names have minutes without trades; HOST had 16 on 2026-10-20 in holes of 2-3 minutes.
    holes = (41, 42, 43, 57, 58, 66, 67, 68, 100, 101)
    snap = evaluate_trend_t1(_bars(holes=holes), prior_close=PRIOR)
    assert snap.state == "exited"


def test_t1_needs_a_ten_percent_mover() -> None:
    snap = evaluate_trend_t1(_bars(), prior_close=Decimal("1.20"))
    assert snap.state == "waiting_signal" and snap.entry_time is None


class _Monitor:
    current_run_id = "run-t1"

    def __init__(self) -> None:
        self.trend_t1_last: dict = {}
        self.trend_t1_evaluated_through: dict = {}
        self.trend_t1_entries_captured: set = set()
        self.trend_t1_event_count = 0
        self.events: list[dict] = []

    async def _event(self, repository, config, **event):
        self.events.append(event)
        return True


class _MarketService:
    def __init__(self) -> None:
        self.requests: list[tuple] = []

    def execution_observation(self, instrument_id, binding_id=None, *, live_first=False):
        self.requests.append((instrument_id, binding_id, live_first))
        return SimpleNamespace(provider="ibkr", bid=Decimal("1.21"), ask=Decimal("1.22"), spread_bps=Decimal("82"),
                               execution_eligible=True, rejection_reasons=())


def test_the_monitor_records_t1_state_changes_and_the_entry_quote_once() -> None:
    monitor, market = _Monitor(), _MarketService()
    config = SimpleNamespace(strategy_id=INTERDAY_TRADING_STRATEGY_ID)
    universe = SimpleNamespace(universe_id="u-1", discovery_source="finviz")
    candidate = SimpleNamespace(instrument_id="equity:AMEX:HOST", binding_id="yahoo:host", discovery_rank=4,
                                previous_close=PRIOR, catalyst_evidence_ids=("news-1",), tod_rvol=None, float_shares=None)
    full = evaluate_trend_t1(_bars(), prior_close=PRIOR)
    entry_minute = int((full.entry_time - OPEN).total_seconds() // 60)

    for last in (entry_minute - 1, entry_minute, entry_minute, entry_minute + 1, 389):
        asyncio.run(t1_monitor.record_trend_t1(monitor, config, None, market, universe, candidate, _bars(last)))
    asyncio.run(t1_monitor.record_trend_t1(
        monitor, SimpleNamespace(strategy_id="stoch-rsi-5min"), None, market, universe, candidate, _bars()
    ))

    kinds = [(event["event_type"], event["state"]) for event in monitor.events]
    assert kinds == [
        ("trend_t1", "waiting_signal"),
        ("trend_t1_entry", "entry_evidence"),
        ("trend_t1", "long_active"),
        ("trend_t1", "exited"),
    ]
    assert market.requests == [("equity:AMEX:HOST", "yahoo:host", True)]  # IBKR first, captured once
    entry = monitor.events[1]["payload"]
    assert entry["execution"]["provider"] == "ibkr" and entry["execution"]["spread_bps"] == "82"
    assert entry["catalyst_evidence_count"] == 1 and entry["arm"] == "trend-continuation-t1"
    assert monitor.trend_t1_event_count == 3
