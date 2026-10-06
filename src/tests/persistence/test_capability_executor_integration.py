"""The broker charges the tool budget for capability calls itself (WP-4.5)."""
from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.platform.agent_runtime import broker_api
from app.platform.agent_runtime.broker_api import BrokerCapabilityRequest, execute_agent_capability
from app.platform.agent_runtime.budget import AgentBudgetManager
from app.platform.agent_runtime.contracts import AgentRunSpec, ModelRef, RunLimits
from app.platform.agent_runtime.repository import PostgresAgentRunRepository
from app.platform.agent_runtime.service import AgentRunService
from app.platform.assistant_tools.models import AssistantToolResult, AssistantToolReviewDecision
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.unit_of_work import unit_of_work

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]

CAPABILITY = "contacts.search_contacts"  # not an evidence capability: input is not rewritten


@pytest.fixture
def broker(monkeypatch):
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=4))
    context = ensure_local_identity(database)
    service = AgentRunService(database, context=context)
    grants = []

    def review(request, _policy):
        return request, AssistantToolReviewDecision(
            tool_id=request.tool_id, action_id=request.action_id, session_id=request.session_id,
            allowed=True, executable=True, approval_required=False, risk_level="low",
        )

    def execute(grant, request, *, user_request=""):
        grants.append(grant)
        return SimpleNamespace(execution_result=AssistantToolResult(
            tool_id=request.tool_id, action_id=request.action_id, session_id=request.session_id,
            result_summary="ok", output={"items": []},
        ))

    monkeypatch.setattr(broker_api, "default_agent_run_service", lambda: service)
    monkeypatch.setattr(broker_api, "default_agent_budget_manager", lambda: AgentBudgetManager(database, context=context))
    monkeypatch.setattr(broker_api, "_review_with_run_policy", review)
    monkeypatch.setattr(broker_api, "execute_capability", execute)
    try:
        yield database, context, grants
    finally:
        database.close()


def _run(database, context, *, max_tool_calls: int) -> str:
    run_id = f"capability-budget-{uuid.uuid4().hex[:10]}"
    spec = AgentRunSpec(
        run_id=run_id,
        task="capability budget",
        model=ModelRef(provider_id="lmstudio", model_id="test"),
        limits=RunLimits(max_tool_calls=max_tool_calls),
        external_capabilities=[CAPABILITY],
    )
    with unit_of_work(database) as work:
        repository = PostgresAgentRunRepository(work.connection, context)
        created = repository.create_run(spec)
        repository.update_state(run_id, expected_revision=created.revision, status="running")
        work.commit()
    return run_id


def _tool_calls(database, context, run_id: str) -> int:
    with unit_of_work(database) as work:
        usage = PostgresAgentRunRepository(work.connection, context).get_usage(run_id)
        work.rollback()
    return int(usage["tool_calls"])


def test_capability_calls_are_charged_by_the_broker_and_stop_at_the_limit(broker) -> None:
    database, context, grants = broker
    run_id = _run(database, context, max_tool_calls=1)

    first = execute_agent_capability(run_id, CAPABILITY, BrokerCapabilityRequest(input={"query": "first"}))
    assert first.result["result_summary"] == "ok"
    assert _tool_calls(database, context, run_id) == 1
    assert grants[0].source == "agent_run" and grants[0].approved is False

    with pytest.raises(HTTPException) as refused:
        execute_agent_capability(run_id, CAPABILITY, BrokerCapabilityRequest(input={"query": "second"}))
    assert refused.value.status_code == 429
    assert refused.value.detail == "budget_max_tool_calls_exceeded"
    assert len(grants) == 1  # the adapter never ran


def test_replaying_a_completed_call_is_not_charged_again(broker) -> None:
    database, context, grants = broker
    run_id = _run(database, context, max_tool_calls=5)
    request = BrokerCapabilityRequest(proposal_id="call-1", input={"query": "same"})

    execute_agent_capability(run_id, CAPABILITY, request)
    execute_agent_capability(run_id, CAPABILITY, request)
    assert _tool_calls(database, context, run_id) == 1
    assert len(grants) == 1
