from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.apps.trading.models import MarketBar
from app.apps.trading.strategies.models import (
    GapPullbackConfig,
    GapPullbackFeatures,
    GapPullbackResult,
)
from app.apps.trading.strategy_intraday_learning import IntradayLearningSnapshot
from app.apps.trading.strategy_monitor import TradingStrategyMonitor
from app.apps.trading.strategy_repository import StrategyEvent, TradingStrategyConfigDocument
from app.apps.trading.strategy_stoch_execution_cost import simulate_stoch_execution
from app.apps.trading.strategy_stoch_trend_capture import StochTrendCaptureSnapshot
from app.apps.trading import (
    strategy_monitor,
    strategy_monitor_candidates,
    strategy_monitor_config_run,
    strategy_monitor_stoch_capture,
    strategy_stoch_sweep,
)
from app.apps.trading.held_quote_demand import HeldQuoteDemand
from app.apps.trading.strategy_stoch_sweep import (
    TradingStochSweepMonitor,
    latest_bar_close,
    stoch_session_history,
)


class _MonitorModules:
    """The strategy monitor spans several modules; a patch reaches each one that uses the name."""

    _modules = (
        strategy_monitor,
        strategy_monitor_candidates,
        strategy_monitor_config_run,
        strategy_monitor_stoch_capture,
        strategy_stoch_sweep,
    )

    def __getattr__(self, name: str):
        for module in self._modules:
            if hasattr(module, name):
                return getattr(module, name)
        raise AttributeError(name)

    def __setattr__(self, name: str, value) -> None:
        for module in self._modules:
            if hasattr(module, name):
                setattr(module, name, value)


monitor_module = _MonitorModules()


INSTRUMENT = "equity:NASDAQ:TEST"
SESSION_DATE = date(2026, 9, 2)
BAR_START = datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc)
SIGNAL_AT = datetime(2026, 9, 2, 13, 57, tzinfo=timezone.utc)
ENTRY_AT = datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc)
EXIT_SIGNAL_AT = datetime(2026, 9, 2, 14, 30, tzinfo=timezone.utc)
EXIT_AT = datetime(2026, 9, 2, 14, 33, tzinfo=timezone.utc)


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
                "instrument_id": INSTRUMENT,
                "binding_id": "fixture:TEST",
                "provider": "alpaca_iex",
                "source_time": SIGNAL_AT + timedelta(seconds=8),
                "last": Decimal("10"),
                "bid": Decimal("9.98"),
                "ask": Decimal("10.02"),
                "bid_size": Decimal("1000"),
                "ask_size": Decimal("1000"),
                "halted": False,
                "execution_eligible": True,
                "freshness_mode": "live",
                "rejection_reasons": (),
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
    assert entries[0].payload["execution_simulation"]["fill_complete"] is True
    assert Decimal(entries[0].payload["execution_simulation"]["fill_price"]) > Decimal("10.02")


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


