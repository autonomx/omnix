from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.agent_runtime.broker_api import BrokerCapabilityRequest, _bind_evidence_retrieval_budget
from app.agent_runtime.contracts import EvidencePolicy, EvidenceReceipt, RetrievalPolicy


def _policy(**updates):
    return EvidencePolicy(
        requirement="required",
        retrieval=RetrievalPolicy(**updates),
    )


def test_web_research_input_is_bounded_by_evidence_policy() -> None:
    request = _bind_evidence_retrieval_budget(
        "research.web_search",
        BrokerCapabilityRequest(input={"query": "topic", "max_results": 10, "max_extracts": 4}),
        policy=_policy(max_sources=3, max_extracts=1, max_queries=4, max_wall_time_seconds=60),
        revision_id="rev-1",
        started_at=datetime.now(timezone.utc),
        receipts=[],
    )
    assert request.input["max_results"] == 3
    assert request.input["max_extracts"] == 1


def test_evidence_query_budget_is_enforced_per_revision() -> None:
    receipts = [
        EvidenceReceipt(
            run_id="run-1",
            task_revision_id="rev-1",
            capability_id="research.web_search",
            source_class="general_current_web",
            request_digest=f"req-{index}",
            result_digest=f"result-{index}",
        )
        for index in range(2)
    ]
    with pytest.raises(HTTPException) as caught:
        _bind_evidence_retrieval_budget(
            "research.web_search",
            BrokerCapabilityRequest(input={"query": "topic"}),
            policy=_policy(max_queries=2, max_wall_time_seconds=60),
            revision_id="rev-1",
            started_at=datetime.now(timezone.utc),
            receipts=receipts,
        )
    assert caught.value.status_code == 429
    assert caught.value.detail == "agent_evidence_retrieval_query_budget_exceeded"


def test_evidence_wall_time_budget_is_enforced() -> None:
    with pytest.raises(HTTPException) as caught:
        _bind_evidence_retrieval_budget(
            "research.web_search",
            BrokerCapabilityRequest(input={"query": "topic"}),
            policy=_policy(max_queries=4, max_wall_time_seconds=1),
            revision_id="rev-1",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=2),
            receipts=[],
        )
    assert caught.value.detail == "agent_evidence_retrieval_wall_time_exceeded"
