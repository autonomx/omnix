from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.trading.strategy_ai_shadow import (
    AIShadowDecision,
    AIShadowPositionState,
    AIShadowResult,
)
from app.trading.strategy_ai_shadow_monitor import TradingAIShadowMonitor
from app.trading.strategy_managed_finviz_shadow import managed_finviz_shadow_document
from app.trading.strategy_repository import StrategyEvent


INSTRUMENT = "equity:NASDAQ:TEST"
START = datetime(2026, 9, 3, 14, 0, tzinfo=timezone.utc)


class MemoryRepository:
    def __init__(self) -> None:
        self.events = []

    def append_event(self, event):
        if any(existing.idempotency_key == event.idempotency_key for existing in self.events):
            return False
        self.events.append(event)
        return True


class RecordingAnalyzer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict[str, object]]]] = []

    def assess(self, *, policy, rows):
        self.calls.append((policy, rows))
        decisions = tuple(
            AIShadowDecision(
                instrument_id=str(row["instrument_id"]),
                action="skip",
                confidence=70,
                market_regime="unresolved",
                expected_horizon_minutes=30,
                thesis="No confirmed long setup yet.",
                reason="Remain flat until the thesis materially improves.",
                invalidation_price=None,
            )
            for row in rows
        )
        return AIShadowResult(
            policy=policy,
            decisions=decisions,
            provider="fixture",
            model="fixture-ai",
            input_tokens=100,
            output_tokens=25,
            total_tokens=125,
            usage_source="provider",
        )


class FailingAnalyzer:
    def __init__(self) -> None:
        self.calls = 0

    def assess(self, *, policy, rows):
        del policy, rows
        self.calls += 1
        raise RuntimeError("fixture invalid json")


def _feature(price: str = "10") -> dict[str, object]:
    return {
        "deterministic": {"state": "second_pullback"},
        "learning": {"pattern": "unresolved"},
        "market": {
            "current_price": price,
            "session_vwap": "10.2",
            "session_high": "11",
            "current_volume_ratio_to_prior10": "1.0",
        },
        "execution": {
            "spread_bps": "40",
            "execution_eligible": True,
            "halted": False,
        },
        "indicators": {
            "one_minute": {
                "stochastic_rsi_k": "50",
                "stochastic_rsi_d": "50",
                "ema9_rising": True,
            }
        },
        "position": {
            "normalized_units": "0",
            "average_cost": None,
            "unrealized_pct": None,
        },
    }


def _row(
    observed_at: datetime,
    feature: dict[str, object],
    *,
    instrument_id: str = INSTRUMENT,
) -> dict[str, object]:
    candidate = SimpleNamespace(
        instrument_id=instrument_id,
        binding_id=f"alpaca:{instrument_id.rsplit(':', 1)[-1]}",
    )
    return {
        "candidate": candidate,
        "observed_at": observed_at,
        "feature_snapshot": feature,
        "universe_id": "finviz-top5-test",
        "bars": [],
        "learning": SimpleNamespace(current_price=10),
    }


