from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.agent_runtime.broker_api import (
    BrokerCapabilityRequest,
    _approved_execution_key,
    _revision_scoped_evidence_execution_key,
)
from app.agent_runtime.contracts import AgentApproval


def _approval(**updates):
    payload = {
        "input": {"target": "Desk", "state": "off"},
        "execution_key": "agent:run-1:tool-call-1",
    }
    payload.update(updates.pop("request_payload", {}))
    return AgentApproval(
        approval_id="approval-1",
        run_id="run-1",
        capability_id=updates.pop("capability_id", "home.set_state"),
        state="approved",
        request_payload=payload,
        **updates,
    )


def test_approval_reuses_original_execution_identity_across_model_retry() -> None:
    request = BrokerCapabilityRequest(
        proposal_id="new-tool-call",
        approval_id="approval-1",
        input={"target": "Desk", "state": "off"},
    )
    assert _approved_execution_key(
        "run-1", "home.set_state", request, _approval()
    ) == "agent:run-1:tool-call-1"


def test_approval_cannot_authorize_changed_arguments() -> None:
    request = BrokerCapabilityRequest(
        approval_id="approval-1",
        input={"target": "Bedroom", "state": "off"},
    )
    with pytest.raises(HTTPException) as caught:
        _approved_execution_key("run-1", "home.set_state", request, _approval())
    assert caught.value.status_code == 403
    assert caught.value.detail == "agent_approval_input_mismatch"



def test_authoritative_market_subject_overrides_missing_ticker_and_rejects_conflict() -> None:
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.agent_runtime.broker_api import BrokerCapabilityRequest, _bind_authoritative_capability_input
    from app.agent_runtime.contracts import EvidencePolicy, EvidenceRequirement, SubjectRef

    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            EvidenceRequirement(
                id="quote",
                source_class="market_quote",
                subject=SubjectRef(
                    type="security",
                    canonical_id="equity:NASDAQ:NVDA",
                    qualifiers={"ticker": "NVDA"},
                ),
            )
        ],
    )
    snapshot = SimpleNamespace(spec=SimpleNamespace(workspace=None))
    bounded = _bind_authoritative_capability_input(
        snapshot,
        "trading.market_quote",
        BrokerCapabilityRequest(input={}),
        policy=policy,
    )
    assert bounded.input["ticker"] == "NVDA"
    with pytest.raises(HTTPException) as caught:
        _bind_authoritative_capability_input(
            snapshot,
            "trading.market_quote",
            BrokerCapabilityRequest(input={"ticker": "TSLA"}),
            policy=policy,
        )
    assert caught.value.status_code == 403



def test_evidence_execution_identity_is_scoped_to_task_revision() -> None:
    base = "agent:run-1:tool-call-1"
    first = _revision_scoped_evidence_execution_key(base, "revision-1")
    replay = _revision_scoped_evidence_execution_key(base, "revision-1")
    second = _revision_scoped_evidence_execution_key(base, "revision-2")
    assert first == replay
    assert first != second
    assert first.startswith(base + ":evidence-revision:")
