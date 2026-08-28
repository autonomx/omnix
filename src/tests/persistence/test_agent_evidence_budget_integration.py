from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import uuid

import pytest

from app.agent_runtime.contracts import AgentRunSpec, ModelRef, TaskRevision
from app.agent_runtime.repository import PostgresAgentRunRepository
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work


DATABASE_URL = os.environ.get("OMNIX_TEST_DATABASE_URL")


@pytest.mark.skipif(not DATABASE_URL, reason="requires PostgreSQL integration database")
def test_evidence_query_reservations_are_idempotent_and_aggregate_bounded() -> None:
    database = PostgresDatabase(DATABASE_URL)
    context = bootstrap_local_tenant(database)
    run_id = f"evidence-budget-{uuid.uuid4().hex}"
    spec = AgentRunSpec(
        run_id=run_id,
        task="research",
        profile="research",
        model=ModelRef(provider_id="test", model_id="model"),
        external_capabilities=["research.web_search"],
    )
    with unit_of_work(database) as work:
        repository = PostgresAgentRunRepository(work.connection, context)
        repository.create_run(spec)
        revision = repository.latest_task_revision(run_id)
        assert revision is not None

        first = repository.reserve_evidence_query(
            run_id,
            revision.revision_id,
            "exec-1",
            max_queries=2,
            max_sources=3,
            max_extracts=1,
            requested_sources=2,
            requested_extracts=1,
        )
        replay = repository.reserve_evidence_query(
            run_id,
            revision.revision_id,
            "exec-1",
            max_queries=2,
            max_sources=3,
            max_extracts=1,
            requested_sources=2,
            requested_extracts=1,
        )
        assert first["reused"] is False
        assert replay["reused"] is True

        second = repository.reserve_evidence_query(
            run_id,
            revision.revision_id,
            "exec-2",
            max_queries=2,
            max_sources=3,
            max_extracts=1,
            requested_sources=2,
            requested_extracts=1,
        )
        assert second["reserved_sources"] == 1
        assert second["reserved_extracts"] == 0

        blocked = repository.reserve_evidence_query(
            run_id,
            revision.revision_id,
            "exec-3",
            max_queries=2,
            max_sources=3,
            max_extracts=1,
            requested_sources=1,
            requested_extracts=0,
        )
        assert blocked["allowed"] is False
        assert blocked["reason"] == "query_budget_exceeded"
        work.rollback()


@pytest.mark.skipif(not DATABASE_URL, reason="requires PostgreSQL integration database")
def test_stale_read_capability_execution_can_be_reclaimed() -> None:
    database = PostgresDatabase(DATABASE_URL)
    context = bootstrap_local_tenant(database)
    run_id = f"read-reclaim-{uuid.uuid4().hex}"
    spec = AgentRunSpec(
        run_id=run_id,
        task="research",
        profile="research",
        model=ModelRef(provider_id="test", model_id="model"),
        external_capabilities=["research.web_search"],
    )
    with unit_of_work(database) as work:
        repository = PostgresAgentRunRepository(work.connection, context)
        repository.create_run(spec)
        repository.ensure_capability_execution(
            run_id,
            "exec-1",
            "research.web_search",
            {"input": {"query": "topic"}, "approval_id": None},
        )
        assert repository.claim_capability_execution(run_id, "exec-1")
        work.connection.execute(
            """
            UPDATE omnix_agent_capability_executions
               SET updated_at = CURRENT_TIMESTAMP - INTERVAL '2 minutes'
             WHERE workspace_id = %s AND run_id = %s AND execution_key = %s
            """,
            (context.workspace_id, run_id, "exec-1"),
        )
        assert repository.reclaim_stale_read_capability_execution(
            run_id,
            "exec-1",
            stale_before=datetime.now(timezone.utc) - timedelta(seconds=30),
        )
        stored = repository.ensure_capability_execution(
            run_id,
            "exec-1",
            "research.web_search",
            {"input": {"query": "topic"}, "approval_id": None},
        )
        assert stored["state"] == "created"
        work.rollback()
