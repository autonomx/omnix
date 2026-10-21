"""Leader Momentum v1.2 recorded daily as a SHADOW arm of the interday group."""
from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.apps.trading import strategy_monitor_leader_momentum as lm_monitor
from app.apps.trading.models import MarketBar
from app.apps.trading.strategy_leader_momentum_continuation import LeaderMomentumSnapshot
from app.apps.trading.strategy_managed_finviz_shadow import INTERDAY_TRADING_STRATEGY_ID

OPEN = datetime(2026, 10, 20, 13, 30, tzinfo=timezone.utc)


def _bar(minute: int) -> MarketBar:
    start = OPEN + timedelta(minutes=minute)
    return MarketBar(
        instrument_id="equity:AMEX:HOST", interval="1m", start_time=start, end_time=start + timedelta(minutes=1),
        open=Decimal("2.50"), high=Decimal("2.50"), low=Decimal("2.50"), close=Decimal("2.50"),
        volume=Decimal("1000"), is_final=True, session="regular", provider="yahoo", received_at=start,
    )


class _Monitor:
    current_run_id = "run-lm"

    def __init__(self) -> None:
        self.leader_momentum_last: dict = {}
        self.leader_momentum_evaluated_through: dict = {}
        self.leader_momentum_event_count = 0
        self.events: list[dict] = []

    async def _event(self, repository, config, **event):
        self.events.append(event)
        return True


def _config(strategy_id: str = INTERDAY_TRADING_STRATEGY_ID):
    return SimpleNamespace(strategy_id=strategy_id, risk=SimpleNamespace(force_flat_et=time(15, 55)))


def test_leader_momentum_runs_daily_on_the_interday_group_and_records_changes_only(monkeypatch) -> None:
    snapshots = iter([
        LeaderMomentumSnapshot(state="waiting_leader", reason_code="WAITING", session_date="2026-10-20"),
        LeaderMomentumSnapshot(state="waiting_leader", reason_code="WAITING", session_date="2026-10-20"),
        LeaderMomentumSnapshot(state="long_active", reason_code="ENTERED", session_date="2026-10-20"),
    ])
    calls: list[dict] = []

    def fake_evaluate(bars, **window):
        calls.append(window)
        return next(snapshots)

    monkeypatch.setattr(lm_monitor, "evaluate_leader_momentum_continuation", fake_evaluate)
    monitor = _Monitor()
    universe = SimpleNamespace(universe_id="u-1", discovery_source="finviz")
    candidate = SimpleNamespace(instrument_id="equity:AMEX:HOST", discovery_rank=4)

    def run(bars, config=None):
        asyncio.run(lm_monitor.record_leader_momentum(monitor, config or _config(), None, universe, candidate, bars))

    run([_bar(0)])
    run([_bar(0)])  # the same finished bar is not evaluated again
    run([_bar(0), _bar(1)])  # unchanged state: evaluated, not recorded
    run([_bar(0), _bar(1), _bar(2)])  # state change: recorded
    run([_bar(0), _bar(1), _bar(2), _bar(3)], config=_config("stoch-rsi-5min"))  # other strategies: not run

    assert len(calls) == 3
    assert calls[0] == {
        "entry_start_et": time(9, 35), "last_entry_et": time(15, 0), "force_flat_et": time(15, 55),
    }
    assert [event["state"] for event in monitor.events] == ["waiting_leader", "long_active"]
    assert monitor.events[-1]["event_type"] == "leader_momentum"
    payload = monitor.events[-1]["payload"]
    assert payload["arm"] == "leader-momentum-continuation"
    assert payload["execution_authority"] is False and payload["research_only"] is True
    assert monitor.leader_momentum_event_count == 2