def test_minute_policy_runs_each_new_bar_but_event_policy_requires_change() -> None:
    repository = MemoryRepository()
    analyzer = RecordingAnalyzer()
    monitor = TradingAIShadowMonitor(
        analyzer_factory=lambda: analyzer,
        interval_seconds=5,
    )
    config = managed_finviz_shadow_document("shadow-account")
    events = []
    market_service = object()

    first = _row(START, _feature())
    asyncio.run(
        monitor._run_policy(
            policy="minute",
            rows=[first],
            config=config,
            repository=repository,
            market_service=market_service,
            events=events,
        )
    )
    asyncio.run(
        monitor._run_policy(
            policy="event",
            rows=[first],
            config=config,
            repository=repository,
            market_service=market_service,
            events=events,
        )
    )

    second = _row(START + timedelta(minutes=1), _feature())
    asyncio.run(
        monitor._run_policy(
            policy="minute",
            rows=[second],
            config=config,
            repository=repository,
            market_service=market_service,
            events=events,
        )
    )
    asyncio.run(
        monitor._run_policy(
            policy="event",
            rows=[second],
            config=config,
            repository=repository,
            market_service=market_service,
            events=events,
        )
    )

    policies = [policy for policy, _ in analyzer.calls]
    assert policies == ["minute", "event", "minute"]
    minute_decisions = [
        event
        for event in repository.events
        if event.event_type == "ai_shadow_decision"
        and event.payload["policy"] == "minute"
    ]
    event_decisions = [
        event
        for event in repository.events
        if event.event_type == "ai_shadow_decision"
        and event.payload["policy"] == "event"
    ]
    assert len(minute_decisions) == 2
    assert len(event_decisions) == 1
    assert all(event.payload["execution_authority"] is False for event in minute_decisions)
    assert all(event.payload["execution_authority"] is False for event in event_decisions)
    assert monitor.minute_llm_call_count == 2
    assert monitor.event_llm_call_count == 1
    assert monitor.total_token_count == 375
    assert not any(event.event_type == "entry_order_submitted" for event in repository.events)


def test_flat_ai_arm_stops_calling_after_entry_window_closes() -> None:
    repository = MemoryRepository()
    analyzer = RecordingAnalyzer()
    monitor = TradingAIShadowMonitor(
        analyzer_factory=lambda: analyzer,
        interval_seconds=5,
    )
    config = managed_finviz_shadow_document("shadow-account")
    # 16:00 UTC is 12:00 ET in September, after the 11:30 ET entry cutoff.
    row = _row(START + timedelta(hours=2), _feature())

    asyncio.run(
        monitor._run_policy(
            policy="minute",
            rows=[row],
            config=config,
            repository=repository,
            market_service=object(),
            events=[],
        )
    )

    assert analyzer.calls == []
    assert repository.events == []


def test_one_trade_per_symbol_stops_flat_reentry_calls() -> None:
    repository = MemoryRepository()
    analyzer = RecordingAnalyzer()
    monitor = TradingAIShadowMonitor(
        analyzer_factory=lambda: analyzer,
        interval_seconds=5,
    )
    config = managed_finviz_shadow_document("shadow-account")
    closed = StrategyEvent(
        strategy_id=config.strategy_id,
        event_id="closed-trade",
        run_id="fixture",
        instrument_id=INSTRUMENT,
        event_type="ai_shadow_trade",
        state="closed",
        reason_code="AI_SHADOW_TRADE_CLOSED",
        observed_at=START,
        idempotency_key="closed-trade",
        payload={
            "policy": "minute",
            "trade_id": "trade-1",
            "execution_authority": False,
        },
    )

    asyncio.run(
        monitor._run_policy(
            policy="minute",
            rows=[_row(START + timedelta(minutes=5), _feature())],
            config=config,
            repository=repository,
            market_service=object(),
            events=[closed],
        )
    )

    assert config.risk.one_trade_per_symbol_per_day is True
    assert analyzer.calls == []
    assert repository.events == []


def test_one_trade_cap_survives_missing_trade_summary_if_closing_fill_persisted() -> None:
    repository = MemoryRepository()
    analyzer = RecordingAnalyzer()
    monitor = TradingAIShadowMonitor(
        analyzer_factory=lambda: analyzer,
        interval_seconds=5,
    )
    config = managed_finviz_shadow_document("shadow-account")
    flat = AIShadowPositionState(policy="minute", instrument_id=INSTRUMENT)
    closing_fill = StrategyEvent(
        strategy_id=config.strategy_id,
        event_id="closing-fill",
        run_id="fixture",
        instrument_id=INSTRUMENT,
        event_type="ai_shadow_fill",
        state="filled",
        reason_code="AI_SHADOW_FILL_SIMULATED",
        observed_at=START,
        idempotency_key="closing-fill",
        payload={
            "policy": "minute",
            "trade_id": "trade-1",
            "position_after": flat.model_dump(mode="json"),
            "closed_position": {
                **flat.model_dump(mode="json"),
                "trade_id": "trade-1",
            },
            "execution_authority": False,
        },
    )

    asyncio.run(
        monitor._run_policy(
            policy="minute",
            rows=[_row(START + timedelta(minutes=5), _feature())],
            config=config,
            repository=repository,
            market_service=object(),
            events=[closing_fill],
        )
    )

    assert analyzer.calls == []
    assert repository.events == []


