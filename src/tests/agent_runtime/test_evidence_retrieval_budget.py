from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.agent_runtime.broker_api import (
    BrokerCapabilityRequest,
    _reserve_evidence_retrieval_budget,
)
from app.agent_runtime.contracts import EvidencePolicy, RetrievalPolicy


def _policy(**updates):
    return EvidencePolicy(
        requirement="required",
        retrieval=RetrievalPolicy(**updates),
    )


class _Repository:
    def __init__(self):
        self.calls = []

    def reserve_evidence_query(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {
            "allowed": True,
            "reserved_sources": min(kwargs["requested_sources"], 3),
            "reserved_extracts": min(kwargs["requested_extracts"], 1),
        }


def test_web_research_input_is_bounded_by_durable_reservation() -> None:
    repository = _Repository()
    request = _reserve_evidence_retrieval_budget(
        repository,
        "run-1",
        "research.web_search",
        "exec-1",
        BrokerCapabilityRequest(input={"query": "topic", "max_results": 10, "max_extracts": 4}),
        policy=_policy(max_sources=3, max_extracts=1, max_queries=4, max_wall_time_seconds=60),
        revision_id="rev-1",
        started_at=datetime.now(timezone.utc),
    )
    assert request.input["max_results"] == 3
    assert request.input["max_extracts"] == 1
    assert repository.calls[0][1]["max_queries"] == 4


def test_evidence_wall_time_budget_is_enforced_before_reservation() -> None:
    with pytest.raises(HTTPException) as caught:
        _reserve_evidence_retrieval_budget(
            _Repository(),
            "run-1",
            "research.web_search",
            "exec-1",
            BrokerCapabilityRequest(input={"query": "topic"}),
            policy=_policy(max_queries=4, max_wall_time_seconds=1),
            revision_id="rev-1",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=2),
        )
    assert caught.value.detail == "agent_evidence_retrieval_wall_time_exceeded"


def test_evidence_requires_durable_task_revision_identity() -> None:
    with pytest.raises(HTTPException) as caught:
        _reserve_evidence_retrieval_budget(
            _Repository(),
            "run-1",
            "research.web_search",
            "exec-1",
            BrokerCapabilityRequest(input={"query": "topic"}),
            policy=_policy(),
            revision_id=None,
            started_at=datetime.now(timezone.utc),
        )
    assert caught.value.detail == "agent_evidence_task_revision_unavailable"
