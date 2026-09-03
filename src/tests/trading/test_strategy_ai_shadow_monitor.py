from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.trading.strategy_ai_shadow import (
    AIShadowDecision,
    AIShadowResult,
)
from app.trading.strategy_ai_shadow_monitor import TradingAIShadowMonitor
from app.trading.strategy_managed_finviz_shadow import managed_finviz_shadow_document


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


def _row(observed_at: datetime, feature: dict[str, object]) -> dict[str, object]:
    candidate = SimpleNamespace(
        instrument_id=INSTRUMENT,
        binding_id="alpaca:TEST",
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