def test_monitor_records_spread_adjusted_range_exit_summary(monkeypatch) -> None:
    entry_execution = {
        "instrument_id": INSTRUMENT,
        "binding_id": "fixture:TEST",
        "provider": "alpaca_iex",
        "source_time": SIGNAL_AT + timedelta(seconds=2),
        "last": Decimal("10"),
        "bid": Decimal("9.95"),
        "ask": Decimal("10.05"),
        "bid_size": Decimal("1000"),
        "ask_size": Decimal("1000"),
        "halted": False,
        "execution_eligible": True,
        "freshness_mode": "live",
        "rejection_reasons": (),
        "spread_bps": Decimal("100"),
    }
    entry_simulation = simulate_stoch_execution(
        entry_execution,
        action="entry",
        instrument_id=INSTRUMENT,
        binding_id="fixture:TEST",
        decision_at=SIGNAL_AT,
        requested_fraction=Decimal("1"),
    )
    repository = MemoryRepository()
    repository.events.append(
        StrategyEvent(
            strategy_id="stoch-monitor-test",
            event_id="entry-existing",
            run_id="run-existing",
            instrument_id=INSTRUMENT,
            event_type="stoch_trend_capture_entry",
            state="entry_evidence",
            reason_code="STOCH_TREND_ENTRY_EVIDENCE_CAPTURED",
            observed_at=SIGNAL_AT,
            idempotency_key="entry-existing",
            payload={
                "risk_decision": {"allowed": True, "reason_codes": []},
                "execution": entry_execution,
                "execution_simulation": entry_simulation.model_dump(mode="json"),
                "research_only": True,
                "execution_authority": False,
            },
        )
    )

    armed = StochTrendCaptureSnapshot(
        state="range_exit_armed",
        reason_code="STOCH_TREND_RANGE_OVERBOUGHT_EXIT_ARMED",
        three_minute_bar_count=40,
        as_of=EXIT_SIGNAL_AT,
        entry_signal_time=SIGNAL_AT,
        entry_time=ENTRY_AT,
        entry_price=Decimal("10"),
        first_overbought_time=EXIT_SIGNAL_AT,
    )
    completed = StochTrendCaptureSnapshot(
        state="range_exited",
        reason_code="STOCH_TREND_RANGE_OVERBOUGHT_EXIT",
        three_minute_bar_count=41,
        as_of=EXIT_AT,
        entry_signal_time=SIGNAL_AT,
        entry_time=ENTRY_AT,
        entry_price=Decimal("10"),
        first_overbought_time=EXIT_SIGNAL_AT,
        runner_exit_time=EXIT_AT,
        runner_exit_price=Decimal("11"),
        combined_exit_price=Decimal("11"),
        return_pct=Decimal("10"),
    )
    snapshots = iter([armed, completed])
    monkeypatch.setattr(
        monitor_module,
        "evaluate_stoch_trend_capture",
        lambda *args, **kwargs: next(snapshots),
    )
    monkeypatch.setattr(
        monitor_module,
        "evaluate_gap_pullback",
        lambda *args, **kwargs: _gap_result(),
    )
    monkeypatch.setattr(
        monitor_module,
        "build_intraday_learning_snapshot",
        lambda *args, **kwargs: _learning(),
    )

    market = FixtureMarketService()

    def observe_exit(*args, **kwargs):
        market.execution_capture_calls += 1
        return SimpleNamespace(
            execution={
                "instrument_id": INSTRUMENT,
                "binding_id": "fixture:TEST",
                "provider": "alpaca_iex",
                "source_time": EXIT_SIGNAL_AT + timedelta(seconds=2),
                "last": Decimal("11"),
                "bid": Decimal("10.95"),
                "ask": Decimal("11.05"),
                "bid_size": Decimal("1000"),
                "ask_size": Decimal("1000"),
                "halted": False,
                "execution_eligible": True,
                "freshness_mode": "live",
                "rejection_reasons": (),
                "spread_bps": Decimal("90.9090909091"),
            }
        )

    monkeypatch.setattr(monitor_module, "observe_shadow_execution", observe_exit)

    monitor = TradingStrategyMonitor(interval_seconds=30)
    monitor.current_run_id = "run-execution-summary"

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

    execution_events = [
        event
        for event in repository.events
        if event.event_type == "stoch_trend_execution"
    ]
    summaries = [
        event
        for event in repository.events
        if event.event_type == "stoch_trend_execution_summary"
    ]
    assert market.execution_capture_calls == 1
    assert len(execution_events) == 1
    assert execution_events[0].payload["action"] == "range_exit"
    assert execution_events[0].payload["execution_simulation"]["fill_complete"] is True
    assert len(summaries) == 1
    policy = summaries[0].payload["policy"]
    assert policy["complete"] is True
    assert Decimal(policy["net_execution_return_pct"]) < Decimal("10")
    assert Decimal(policy["execution_drag_pct"]) > Decimal("0")


# --- The sweep: the Stoch arm is read at every 3m bar close (owner decision 2026-11-12) ---

FORCE_FLAT_AT = datetime(2026, 9, 2, 19, 57, tzinfo=timezone.utc)  # 15:57 ET, the force-flat bar's end
BAR = timedelta(minutes=3)


