from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.trading.gapper_dataset import GapperCandidate, freeze_gapper_universe
from app.trading.strategies.models import GapPullbackConfig, GapPullbackFeatures, GapPullbackResult, StrategySignal
from app.trading.strategy_monitor import TradingStrategyMonitor
from app.trading.strategy_repository import TradingStrategyConfigDocument
from app.trading.strategy_intraday_learning import IntradayLearningSnapshot
from app.trading.strategy_intraday_llm import (
    IntradayLLMAssessment,
    IntradayLLMAnalyzer,
    IntradayLLMResult,
    build_intraday_llm_payload,
    select_intraday_llm_candidates,
    should_run_intraday_llm_batch,
)


OBSERVED = datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc)


def candidate(symbol: str, rank: int) -> GapperCandidate:
    return GapperCandidate(
        instrument_id=f"equity:NASDAQ:{symbol}",
        previous_close=Decimal("8"),
        premarket_price=Decimal("10"),
        gap_pct=Decimal("25"),
        premarket_volume=Decimal("500000"),
        premarket_dollar_volume=Decimal("5000000"),
        tod_rvol=Decimal("5"),
        float_shares=Decimal("2000000"),
        spread_bps=Decimal("40"),
        catalyst_evidence_ids=("ev-1",),
        dilution_flags=(),
        discovery_rank=rank,
    )


def result(symbol: str, *, state: str = "higher_low_confirmed") -> GapPullbackResult:
    signal = None
    if state == "entry_ready":
        signal = StrategySignal(
            instrument_id=f"equity:NASDAQ:{symbol}",
            state="entry_ready",
            entry_price=Decimal("11"),
            stop_price=Decimal("10"),
            target_price=Decimal("13"),
            risk_per_share=Decimal("1"),
            reason_code="ENTRY_READY",
            quality_score=8,
        )
    return GapPullbackResult(
        instrument_id=f"equity:NASDAQ:{symbol}",
        state=state,
        reason_code="WAITING" if signal is None else "ENTRY_READY",
        features=GapPullbackFeatures(
            gap_pct=Decimal("25"),
            session_vwap=Decimal("10.4"),
            float_shares=Decimal("2000000"),
            quality_score=8,
        ),
        transitions=("discovered", "qualified_gap", "higher_low_confirmed"),
        signal=signal,
        evaluated_bar_count=30,
    )


def learning(*, opportunity: int = 8, pattern: str = "failed_selloff_watch") -> IntradayLearningSnapshot:
    return IntradayLearningSnapshot(
        catalyst_quality_score=8,
        supply_risk_score=3,
        float_structure_risk_score=7,
        extension_risk_score=2,
        squeeze_probability_score=7,
        failed_selloff_probability_score=8,
        trend_continuation_score=6,
        gap_retention_score=8,
        execution_quality_score=9,
        opportunity_score=opportunity,
        pattern=pattern,
        current_price=Decimal("10.8"),
        session_open=Decimal("10"),
        session_high=Decimal("11"),
        session_low=Decimal("9.5"),
        session_vwap=Decimal("10.4"),
        close_location=Decimal("0.8667"),
        gap_retention_ratio=Decimal("0.9"),
        turnover_to_float=Decimal("2.4"),
        current_vs_premarket_pct=Decimal("8"),
        session_return_pct=Decimal("8"),
        deterministic_state="higher_low_confirmed",
        deterministic_reason_code="WAITING",
        execution_authority=False,
    )


def row(symbol: str, rank: int, *, state: str = "higher_low_confirmed", opportunity: int = 8):
    return (candidate(symbol, rank), result(symbol, state=state), OBSERVED, learning(opportunity=opportunity))


class FakeProvider:
    provider_name = "fixture"

    def __init__(self, payload):
        self.payload = payload
        self.config = SimpleNamespace(model="fixture-model")
        self.messages = None

    def chat_completion(self, *, messages, model=None, stream=False, **kwargs):
        self.messages = messages
        return SimpleNamespace(content=json.dumps(self.payload), model=model or "fixture-model")


