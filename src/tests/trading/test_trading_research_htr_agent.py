from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.trading.research.contracts import (
    ResearchActionProposal,
    ResearchActionRecord,
    ResearchCoverage,
    TradingResearchRequest,
    fingerprint,
)
from app.trading.research.coordinator import _research_status
from app.trading.research.hermes_contract import TradingHermesNextActionDecision
from app.trading.research.policy import evaluate_research_policy


def _request(**updates):
    now=datetime.now(timezone.utc)
    values=dict(request_id="r",instrument_id="equity:NASDAQ:XYZ",requested_at=now,decision_context_at=now,evidence_cutoff_at=now,deadline_at=now+timedelta(seconds=30))
    values.update(updates);return TradingResearchRequest(**values)


def _failed_source(step: int, operation: str) -> ResearchActionRecord:
    now = datetime.now(timezone.utc)
    return ResearchActionRecord(
        action_id=f"a-{step}", trace_id="trace", instrument_id="equity:NASDAQ:XYZ",
        step=step, operation=operation, args={}, reason="fixture", status="failed",
        result_summary={}, evidence_ids=(), requested_at=now, completed_at=now,
        error_code="ProviderError",
        immutable_fingerprint=fingerprint({"step": step, "operation": operation}),
    )


def test_trading_hermes_contract_blocks_order_operation():
    with pytest.raises(ValidationError):
        ResearchActionProposal.model_validate({"operation":"place_order","args":{"symbol":"XYZ"},"reason":"buy"})


def test_trading_hermes_contract_allows_exactly_one_semantic_action():
    decision=TradingHermesNextActionDecision.model_validate({"action":{"operation":"sec_find_filings","args":{"forms":"8-K,S-3"},"reason":"financing clue"},"rationale":"check primary source"})
    assert decision.action.operation=="sec_find_filings"


def test_request_enforces_hard_budgets():
    with pytest.raises(ValidationError): _request(max_steps=21)
    with pytest.raises(ValidationError): _request(max_queries=21)


def test_research_status_distinguishes_timeout_and_total_source_failure():
    assert _research_status(
        coverage=ResearchCoverage(), actions=[], evidence_count=0, stop_reason="deadline_exhausted",
    ) == "timed_out"
    failed = [
        _failed_source(0, "sec_find_filings"),
        _failed_source(1, "company_find_releases"),
        _failed_source(2, "web_search"),
    ]
    assert _research_status(
        coverage=ResearchCoverage(sec="failed", company_ir="failed", recent_news="failed"),
        actions=failed, evidence_count=0, stop_reason="planner_stop",
    ) == "failed"


def test_legacy_strategy_research_is_never_authoritative():
    decision=evaluate_research_policy(strategy_version="1.1.0",features=None,validation=None)
    assert decision.allowed is True and decision.authoritative is False


def test_v12_fails_closed_without_reviewed_validation():
    decision=evaluate_research_policy(strategy_version="1.2.0",features=None,validation=None)
    assert decision.allowed is False and decision.reason_code=="RESEARCH_POLICY_NOT_VALIDATED"