class SweepRepository(MemoryRepository):
    def __init__(self) -> None:
        super().__init__()
        self.list_calls = 0

    def list_configs(self, *, active_only: bool):
        assert active_only
        self.list_calls += 1
        return [_strategy()]


def _entered(repository: MemoryRepository) -> None:
    repository.events.append(
        StrategyEvent(
            strategy_id="stoch-monitor-test",
            event_id="entry-existing",
            run_id="run-existing",
            instrument_id=INSTRUMENT,
            event_type="stoch_trend_capture_entry",
            state="entry_evidence",
            reason_code="STOCH_TREND_ENTRY_EVIDENCE_CAPTURED",
            observed_at=SIGNAL_AT,
            idempotency_key="entry-existing",
            payload={"research_only": True, "execution_authority": False},
        )
    )


def _runner(**fields) -> StochTrendCaptureSnapshot:
    values = {
        "state": "trend_runner",
        "reason_code": "STOCH_TREND_RUNNER_ACTIVE",
        "three_minute_bar_count": 120,
        "entry_signal_time": SIGNAL_AT,
        "entry_time": ENTRY_AT,
        "entry_price": Decimal("10"),
    }
    values.update(fields)
    return StochTrendCaptureSnapshot(**values)


def _force_flat() -> StochTrendCaptureSnapshot:
    return _runner(
        state="force_flat",
        reason_code="STOCH_TREND_RANGE_FORCE_FLAT",
        as_of=FORCE_FLAT_AT,
        runner_exit_time=FORCE_FLAT_AT,
        runner_exit_price=Decimal("10.50"),
        combined_exit_price=Decimal("10.50"),
        return_pct=Decimal("5"),
    )


def _entry_armed() -> StochTrendCaptureSnapshot:
    return StochTrendCaptureSnapshot(
        state="entry_armed",
        reason_code="STOCH_TREND_FIRST_OVERSOLD_ARMED",
        three_minute_bar_count=9,
        as_of=SIGNAL_AT,
        entry_signal_time=SIGNAL_AT,
        stochastic_rsi_k=Decimal("25"),
        stochastic_rsi_d=Decimal("18"),
    )


def _live_quote(market: FixtureMarketService, at: datetime):
    def observe(*args, **kwargs):
        market.execution_capture_calls += 1
        return SimpleNamespace(
            execution={
                "instrument_id": INSTRUMENT,
                "binding_id": "fixture:TEST",
                "provider": "ibkr",
                "source_time": at,
                "last": Decimal("10.50"),
                "bid": Decimal("10.49"),
                "ask": Decimal("10.51"),
                "bid_size": Decimal("1000"),
                "ask_size": Decimal("1000"),
                "halted": False,
                "execution_eligible": True,
                "freshness_mode": "live",
                "rejection_reasons": (),
                "spread_bps": Decimal("19"),
            }
        )

    return observe


async def _ready_session_bars(market_service, universe, candidate, **kwargs):
    # The fixture's one bar is not a full session; the loader itself is the strategy pass's.
    bars = FixtureMarketService().bars(candidate.instrument_id, "1m", 500, candidate.binding_id).bars
    return strategy_monitor_candidates.CandidateSessionBars(
        primary_error=None,
        shared_recovery=None,
        base_bars=list(bars),
        gap_pullback_coverage=None,
        current_ready=True,
        integrity_reason="GAP_PULLBACK_REQUIRED_FEATURES_READY",
        bar_source="configured_history",
    )


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _sweep(repository, market, now) -> TradingStochSweepMonitor:
    clock = now if isinstance(now, _Clock) else _Clock(now)
    return TradingStochSweepMonitor(
        strategy_repository_factory=lambda: repository,
        market_service_factory=lambda: market,
        now_factory=clock,
    )