def _open_position_fill(config, instrument_id: str, trade_id: str) -> StrategyEvent:
    position = AIShadowPositionState(
        policy="minute",
        instrument_id=instrument_id,
        normalized_units=Decimal("1"),
        average_cost=Decimal("10"),
        trade_id=trade_id,
        entry_time=START,
        first_entry_price=Decimal("10"),
        total_buy_notional=Decimal("10"),
        total_reference_buy_notional=Decimal("10"),
        fill_count=1,
    )
    return StrategyEvent(
        strategy_id=config.strategy_id,
        event_id=f"fill-{trade_id}",
        run_id="fixture",
        instrument_id=instrument_id,
        event_type="ai_shadow_fill",
        state="filled",
        reason_code="AI_SHADOW_FILL_SIMULATED",
        observed_at=START,
        idempotency_key=f"fill-{trade_id}",
        payload={
            "policy": "minute",
            "trade_id": trade_id,
            "side": "buy",
            "position_after": position.model_dump(mode="json"),
            "closed_position": None,
            "execution_authority": False,
        },
    )


def test_max_positions_blocks_new_ai_shadow_entry_before_execution_call() -> None:
    repository = MemoryRepository()
    monitor = TradingAIShadowMonitor(interval_seconds=5)
    config = managed_finviz_shadow_document("shadow-account")
    events = [
        _open_position_fill(config, f"equity:NASDAQ:OPEN{index}", f"trade-{index}")
        for index in range(config.risk.max_positions)
    ]
    row = _row(START, _feature())
    decision = AIShadowDecision(
        instrument_id=INSTRUMENT,
        action="enter",
        confidence=90,
        market_regime="trend_continuation",
        expected_horizon_minutes=60,
        thesis="Strong trend.",
        reason="Momentum remains constructive.",
        invalidation_price=Decimal("9.50"),
    )

    asyncio.run(
        monitor._apply_decision(
            policy="minute",
            decision=decision,
            row=row,
            candidate=row["candidate"],
            bars=[],
            config=config,
            repository=repository,
            market_service=object(),
            events=events,
            result=SimpleNamespace(current_price=Decimal("10")),
            batch_result=None,
            trigger_reasons=("completed_1m_bar",),
        )
    )

    persisted = repository.events
    assert len(persisted) == 1
    assert persisted[0].event_type == "ai_shadow_decision"
    assert persisted[0].payload["effective_action"] == "skip"
    assert "AI_SHADOW_MAX_POSITIONS" in persisted[0].payload["action_normalization_reasons"]


def test_max_trades_per_day_blocks_new_ai_shadow_entry() -> None:
    repository = MemoryRepository()
    monitor = TradingAIShadowMonitor(interval_seconds=5)
    config = managed_finviz_shadow_document("shadow-account")
    events = [
        _open_position_fill(config, f"equity:NASDAQ:TRADE{index}", f"trade-{index}")
        for index in range(config.risk.max_trades_per_day)
    ]
    row = _row(START, _feature())
    decision = AIShadowDecision(
        instrument_id=INSTRUMENT,
        action="enter",
        confidence=90,
        market_regime="trend_continuation",
        expected_horizon_minutes=60,
        thesis="Strong trend.",
        reason="Momentum remains constructive.",
        invalidation_price=Decimal("9.50"),
    )

    asyncio.run(
        monitor._apply_decision(
            policy="minute",
            decision=decision,
            row=row,
            candidate=row["candidate"],
            bars=[],
            config=config,
            repository=repository,
            market_service=object(),
            events=events,
            result=SimpleNamespace(current_price=Decimal("10")),
            batch_result=None,
            trigger_reasons=("completed_1m_bar",),
        )
    )

    assert repository.events[0].payload["effective_action"] == "skip"
    assert "AI_SHADOW_MAX_TRADES_PER_DAY" in repository.events[0].payload["action_normalization_reasons"]