def assessment(instrument_id: str):
    return {
        "instrument_id": instrument_id,
        "market_regime": "failed_selloff",
        "squeeze_probability": 62,
        "failed_selloff_probability": 81,
        "trend_continuation_probability": 58,
        "distribution_probability": 24,
        "confidence": 78,
        "thesis_change": "strengthened",
        "summary": "Recovery evidence strengthened while price remains above VWAP.",
        "bull_case": "Higher lows and gap retention support continued recovery.",
        "bear_case": "A VWAP loss with expanding sell pressure would weaken the recovery.",
        "what_would_change_my_mind": "Sustained acceptance below VWAP and failure of the higher-low structure.",
        "execution_authority": False,
    }


def test_llm_batch_cadence_is_bounded():
    assert should_run_intraday_llm_batch(
        observed_at=OBSERVED,
        previous_batch_at=None,
        minimum_interval_minutes=5,
    )
    assert not should_run_intraday_llm_batch(
        observed_at=OBSERVED,
        previous_batch_at=OBSERVED - timedelta(minutes=4, seconds=59),
        minimum_interval_minutes=5,
    )
    assert should_run_intraday_llm_batch(
        observed_at=OBSERVED,
        previous_batch_at=OBSERVED - timedelta(minutes=5),
        minimum_interval_minutes=5,
    )


def test_selection_uses_top_n_but_also_keeps_entry_ready_candidate():
    rows = [
        row("AAA", 1, opportunity=10),
        row("BBB", 2, opportunity=9),
        row("CCC", 3, state="entry_ready", opportunity=3),
    ]
    selected = select_intraday_llm_candidates(rows, top_n=2)
    assert [item[0].instrument_id for item in selected] == [
        "equity:NASDAQ:AAA",
        "equity:NASDAQ:BBB",
        "equity:NASDAQ:CCC",
    ]


def test_payload_includes_previous_assessment_without_granting_execution_authority():
    rows = [row("AAA", 1)]
    previous = {
        "equity:NASDAQ:AAA": {
            "assessment": {
                **assessment("equity:NASDAQ:AAA"),
                "summary": "Earlier thesis.",
            }
        }
    }
    payload = build_intraday_llm_payload(
        rows,
        ranks={"equity:NASDAQ:AAA": 1},
        previous_by_instrument=previous,
    )
    item = payload["candidates"][0]
    assert item["live_research_rank"] == 1
    assert item["previous_llm_assessment"]["summary"] == "Earlier thesis."
    assert item["intraday_learning"]["execution_authority"] is False


def test_analyzer_uses_default_provider_contract_and_returns_strict_research_assessment():
    instrument_id = "equity:NASDAQ:AAA"
    provider = FakeProvider({"assessments": [assessment(instrument_id)]})
    analyzer = IntradayLLMAnalyzer(provider_factory=lambda: provider)

    output = analyzer.assess(
        [row("AAA", 1)],
        ranks={instrument_id: 1},
    )

    assert output.provider == "fixture"
    assert output.model == "fixture-model"
    assert output.assessments[0].instrument_id == instrument_id
    assert output.assessments[0].execution_authority is False
    assert provider.messages is not None
    assert "Never say buy, sell" in provider.messages[0].content
    user_payload = json.loads(provider.messages[1].content)
    assert user_payload["candidates"][0]["deterministic_strategy"]["state"] == "higher_low_confirmed"


def test_analyzer_fails_closed_when_provider_omits_requested_candidate():
    provider = FakeProvider({"assessments": []})
    analyzer = IntradayLLMAnalyzer(provider_factory=lambda: provider)

    with pytest.raises(RuntimeError, match="missing_assessments"):
        analyzer.assess(
            [row("AAA", 1)],
            ranks={"equity:NASDAQ:AAA": 1},
        )



def test_intraday_llm_requires_deterministic_learning_layer():
    with pytest.raises(ValueError, match="requires intraday learning"):
        GapPullbackConfig(
            intraday_learning_enabled=False,
            intraday_llm_enabled=True,
        )



class MemoryEventRepository:
    def __init__(self):
        self.events = []

    def recent_events(self, strategy_id, limit=200):
        matching = [event for event in self.events if event.strategy_id == strategy_id]
        return sorted(matching, key=lambda event: event.observed_at, reverse=True)[:limit]

    def append_event(self, event):
        if any(existing.idempotency_key == event.idempotency_key for existing in self.events):
            return False
        self.events.append(event)
        return True