def _patch_sweep(monkeypatch, snapshots, market: FixtureMarketService, quote_at: datetime) -> HeldQuoteDemand:
    demand = HeldQuoteDemand()
    feed = iter(snapshots)
    monkeypatch.setattr(monitor_module, "evaluate_stoch_trend_capture", lambda *args, **kwargs: next(feed))
    monkeypatch.setattr(monitor_module, "observe_shadow_execution", _live_quote(market, quote_at))
    monkeypatch.setattr(monitor_module, "default_held_quote_demand", lambda: demand)
    monkeypatch.setattr(strategy_stoch_sweep, "resolve_v2_runtime_archive", lambda *args, **kwargs: _universe())
    monkeypatch.setattr(strategy_stoch_sweep, "load_candidate_session_bars", _ready_session_bars)
    return demand


def _executions(repository: MemoryRepository):
    return [event for event in repository.events if event.event_type == "stoch_trend_execution"]


def test_the_sweep_captures_an_entry_as_its_signal_bar_closes_and_the_pass_keeps_it(monkeypatch) -> None:
    repository = SweepRepository()
    market = FixtureMarketService()
    active = _runner(state="range_active", reason_code="STOCH_TREND_RANGE_ACTIVE", entry_signal_time=SIGNAL_AT)
    _patch_common(monkeypatch, active)
    _patch_sweep(monkeypatch, [_entry_armed(), active], market, SIGNAL_AT + timedelta(seconds=3))

    # 9:57:04 ET: the signal bar closed four seconds ago; the entry is captured from the live line.
    assert asyncio.run(_sweep(repository, market, SIGNAL_AT + timedelta(seconds=4)).run_once()) == 1
    entries = _entry_events(repository)
    assert len(entries) == 1
    assert entries[0].observed_at == SIGNAL_AT
    assert entries[0].payload["execution"]["provider"] == "ibkr"
    assert entries[0].payload["execution_capture_lag_seconds"] == 3.0
    assert entries[0].payload["risk_decision"]["allowed"] is True
    assert entries[0].payload["execution_simulation"] is not None
    assert entries[0].payload["execution_authority"] is False

    # The pass comes after the entry bar is final: before the sweep it recorded this entry as missed.
    monitor = TradingStrategyMonitor(interval_seconds=30)
    monitor.current_run_id = "run-after-entry-bar"
    asyncio.run(monitor._evaluate_candidates(_strategy(), repository, market, _universe()))
    entries = _entry_events(repository)
    assert len(entries) == 1
    assert entries[0].payload["risk_decision"]["reason_codes"] != ["STOCH_TREND_ENTRY_EVIDENCE_MISSED"]
    assert market.execution_capture_calls == 1


def test_the_sweep_captures_a_midday_runner_exit_within_seconds(monkeypatch) -> None:
    repository = SweepRepository()
    _entered(repository)
    market = FixtureMarketService()
    exit_armed = _runner(
        state="trend_exit_armed",
        reason_code="STOCH_TREND_RUNNER_EXIT_ARMED",
        as_of=EXIT_SIGNAL_AT,
        trend_break_time=EXIT_SIGNAL_AT,
    )
    _patch_sweep(monkeypatch, [exit_armed], market, EXIT_SIGNAL_AT + timedelta(seconds=3))

    # 10:30:05 ET: on 2026-11-12 a 13:51 runner exit waited two hours for the pass.
    sweep = _sweep(repository, market, EXIT_SIGNAL_AT + timedelta(seconds=5))
    assert asyncio.run(sweep.run_once()) == 1
    executions = _executions(repository)
    assert [event.state for event in executions] == ["runner_exit"]
    assert executions[0].observed_at == EXIT_SIGNAL_AT
    assert executions[0].payload["execution"]["provider"] == "ibkr"
    assert executions[0].payload["execution_simulation"] is not None
    # The position is closed and the slot done: the next runs read nothing.
    assert asyncio.run(sweep.run_once()) == 0
    assert sweep.read_count == 1