def test_event_policy_reacts_to_material_state_change() -> None:
    repository = MemoryRepository()
    analyzer = RecordingAnalyzer()
    monitor = TradingAIShadowMonitor(
        analyzer_factory=lambda: analyzer,
        interval_seconds=5,
    )
    config = managed_finviz_shadow_document("shadow-account")
    events = []

    first = _row(START, _feature())
    asyncio.run(
        monitor._run_policy(
            policy="event",
            rows=[first],
            config=config,
            repository=repository,
            market_service=object(),
            events=events,
        )
    )

    changed = _feature(price="10.4")
    changed["deterministic"] = {"state": "entry_ready"}
    changed["market"] = {
        **changed["market"],
        "session_vwap": "10.2",
        "session_high": "11.2",
        "current_volume_ratio_to_prior10": "2.0",
    }
    second = _row(START + timedelta(minutes=1), changed)
    asyncio.run(
        monitor._run_policy(
            policy="event",
            rows=[second],
            config=config,
            repository=repository,
            market_service=object(),
            events=events,
        )
    )

    assert [policy for policy, _ in analyzer.calls] == ["event", "event"]
    decisions = [
        event
        for event in repository.events
        if event.event_type == "ai_shadow_decision"
        and event.payload["policy"] == "event"
    ]
    assert len(decisions) == 2
    assert "deterministic_state_changed" in decisions[-1].payload["trigger_reasons"]
    assert "vwap_side_changed" in decisions[-1].payload["trigger_reasons"]


