from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.trading import strategy_stoch_rsi_5m as stoch_module
from app.trading.models import MarketBar
from app.trading.strategy_monitor import TradingStrategyMonitor
from app.trading.strategy_repository import StrategyEvent, TradingStrategyConfigDocument
from app.trading.strategies.models import StochRsi5mConfig


INSTRUMENT = "equity:NASDAQ:TEST"
SESSION_DATE = date(2026, 9, 10)
START = datetime(2026, 9, 10, 13, 30, tzinfo=timezone.utc)
HISTORY_START = datetime(2026, 9, 9, 13, 30, tzinfo=timezone.utc)


class MemoryRepository:
    def __init__(self) -> None:
        self.events: list[StrategyEvent] = []

    def append_event(self, event: StrategyEvent) -> bool:
        if any(item.idempotency_key == event.idempotency_key for item in self.events):
            return False
        self.events.append(event)
        return True

    def get_universe(self, universe_id: str):
        assert universe_id == "stoch-universe"
        return _universe()


class FixtureMarketService:
    def __init__(self) -> None:
        self.calls = 0

    def bars(self, instrument_id, interval, limit, binding_id):
        assert instrument_id == INSTRUMENT
        assert interval == "5m"
        assert limit == 500
        self.calls += 1
        bars = []
        for index in range(60):
            start = (
                HISTORY_START + timedelta(minutes=5 * index)
                if index < 50
                else START + timedelta(minutes=5 * (index - 50))
            )
            bars.append(
                MarketBar(
                    instrument_id=INSTRUMENT,
                    interval="5m",
                    start_time=start,
                    end_time=start + timedelta(minutes=5),
                    open=Decimal("10"),
                    high=Decimal("10"),
                    low=Decimal("10"),
                    close=Decimal("10"),
                    volume=Decimal("1000"),
                    session="regular",
                    provider="fixture",
                    received_at=start + timedelta(minutes=5),
                )
            )
        return SimpleNamespace(
            bars=bars,
            provenance=SimpleNamespace(
                resolved_binding=binding_id,
                dataset_fingerprint="fixture-5m",
                as_of=bars[-1].end_time,
            ),
        )


def _universe():
    return SimpleNamespace(
        universe_id="stoch-universe",
        session_date=SESSION_DATE,
        discovery_source="manual",
        candidates=[
            SimpleNamespace(
                instrument_id=INSTRUMENT,
                binding_id="fixture:TEST",
                market_data_complete=True,
            )
        ],
    )


def _config(*, mode: str = "shadow") -> TradingStrategyConfigDocument:
    config = StochRsi5mConfig()
    return TradingStrategyConfigDocument(
        strategy_id="stoch-rsi-5min",
        account_id="paper-test",
        strategy_kind="stoch_rsi_5m_v1",
        strategy_version="1.0.0",
        mode=mode,
        active_universe_id="stoch-universe",
        config=config,
    )


def test_strategy_document_is_shadow_only() -> None:
    with pytest.raises(ValueError, match="stoch_rsi_5m_is_shadow_only"):
        _config(mode="auto_paper")


def test_monitor_persists_stoch_rsi_evidence_without_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        stoch_module,
        "_stochastic_rsi_aligned",
        lambda values, **kwargs: (
            [Decimal("50")] * (len(values) - 2) + [Decimal("5"), Decimal("9")],
            [Decimal("50")] * (len(values) - 2) + [Decimal("8"), Decimal("7")],
        ),
    )
    repository = MemoryRepository()
    market = FixtureMarketService()
    monitor = TradingStrategyMonitor(interval_seconds=30)
    monitor.current_run_id = "stoch-test-run"

    asyncio.run(
        monitor._run_stoch_rsi_5m_config(
            _config(),
            repository,
            market,
            now_utc=datetime(2026, 9, 10, 13, 45, tzinfo=timezone.utc),
        )
    )

    assert market.calls == 1
    assert len(repository.events) == 1
    event = repository.events[0]
    assert event.event_type == "stoch_rsi_5m"
    assert event.state == "entry_armed"
    assert event.payload["execution_authority"] is False
    assert event.payload["research_only"] is True
