from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.trading.gapper_dataset import GapperCandidate
from app.trading.strategies.models import GapPullbackFeatures, GapPullbackResult, StrategySignal
from app.trading.strategy_intraday_learning import IntradayLearningSnapshot
from app.trading.strategy_intraday_llm import (
    IntradayLLMAnalyzer,
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