def test_postclose_comparison_preserves_spread_cost_and_data_quality_boundaries() -> None:
    repository = MemoryRepository()
    monitor = TradingAIShadowMonitor(interval_seconds=5)
    config = managed_finviz_shadow_document("shadow-account")
    now = START + timedelta(hours=6)  # 16:00 ET
    events = [
        StrategyEvent(
            strategy_id=config.strategy_id,
            event_id="state-entry",
            run_id="fixture",
            instrument_id=INSTRUMENT,
            event_type="state",
            state="entry_ready",
            reason_code="V2_ENTRY_READY",
            observed_at=START,
            idempotency_key="state-entry",
            payload={},
        ),
        StrategyEvent(
            strategy_id=config.strategy_id,
            event_id="v2-live-execution",
            run_id="fixture",
            instrument_id=INSTRUMENT,
            event_type="shadow_execution",
            state="entry_ready",
            reason_code="SHADOW_EXECUTION_OBSERVED",
            observed_at=START,
            idempotency_key="v2-live-execution",
            payload={
                "strategy_version": "2.0.0",
                "execution": {
                    "execution_eligible": True,
                    "spread_bps": "40",
                },
                "execution_authority": False,
            },
        ),
        StrategyEvent(
            strategy_id=config.strategy_id,
            event_id="v2-replay",
            run_id="fixture",
            instrument_id=INSTRUMENT,
            event_type="v2_shadow_replay_trade",
            state="replayed",
            reason_code="V2_SHADOW_REPLAY_TRADE",
            observed_at=now,
            idempotency_key="v2-replay",
            payload={
                "r_result": "1.0",
                "assumed_spread_bps": "150",
                "execution_authority": False,
            },
        ),
        StrategyEvent(
            strategy_id=config.strategy_id,
            event_id="stoch-summary",
            run_id="fixture",
            instrument_id=INSTRUMENT,
            event_type="stoch_trend_execution_summary",
            state="complete",
            reason_code="STOCH_EXECUTION_NET_RETURN_READY",
            observed_at=now,
            idempotency_key="stoch-summary",
            payload={
                "policy": {
                    "complete": True,
                    "net_execution_return_pct": "2.0",
                    "execution_drag_pct": "0.4",
                },
                "execution_authority": False,
            },
        ),
        StrategyEvent(
            strategy_id=config.strategy_id,
            event_id="minute-batch",
            run_id="fixture",
            instrument_id="__universe__",
            event_type="ai_shadow_batch",
            state="complete",
            reason_code="AI_SHADOW_LLM_BATCH_COMPLETE",
            observed_at=START,
            idempotency_key="minute-batch",
            payload={
                "policy": "minute",
                "total_tokens": 125,
                "execution_authority": False,
            },
        ),
        StrategyEvent(
            strategy_id=config.strategy_id,
            event_id="event-batch-error",
            run_id="fixture",
            instrument_id="__universe__",
            event_type="ai_shadow_batch",
            state="error",
            reason_code="AI_SHADOW_LLM_BATCH_ERROR",
            observed_at=START,
            idempotency_key="event-batch-error",
            payload={
                "policy": "event",
                "execution_authority": False,
            },
        ),
        StrategyEvent(
            strategy_id=config.strategy_id,
            event_id="minute-decision",
            run_id="fixture",
            instrument_id=INSTRUMENT,
            event_type="ai_shadow_decision",
            state="enter",
            reason_code="AI_SHADOW_MINUTE_DECISION",
            observed_at=START,
            idempotency_key="minute-decision",
            payload={
                "policy": "minute",
                "effective_action": "enter",
                "execution_authority": False,
            },
        ),
        StrategyEvent(
            strategy_id=config.strategy_id,
            event_id="minute-trade",
            run_id="fixture",
            instrument_id=INSTRUMENT,
            event_type="ai_shadow_trade",
            state="closed",
            reason_code="AI_SHADOW_TRADE_CLOSED",
            observed_at=now,
            idempotency_key="minute-trade",
            payload={
                "policy": "minute",
                "net_execution_return_pct": "1.5",
                "execution_drag_pct": "0.2",
                "mae_pct": "-0.5",
                "decision_count": 2,
                "action_change_count": 1,
                "decision_stability": "0.5",
                "execution_authority": False,
            },
        ),
        StrategyEvent(
            strategy_id=config.strategy_id,
            event_id="data-gap",
            run_id="fixture",
            instrument_id="equity:NASDAQ:GAP",
            event_type="ai_shadow_data_gap",
            state="unavailable",
            reason_code="AI_SHADOW_MARKET_CONTEXT_UNAVAILABLE",
            observed_at=START,
            idempotency_key="data-gap",
            payload={
                "execution_authority": False,
            },
        ),
    ]

    asyncio.run(
        monitor._comparison_summary(
            config=config,
            repository=repository,
            events=events,
            session_date=START.astimezone(timezone.utc).date(),
            cohort_candidate_count=5,
            now=now,
        )
    )

    comparison = next(
        event
        for event in repository.events
        if event.event_type == "shadow_strategy_comparison"
    ).payload
    quality = comparison["shared_data_quality"]
    arm_a = comparison["arm_a_deterministic_v2"]
    arm_b = comparison["arm_b_stoch_trend"]
    arm_c = comparison["arm_c_ai_every_minute"]
    arm_d = comparison["arm_d_ai_event_driven"]

    assert quality["cohort_candidate_count"] == 5
    assert quality["market_data_gap_event_count"] == 1
    assert quality["symbols_with_market_data_gaps"] == ["equity:NASDAQ:GAP"]
    assert arm_a["mean_live_entry_spread_bps"] == "40"
    assert arm_a["live_execution_eligible_signal_count"] == 1
    assert arm_a["assumed_spread_bps_values"] == ["150"]
    assert arm_a["execution_model"] == "canonical_v2_postclose_replay_with_assumed_spread"
    assert arm_b["mean_net_execution_return_pct"] == "2.0"
    assert arm_c["llm_call_count"] == 1
    assert arm_c["llm_total_tokens"] == 125
    assert arm_c["total_decisions"] == 1
    assert arm_d["llm_error_count"] == 1
    assert comparison["cross_arm_return_units_harmonized"] is False
    assert comparison["cross_arm_execution_models_harmonized"] is False
    assert comparison["ranking_deferred_until_risk_normalized"] is True


