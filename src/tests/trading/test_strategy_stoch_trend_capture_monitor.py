from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.trading.models import MarketBar
from app.trading.strategies.models import (
    GapPullbackConfig,
    GapPullbackFeatures,
    GapPullbackResult,
)
from app.trading.strategy_intraday_learning import IntradayLearningSnapshot
from app.trading.strategy_monitor import TradingStrategyMonitor
from app.trading.strategy_repository import TradingStrategyConfigDocument
from app.trading.strategy_stoch_trend_capture import StochTrendCaptureSnapshot
from app.trading import strategy_monitor as monitor_module


INSTRUMENT = "equity:NASDAQ:TEST"
SESSION_DATE = date(2026, 9, 2)
BAR_START = datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc)
SIGNAL_AT = datetime(2026, 9, 2, 13, 57, tzinfo=timezone.utc)
ENTRY_AT = datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc)


class MemoryRepository:
    def __init__(self) -> None:
        self.events = []

    def events_by_types_between(
        self,
        strategy_id: str,
        *,
        event_types,
        start_time,
        end_time,
        limit=10_000,
    ):
        matching = [
            event
            for event in self.events
            if event.strategy_id == strategy_id
            and event.event_type in event_types
            and start_time <= event.observed_at < end_time
        ]
        return sorted(matching, key=lambda event: event.observed_at)[:limit]

    def append_event(self, event):
        if any(existing.idempotency_key == event.idempotency_key for existing in self.events):
            return False
        self.events.append(event)
        return True


class FixtureMarketService:
    def __init__(self) -> None:
        self.execution_capture_calls = 0

    def bars(self, instrument_id, interval, limit, binding_id):
        assert instrument_id == INSTRUMENT
        assert interval == "1m"
        assert limit == 500
        return SimpleNamespace(
            bars=[
                MarketBar(
                    instrument_id=INSTRUMENT,
                    interval="1m",
                    start_time=BAR_START,
                    end_time=BAR_START + timedelta(minutes=1),
                    open=Decimal("10"),
                    high=Decimal("10.20"),
                    low=Decimal("9.90"),
                    close=Decimal("10.10"),
                    volume=Decimal("100000"),
                    is_final=True,
                    session="regular",
                    provider="fixture",
                    received_at=BAR_START + timedelta(minutes=1),
                )
            ]
        )


def _strategy() -> TradingStrategyConfigDocument:
    config = GapPullbackConfig(
        strategy_version="2.0.0",
        universe_discovery_source="finviz",
        intraday_learning_enabled=True,
        stoch_trend_capture_enabled=True,
        intraday_llm_enabled=False,
    )
    return TradingStrategyConfigDocument(
        strategy_id="stoch-monitor-test",
        account_id="paper-test",
        strategy_version="2.0.0",
        mode="shadow",
        config=config,
    )


def _universe():
    candidate = SimpleNamespace(
        instrument_id=INSTRUMENT,
        binding_id="fixture:TEST",
        discovery_rank=1,
    )
    return SimpleNamespace(
        universe_id="finviz-stoch-monitor-test",
        session_date=SESSION_DATE,
        discovery_source="finviz",
        candidates=[candidate],
    )


def _gap_result() -> GapPullbackResult:
    return GapPullbackResult(
        instrument_id=INSTRUMENT,
        state="discovered",
        reason_code="WAITING",
        features=GapPullbackFeatures(
            gap_pct=Decimal("25"),
            quality_score=5,
        ),
        transitions=("discovered",),
        signal=None,
        evaluated_bar_count=1,
    )


def _learning() -> IntradayLearningSnapshot:
    return IntradayLearningSnapshot(
        catalyst_quality_score=6,
        supply_risk_score=3,
        float_structure_risk_score=5,
        extension_risk_score=2,
        squeeze_probability_score=4,
        failed_selloff_probability_score=5,
        trend_continuation_score=4,
        gap_retention_score=6,
        execution_quality_score=8,
        opportunity_score=6,
        raw_movement_score=6,
        execution_adjusted_opportunity_score=6,
        pattern="unresolved",
        current_price=Decimal("10.10"),
        session_open=Decimal("10"),
        session_high=Decimal("10.20"),
        session_low=Decimal("9.90"),
        session_vwap=Decimal("10.05"),
        close_location=Decimal("0.6667"),
        gap_retention_ratio=Decimal("0.8"),
        turnover_to_float=Decimal("0.2"),
        current_vs_premarket_pct=Decimal("1"),
        session_return_pct=Decimal("1"),
        deterministic_state="discovered",
        deterministic_reason_code="WAITING",
        execution_authority=False,
    )