def test_the_sweep_rereads_a_stock_until_its_bar_arrives_then_waits_for_the_next_bar(monkeypatch) -> None:
    repository = SweepRepository()
    _entered(repository)
    market = FixtureMarketService()
    stale = _runner(as_of=EXIT_SIGNAL_AT - BAR)  # the 10:30 bar has not arrived
    _patch_sweep(monkeypatch, [stale] * 5, market, EXIT_SIGNAL_AT)
    clock = _Clock(EXIT_SIGNAL_AT + timedelta(seconds=5))
    sweep = _sweep(repository, market, clock)

    for seconds, reads in ((5, 1), (10, 2), (61, 3), (65, 3), (180 + 5, 4)):
        clock.now = EXIT_SIGNAL_AT + timedelta(seconds=seconds)
        assert asyncio.run(sweep.run_once()) == 0
        assert sweep.read_count == reads, seconds
    assert _executions(repository) == []
    assert market.execution_capture_calls == 0


def test_the_sweep_reads_a_stock_without_an_entry_only_while_an_entry_is_possible(monkeypatch) -> None:
    repository = SweepRepository()
    market = FixtureMarketService()
    waiting = StochTrendCaptureSnapshot(
        state="waiting_oversold",
        reason_code="STOCH_TREND_NO_CONFIRMED_ENTRY_SETUP",
        three_minute_bar_count=20,
    )
    _patch_sweep(monkeypatch, [waiting] * 3, market, SIGNAL_AT)
    clock = _Clock(SIGNAL_AT)
    sweep = _sweep(repository, market, clock)
    # 9:33 ET is before the entry window (9:35) and 11:33 ET after it (11:30); 9:57 ET is inside.
    for now, reads in (
        (datetime(2026, 9, 2, 13, 33, 5, tzinfo=timezone.utc), 0),
        (SIGNAL_AT + timedelta(seconds=5), 1),
        (datetime(2026, 9, 2, 15, 33, 5, tzinfo=timezone.utc), 1),
    ):
        clock.now = now
        assert asyncio.run(sweep.run_once()) == 0
        assert sweep.read_count == reads, now
    assert repository.events == []


def test_the_sweep_captures_the_force_flat_before_the_bell_and_the_pass_keeps_it(monkeypatch) -> None:
    repository = SweepRepository()
    _entered(repository)
    market = FixtureMarketService()
    _patch_common(monkeypatch, _runner())
    demand = _patch_sweep(
        monkeypatch,
        [_runner(as_of=FORCE_FLAT_AT - BAR), _force_flat(), _force_flat()],
        market,
        FORCE_FLAT_AT + timedelta(seconds=3),
    )

    # 15:56:30 ET: the force-flat bar is not final; the stock keeps its live line.
    assert asyncio.run(_sweep(repository, market, FORCE_FLAT_AT - timedelta(seconds=30)).run_once()) == 0
    assert demand.current(now=FORCE_FLAT_AT) == {INSTRUMENT}
    # 15:57:08 ET: the bar is final, and the exit is captured from the live quote.
    sweep = _sweep(repository, market, FORCE_FLAT_AT + timedelta(seconds=8))
    assert asyncio.run(sweep.run_once()) == 1
    assert asyncio.run(sweep.run_once()) == 0  # the position is closed now: nothing to re-read

    executions = _executions(repository)
    assert len(executions) == 1
    assert executions[0].state == "force_flat"
    assert executions[0].observed_at == FORCE_FLAT_AT
    assert executions[0].payload["execution"]["provider"] == "ibkr"
    assert executions[0].payload["execution_simulation"] is not None
    assert executions[0].payload["execution_authority"] is False

    # The strategy pass after the bell finds the exit captured and leaves it as it was.
    monitor = TradingStrategyMonitor(interval_seconds=30)
    monitor.current_run_id = "run-after-bell"
    asyncio.run(monitor._evaluate_candidates(_strategy(), repository, market, _universe()))
    assert market.execution_capture_calls == 1
    assert [event.state for event in _executions(repository)] == ["force_flat"]