def test_ai_shadow_failure_checkpoint_prevents_retries_for_same_market_minute() -> None:
    repository = MemoryRepository()
    analyzer = FailingAnalyzer()
    monitor = TradingAIShadowMonitor(
        analyzer_factory=lambda: analyzer,
        interval_seconds=5,
    )
    config = managed_finviz_shadow_document("shadow-account")
    row = _row(START, _feature())

    asyncio.run(
        monitor._run_policy(
            policy="minute",
            rows=[row],
            config=config,
            repository=repository,
            market_service=object(),
            events=[],
        )
    )
    assert analyzer.calls == 1
    errors = [
        event
        for event in repository.events
        if event.event_type == "ai_shadow_batch"
        and event.state == "error"
    ]
    assert len(errors) == 1

    asyncio.run(
        monitor._run_policy(
            policy="minute",
            rows=[row],
            config=config,
            repository=repository,
            market_service=object(),
            events=list(repository.events),
        )
    )
    assert analyzer.calls == 1

    next_row = _row(START + timedelta(minutes=1), _feature("10.1"))
    asyncio.run(
        monitor._run_policy(
            policy="minute",
            rows=[next_row],
            config=config,
            repository=repository,
            market_service=object(),
            events=list(repository.events),
        )
    )
    assert analyzer.calls == 2


def test_same_max_minute_allows_late_symbol_request_signature() -> None:
    repository = MemoryRepository()
    analyzer = RecordingAnalyzer()
    monitor = TradingAIShadowMonitor(
        analyzer_factory=lambda: analyzer,
        interval_seconds=5,
    )
    config = managed_finviz_shadow_document("shadow-account")
    instrument_a = "equity:NASDAQ:A"
    instrument_b = "equity:NASDAQ:B"
    minute_one = START + timedelta(minutes=1)

    asyncio.run(
        monitor._run_policy(
            policy="minute",
            rows=[
                _row(minute_one, _feature("10.1"), instrument_id=instrument_a),
                _row(START, _feature("9.9"), instrument_id=instrument_b),
            ],
            config=config,
            repository=repository,
            market_service=object(),
            events=[],
        )
    )
    assert len(analyzer.calls) == 1

    asyncio.run(
        monitor._run_policy(
            policy="minute",
            rows=[
                _row(minute_one, _feature("10.0"), instrument_id=instrument_b),
            ],
            config=config,
            repository=repository,
            market_service=object(),
            events=list(repository.events),
        )
    )

    assert len(analyzer.calls) == 2
    assert [
        row["instrument_id"] for row in analyzer.calls[1][1]
    ] == [instrument_b]
    batches = [
        event
        for event in repository.events
        if event.event_type == "ai_shadow_batch"
        and event.state == "complete"
        and event.payload.get("policy") == "minute"
    ]
    assert len(batches) == 2
    assert batches[0].observed_at == batches[1].observed_at == minute_one
    assert batches[0].payload["request_signature"] != batches[1].payload["request_signature"]
    assert batches[1].payload["requested_instrument_ids"] == [instrument_b]