def _patch_common(monkeypatch, snapshot: StochTrendCaptureSnapshot) -> None:
    monkeypatch.setattr(monitor_module, "evaluate_gap_pullback", lambda *args, **kwargs: _gap_result())
    monkeypatch.setattr(
        monitor_module,
        "evaluate_stoch_trend_capture",
        lambda *args, **kwargs: snapshot,
    )
    monkeypatch.setattr(
        monitor_module,
        "build_intraday_learning_snapshot",
        lambda *args, **kwargs: _learning(),
    )


def _entry_events(repository: MemoryRepository):
    return [
        event
        for event in repository.events
        if event.event_type == "stoch_trend_capture_entry"
    ]


def test_monitor_captures_live_entry_evidence_once_and_dedupes(monkeypatch) -> None:
    snapshot = StochTrendCaptureSnapshot(
        state="entry_armed",
        reason_code="STOCH_TREND_FIRST_OVERSOLD_ARMED",
        three_minute_bar_count=30,
        entry_signal_time=SIGNAL_AT,
        stochastic_rsi_k=Decimal("12"),
        stochastic_rsi_d=Decimal("15"),
    )
    _patch_common(monkeypatch, snapshot)

    market = FixtureMarketService()

    def observe_shadow_execution(*args, **kwargs):
        market.execution_capture_calls += 1
        return SimpleNamespace(
            execution={
                "source_time": SIGNAL_AT + timedelta(seconds=8),
                "halted": False,
                "execution_eligible": True,
                "spread_bps": Decimal("40"),
            }
        )

    monkeypatch.setattr(
        monitor_module,
        "observe_shadow_execution",
        observe_shadow_execution,
    )

    repository = MemoryRepository()
    monitor = TradingStrategyMonitor(interval_seconds=30)
    monitor.current_run_id = "run-live-capture"

    asyncio.run(
        monitor._evaluate_candidates(
            _strategy(),
            repository,
            market,
            _universe(),
        )
    )
    asyncio.run(
        monitor._evaluate_candidates(
            _strategy(),
            repository,
            market,
            _universe(),
        )
    )

    entries = _entry_events(repository)
    assert market.execution_capture_calls == 1
    assert len(entries) == 1
    assert entries[0].observed_at == SIGNAL_AT
    assert entries[0].state == "entry_evidence"
    assert entries[0].payload["risk_decision"]["allowed"] is True
    assert entries[0].payload["execution_capture_lag_seconds"] == 8.0


def test_monitor_marks_missed_entry_evidence_fail_closed_without_backfill(monkeypatch) -> None:
    snapshot = StochTrendCaptureSnapshot(
        state="range_active",
        reason_code="STOCH_TREND_RANGE_WAITING_FOR_TREND_OR_OVERBOUGHT",
        three_minute_bar_count=31,
        entry_signal_time=SIGNAL_AT,
        entry_time=ENTRY_AT,
        entry_price=Decimal("10"),
        stochastic_rsi_k=Decimal("35"),
        stochastic_rsi_d=Decimal("32"),
    )
    _patch_common(monkeypatch, snapshot)

    market = FixtureMarketService()

    def should_not_capture(*args, **kwargs):
        market.execution_capture_calls += 1
        raise AssertionError("missed entry evidence must never be backfilled from a later quote")

    monkeypatch.setattr(
        monitor_module,
        "observe_shadow_execution",
        should_not_capture,
    )

    repository = MemoryRepository()
    monitor = TradingStrategyMonitor(interval_seconds=30)
    monitor.current_run_id = "run-missed-capture"

    asyncio.run(
        monitor._evaluate_candidates(
            _strategy(),
            repository,
            market,
            _universe(),
        )
    )
    asyncio.run(
        monitor._evaluate_candidates(
            _strategy(),
            repository,
            market,
            _universe(),
        )
    )

    entries = _entry_events(repository)
    assert market.execution_capture_calls == 0
    assert len(entries) == 1
    assert entries[0].observed_at == SIGNAL_AT
    assert entries[0].state == "entry_evidence"
    assert entries[0].payload["execution"] is None
    assert entries[0].payload["risk_decision"]["allowed"] is False
    assert entries[0].payload["risk_decision"]["reason_codes"] == [
        "STOCH_TREND_ENTRY_EVIDENCE_MISSED"
    ]
