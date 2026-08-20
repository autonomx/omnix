from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.trading.research.contracts import ResearchActionProposal, TradingResearchRequest
from app.trading.research.hermes_contract import TradingHermesNextActionDecision
from app.trading.research.policy import evaluate_research_policy


def _request(**updates):
    now=datetime.now(timezone.utc)
    values=dict(request_id="r",instrument_id="equity:NASDAQ:XYZ",requested_at=now,decision_context_at=now,evidence_cutoff_at=now,deadline_at=now+timedelta(seconds=30))
    values.update(updates);return TradingResearchRequest(**values)


def test_trading_hermes_contract_blocks_order_operation():
    with pytest.raises(ValidationError):
        ResearchActionProposal.model_validate({"operation":"place_order","args":{"symbol":"XYZ"},"reason":"buy"})


def test_trading_hermes_contract_allows_exactly_one_semantic_action():
    decision=TradingHermesNextActionDecision.model_validate({"action":{"operation":"sec_find_filings","args":{"forms":"8-K,S-3"},"reason":"financing clue"},"rationale":"check primary source"})
    assert decision.action.operation=="sec_find_filings"


def test_request_enforces_hard_budgets():
    with pytest.raises(ValidationError): _request(max_steps=21)
    with pytest.raises(ValidationError): _request(max_queries=21)


def test_legacy_strategy_research_is_never_authoritative():
    decision=evaluate_research_policy(strategy_version="1.1.0",features=None,validation=None)
    assert decision.allowed is True and decision.authoritative is False


def test_v12_fails_closed_without_reviewed_validation():
    decision=evaluate_research_policy(strategy_version="1.2.0",features=None,validation=None)
    assert decision.allowed is False and decision.reason_code=="RESEARCH_POLICY_NOT_VALIDATED"