def test_the_sweep_rests_outside_the_regular_session(monkeypatch) -> None:
    repository = SweepRepository()
    _entered(repository)
    market = FixtureMarketService()

    def no_universe(*args, **kwargs):
        raise AssertionError("outside the session the sweep reads nothing")

    monkeypatch.setattr(strategy_stoch_sweep, "resolve_v2_runtime_archive", no_universe)
    before_open = datetime(2026, 9, 2, 13, 29, tzinfo=timezone.utc)  # 9:29 ET
    first_bar_open = datetime(2026, 9, 2, 13, 32, 30, tzinfo=timezone.utc)  # 9:32:30 ET, no bar closed
    after_bell = datetime(2026, 9, 2, 20, 0, 1, tzinfo=timezone.utc)
    saturday = datetime(2026, 9, 5, 15, 0, 5, tzinfo=timezone.utc)
    for now in (before_open, first_bar_open, after_bell, saturday):
        assert asyncio.run(_sweep(repository, market, now).run_once()) == 0
    assert repository.list_calls == 0
    assert market.execution_capture_calls == 0


def test_bar_closes_are_aligned_to_the_open_and_wait_out_the_grace() -> None:
    assert latest_bar_close(datetime(2026, 9, 2, 13, 33, 1, tzinfo=timezone.utc)) is None
    assert latest_bar_close(datetime(2026, 9, 2, 13, 33, 2, tzinfo=timezone.utc)) == datetime(
        2026, 9, 2, 13, 33, tzinfo=timezone.utc
    )
    assert latest_bar_close(datetime(2026, 9, 2, 14, 32, 59, tzinfo=timezone.utc)) == EXIT_SIGNAL_AT


def test_the_sweep_follows_the_market_calendar() -> None:
    # The day after Thanksgiving closes at 13:00 ET (18:00 UTC); an ordinary day runs on.
    assert latest_bar_close(datetime(2026, 11, 27, 17, 57, 2, tzinfo=timezone.utc)) == datetime(
        2026, 11, 27, 17, 57, tzinfo=timezone.utc
    )
    assert latest_bar_close(datetime(2026, 11, 27, 18, 3, 2, tzinfo=timezone.utc)) is None
    assert latest_bar_close(datetime(2026, 11, 25, 18, 3, 2, tzinfo=timezone.utc)) == datetime(
        2026, 11, 25, 18, 3, tzinfo=timezone.utc
    )
    # Thanksgiving itself has no session.
    assert latest_bar_close(datetime(2026, 11, 26, 15, 0, 2, tzinfo=timezone.utc)) is None


def test_the_session_history_keys_entries_and_actions_as_the_pass_does() -> None:
    def event(instrument, event_type, action=None):
        return SimpleNamespace(
            instrument_id=instrument,
            event_type=event_type,
            observed_at=FORCE_FLAT_AT,
            payload={} if action is None else {"action": action},
        )

    history = stoch_session_history([
        event("A", "stoch_trend_capture_entry"),
        event("A", "stoch_trend_execution", "partial_exit"),  # a runner is still held
        event("B", "stoch_trend_capture_entry"),
        event("B", "stoch_trend_execution", "range_exit"),
        event("C", "stoch_trend_capture_entry"),
        event("C", "stoch_trend_execution", "force_flat"),
        event("D", "stoch_trend_execution", "runner_exit"),  # no entry this session
    ])
    assert history.open_positions == {"A"}
    assert ("A", FORCE_FLAT_AT.isoformat()) in history.entry_signals
    assert ("C", "force_flat", FORCE_FLAT_AT.isoformat()) in history.actions


def test_the_pass_keeps_a_live_line_while_the_arm_is_armed_or_holding(monkeypatch) -> None:
    demand = HeldQuoteDemand()
    monkeypatch.setattr(monitor_module, "default_held_quote_demand", lambda: demand)
    hold = strategy_monitor_candidates.hold_stoch_quote_line
    assert hold(_runner(state="range_active"), "A", now=FORCE_FLAT_AT)
    assert hold(_runner(state="setup_armed"), "B", now=FORCE_FLAT_AT)
    assert not hold(_runner(state="waiting_oversold"), "C", now=FORCE_FLAT_AT)
    assert not hold(_force_flat(), "D", now=FORCE_FLAT_AT)
    assert demand.current(now=FORCE_FLAT_AT) == {"A", "B"}
