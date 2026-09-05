from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.trading.models import MarketBar
from app.trading.strategy_solana_ai import (
    SOLANA_INSTRUMENT_ID,
    SolanaAIDecision,
    SolanaAIAnalyzer,
)
from app.trading.strategy_solana_ai_monitor import (
    TradingSolanaAIMonitor,
    create_trading_solana_ai_control_router,
)


START = datetime(2026, 9, 4, 20, 0, tzinfo=timezone.utc)


def _bars() -> list[MarketBar]:
    return [
        MarketBar(
            instrument_id=SOLANA_INSTRUMENT_ID,
            interval="1m",
            start_time=START + timedelta(minutes=index),
            end_time=START + timedelta(minutes=index + 1),
            open=Decimal(str(145 + index)),
            high=Decimal(str(146 + index)),
            low=Decimal(str(144 + index)),
            close=Decimal(str("145.5") if index == 0 else "146.5"),
            volume=Decimal("1000"),
            is_final=True,
            session="24x7",
            provider="fixture",
        )
        for index in range(3)
    ]


class FixtureProvider:
    provider_name = "fixture-ai"
    config = SimpleNamespace(model="fixture-model")

    def __init__(self) -> None:
        self.messages = []

    def chat_completion(self, **kwargs):
        self.messages.append(kwargs["messages"])
        return SimpleNamespace(
            content=(
                '{"decision":{"instrument_id":"crypto:BINANCE:spot:SOL-USDT",'
                '"action":"skip","confidence":72,"market_regime":"unclear",'
                '"expected_horizon_minutes":5,"thesis":"Insufficient evidence.",'
                '"reason":"Wait for a clearer causal move.","invalidation_price":null,'
                '"execution_authority":false}}'
            ),
            usage={"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
            model="fixture-model",
        )


def test_solana_ai_analyzer_requires_exact_shadow_decision() -> None:
    provider = FixtureProvider()
    result = SolanaAIAnalyzer(provider_factory=lambda: provider).assess(
        bars=_bars(),
        observed_at=START + timedelta(minutes=3),
        quote={"price": "147.5"},
    )

    assert result.decision.action == "skip"
    assert result.decision.execution_authority is False
    assert result.provider == "fixture-ai"
    assert result.total_tokens == 130
    assert "completed_1m_candles" in provider.messages[0][1].content
    assert "deterministic" not in provider.messages[0][1].content


class FixtureMarket:
    def __init__(self, bars: list[MarketBar]) -> None:
        self.bars_result = SimpleNamespace(bars=bars)
        self.bar_calls = 0

    def bars(self, instrument_id, interval, limit, binding_id):
        assert instrument_id == SOLANA_INSTRUMENT_ID
        assert interval == "1m"
        assert limit == 120
        assert binding_id
        self.bar_calls += 1
        return self.bars_result

    def quote(self, instrument_id, binding_id):
        return {
            "instrument_id": instrument_id,
            "binding_id": binding_id,
            "price": "147.5",
        }


class FixtureAnalyzer:
    def __init__(self) -> None:
        self.calls = 0

    def assess(self, **kwargs):
        self.calls += 1
        assert kwargs["bars"]
        return SimpleNamespace(
            decision=SolanaAIDecision(
                action="hold",
                confidence=60,
                market_regime="trend_up",
                expected_horizon_minutes=5,
                thesis="Hold the observation state.",
                reason="Fixture decision.",
            ),
            provider="fixture-ai",
            model="fixture-model",
            input_characters=10,
            output_characters=10,
            input_tokens=2,
            output_tokens=2,
            total_tokens=4,
            usage_source="provider",
        )


def test_solana_ai_monitor_processes_each_completed_candle_once() -> None:
    market = FixtureMarket(_bars())
    analyzer = FixtureAnalyzer()
    monitor = TradingSolanaAIMonitor(
        market_service_factory=lambda: market,
        analyzer_factory=lambda: analyzer,
        now_factory=lambda: START + timedelta(minutes=3, seconds=5),
        interval_seconds=2,
    )

    import asyncio

    assert asyncio.run(monitor.run_once()) == 1
    assert asyncio.run(monitor.run_once()) == 0
    assert market.bar_calls == 2
    assert analyzer.calls == 1
    assert monitor.ai_call_count == 1
    assert monitor.decision_count == 1
    assert monitor.signal_count == 0
    assert monitor.last_error is None


def test_solana_ai_monitor_control_router_stops_only_registered_monitor() -> None:
    app = FastAPI()
    monitor = TradingSolanaAIMonitor()
    app.state._omnix_trading_solana_ai_monitor = monitor
    app.include_router(create_trading_solana_ai_control_router())

    response = TestClient(app).post("/api/trading/solana-ai/stop")

    assert response.status_code == 202
    assert response.json()["status"] == "stopped"
    assert response.json()["execution_authority"] is False
    assert monitor._task is None

class FixtureStrategyRepository:
    def __init__(self) -> None:
        self.events = []
        self.ensure_calls = 0

    def ensure_strategy(self, *, enabled: bool) -> None:
        assert isinstance(enabled, bool)
        self.ensure_calls += 1

    def append_decision(self, event, *, enabled: bool):
        assert isinstance(enabled, bool)
        self.events.append(event)
        return True

    def recent_decisions(self, *, limit: int = 200):
        return list(reversed(self.events[-limit:]))

    def decision_counts(self):
        signals = sum(event.state in {"enter_long", "exit_long"} for event in self.events)
        return (len(self.events), signals)


def test_solana_ai_monitor_persists_strategy_decision_history() -> None:
    market = FixtureMarket(_bars())
    analyzer = FixtureAnalyzer()
    repository = FixtureStrategyRepository()
    monitor = TradingSolanaAIMonitor(
        market_service_factory=lambda: market,
        analyzer_factory=lambda: analyzer,
        strategy_repository_factory=lambda: repository,
        now_factory=lambda: START + timedelta(minutes=3, seconds=5),
        interval_seconds=2,
    )

    import asyncio

    assert asyncio.run(monitor.run_once()) == 1
    assert len(repository.events) == 1
    event = repository.events[0]
    assert event.strategy_id == "solana-ai-1m-shadow"
    assert event.event_type == "solana_ai_decision"
    assert event.state == "hold"
    assert event.payload["execution_authority"] is False
    assert monitor.recent_decisions()[0].event_id == event.event_id



class FailOnceStrategyRepository(FixtureStrategyRepository):
    def __init__(self) -> None:
        super().__init__()
        self.failures_remaining = 1

    def append_decision(self, event, *, enabled: bool):
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise RuntimeError("database unavailable")
        return super().append_decision(event, enabled=enabled)


def test_solana_ai_persistence_failure_keeps_completed_bar_retryable() -> None:
    market = FixtureMarket(_bars())
    analyzer = FixtureAnalyzer()
    repository = FailOnceStrategyRepository()
    monitor = TradingSolanaAIMonitor(
        market_service_factory=lambda: market,
        analyzer_factory=lambda: analyzer,
        strategy_repository_factory=lambda: repository,
        now_factory=lambda: START + timedelta(minutes=3, seconds=5),
        interval_seconds=2,
    )

    import asyncio

    assert asyncio.run(monitor.run_once()) == 0
    assert monitor.last_decision is None
    assert monitor.decision_count == 0
    assert monitor._last_processed_bar_end is None
    assert "database unavailable" in str(monitor.last_error)

    assert asyncio.run(monitor.run_once()) == 1
    assert monitor.last_decision is not None
    assert monitor.decision_count == 1
    assert monitor._last_processed_bar_end == START + timedelta(minutes=3)
    assert analyzer.calls == 2
    assert len(repository.events) == 1