class FixtureAnalyzer:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls = 0

    def assess(self, rows, *, ranks, previous_by_instrument=None):
        self.calls += 1
        if self.fail:
            raise RuntimeError("fixture provider unavailable")
        assessments = []
        for candidate_, *_ in rows:
            assessments.append(
                IntradayLLMAssessment.model_validate(
                    assessment(candidate_.instrument_id)
                )
            )
        return IntradayLLMResult(
            assessments=tuple(assessments),
            provider="fixture",
            model="fixture-model",
        )


def _llm_strategy() -> TradingStrategyConfigDocument:
    config = GapPullbackConfig(
        strategy_version="2.0.0",
        universe_discovery_source="finviz",
        intraday_learning_enabled=True,
        intraday_llm_enabled=True,
        intraday_llm_top_n=1,
        intraday_llm_interval_minutes=5,
    )
    return TradingStrategyConfigDocument(
        strategy_id="intraday-llm-test",
        account_id="paper-test",
        strategy_version="2.0.0",
        mode="shadow",
        config=config,
    )


def _llm_universe():
    observed = OBSERVED - timedelta(minutes=10)
    return freeze_gapper_universe(
        universe_id="finviz-intraday-llm-test",
        session_date=OBSERVED.date(),
        evaluation_time=OBSERVED,
        discovery_source="finviz",
        source_locator="https://finviz.com/screener?v=340&s=ta_topgainers",
        source_candidate_symbols=("AAA",),
        candidates=[candidate("AAA", 1).model_copy(update={"observed_at": observed})],
    )


def test_monitor_persists_llm_assessment_and_uses_batch_event_as_cadence_checkpoint():
    repository = MemoryEventRepository()
    analyzer = FixtureAnalyzer()
    monitor = TradingStrategyMonitor(
        intraday_llm_analyzer_factory=lambda: analyzer,
        interval_seconds=30,
    )
    monitor.current_run_id = "run-test"
    ranked = [row("AAA", 1)]

    asyncio.run(
        monitor._run_intraday_llm(
            _llm_strategy(),
            repository,
            _llm_universe(),
            ranked,
        )
    )

    assert analyzer.calls == 1
    assert monitor.intraday_llm_call_count == 1
    assert monitor.intraday_llm_assessment_count == 1
    assert [event.event_type for event in repository.events] == [
        "intraday_llm",
        "intraday_llm_batch",
    ]
    llm_event = repository.events[0]
    assert llm_event.payload["execution_authority"] is False
    assert llm_event.payload["assessment"]["execution_authority"] is False

    # Same causal minute cannot re-call the LLM because the persisted batch
    # checkpoint is at the same observed_at.
    asyncio.run(
        monitor._run_intraday_llm(
            _llm_strategy(),
            repository,
            _llm_universe(),
            ranked,
        )
    )
    assert analyzer.calls == 1
    assert monitor.intraday_llm_call_count == 1


def test_monitor_persists_failed_batch_checkpoint_to_bound_provider_retries():
    repository = MemoryEventRepository()
    analyzer = FixtureAnalyzer(fail=True)
    monitor = TradingStrategyMonitor(
        intraday_llm_analyzer_factory=lambda: analyzer,
        interval_seconds=30,
    )
    monitor.current_run_id = "run-error"
    ranked = [row("AAA", 1)]

    asyncio.run(
        monitor._run_intraday_llm(
            _llm_strategy(),
            repository,
            _llm_universe(),
            ranked,
        )
    )

    assert analyzer.calls == 1
    assert monitor.intraday_llm_call_count == 1
    assert monitor.intraday_llm_error_count == 1
    assert len(repository.events) == 1
    assert repository.events[0].event_type == "intraday_llm_batch"
    assert repository.events[0].state == "error"

    asyncio.run(
        monitor._run_intraday_llm(
            _llm_strategy(),
            repository,
            _llm_universe(),
            ranked,
        )
    )
    assert analyzer.calls == 1
