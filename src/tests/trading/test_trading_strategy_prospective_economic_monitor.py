from __future__ import annotations

import asyncio
import hashlib
import inspect
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.trading.models import MarketBar
from app.trading.strategy_deep_recovery import DEEP_RECOVERY_RULE_VERSION, DEEP_RECOVERY_SETUP_ID
from app.trading.strategy_prospective_economic_monitor import TradingStrategyProspectiveEconomicMonitor
from app.trading.strategy_repository import StrategyEvent, TradingStrategyConfigDocument
from app.trading.strategy_v2_qualification import frozen_v2_config, v2_profile_fingerprint


INSTRUMENT = "equity:NASDAQ:ECON"
ENTRY = datetime(2026, 8, 24, 14, 0, 30, tzinfo=timezone.utc)
NOW = ENTRY + timedelta(minutes=70)


def _bar(index: int) -> MarketBar:
    start = ENTRY.replace(second=0, microsecond=0) + timedelta(minutes=index)
    high = Decimal("11.10") if index == 10 else Decimal("10.40")
    return MarketBar(
        instrument_id=INSTRUMENT,
        interval="1m",
        start_time=start,
        end_time=start + timedelta(minutes=1),
        open=Decimal("10.10"),
        high=high,
        low=Decimal("9.50"),
        close=Decimal("10.20"),
        volume=Decimal("1000"),
        is_final=True,
        session="regular",
        provider="fixture",
        received_at=start + timedelta(minutes=1),
    )


def _source_event(config) -> StrategyEvent:
    idem = hashlib.sha256(b"deep-recovery-source").hexdigest()
    return StrategyEvent(
        strategy_id="strategy-1",
        event_id=idem[:32],
        instrument_id=INSTRUMENT,
        event_type="deep_recovery_shadow",
        state="signal_ready",
        reason_code="DEEP_RECOVERY_SIGNAL_READY",
        observed_at=ENTRY,
        idempotency_key=idem,
        payload={
            "setup_id": DEEP_RECOVERY_SETUP_ID,
            "rule_version": DEEP_RECOVERY_RULE_VERSION,
            "profile_fingerprint": v2_profile_fingerprint(config),
            "evaluation": {"research_stop_price": "9.00"},
            "execution": {
                "instrument_id": INSTRUMENT,
                "binding_id": "fixture:ECON",
                "provider": "alpaca-iex-fixture",
                "source_time": ENTRY.isoformat(),
                "ask": "10.00",
                "last": "9.99",
                "spread_bps": "20",
                "execution_eligible": True,
                "halted": False,
                "prospective_signal_features": {"immutable_fingerprint": "a" * 64},
            },
            "execution_authority": False,
        },
    )


class FakeRepository:
    def __init__(self) -> None:
        config = frozen_v2_config()
        self.configs = [TradingStrategyConfigDocument(
            strategy_id="strategy-1",
            account_id="paper-1",
            strategy_version="2.0.0",
            mode="shadow",
            config=config,
            enabled=True,
        )]
        self.events: list[StrategyEvent] = [_source_event(config)]

    def list_configs(self, *, active_only: bool = False):
        return list(self.configs)

    def events_by_types_between(self, strategy_id: str, *, event_types, start_time, end_time, limit=50000):
        return [
            event for event in self.events
            if event.strategy_id == strategy_id
            and event.event_type in event_types
            and start_time <= event.observed_at < end_time
        ][:limit]

    def append_event(self, event: StrategyEvent) -> bool:
        if any(existing.idempotency_key == event.idempotency_key for existing in self.events):
            return False
        self.events.append(event)
        return True


class FakeMarketService:
    def bars(self, instrument_id: str, interval: str, limit: int, binding_id: str | None):
        assert instrument_id == INSTRUMENT
        assert interval == "1m"
        assert limit == 500
        assert binding_id == "fixture:ECON"
        # Includes the first finalized 1m bar closing after the exact 60-minute
        # horizon (15:00:30 -> 15:01:00), which is required for causal closure.
        return SimpleNamespace(bars=[_bar(index) for index in range(62)])


def test_prospective_economic_monitor_is_structurally_orderless() -> None:
    import app.trading.strategy_prospective_economic_monitor as module

    source = inspect.getsource(module)
    assert "TradingPaperRepository" not in source
    assert "PaperOrderRequest" not in source
    assert "place_order" not in source


def test_monitor_captures_signal_and_uses_first_finalized_bar_after_60m_horizon() -> None:
    repository = FakeRepository()
    monitor = TradingStrategyProspectiveEconomicMonitor(
        strategy_repository_factory=lambda: repository,
        market_service_factory=lambda: FakeMarketService(),
        now_factory=lambda: NOW,
        interval_seconds=30,
    )

    captured = asyncio.run(monitor.run_once())

    assert captured == 2
    signals = [event for event in repository.events if event.event_type == "prospective_economic_signal"]
    outcomes = [event for event in repository.events if event.event_type == "prospective_economic_outcome"]
    assert len(signals) == 1
    assert len(outcomes) == 1
    signal = signals[0]
    outcome = outcomes[0]
    assert signal.payload["entry_price"] == "10.00"
    assert signal.payload["stop_price"] == "9.00"
    assert signal.payload["risk_per_share"] == "1.00"
    assert signal.payload["execution_authority"] is False
    assert outcome.payload["data_complete"] is True
    assert outcome.payload["one_r_before_minus_one_r"] is True
    assert outcome.payload["first_passage_1r"] == "target"
    assert outcome.payload["r_result_60m"] == "1"
    assert outcome.payload["execution_authority"] is False
    assert asyncio.run(monitor.run_once()) == 0
