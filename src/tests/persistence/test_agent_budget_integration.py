from __future__ import annotations

import os
import uuid

import pytest

from app.agent_runtime.budget import AgentBudgetError, AgentBudgetManager
from app.agent_runtime.contracts import AgentRunSpec, ModelRef, RunLimits
from app.agent_runtime.repository import PostgresAgentRunRepository
from app.agent_runtime.resource_grants import PostgresResourceGrantRepository, ResourceGrantError
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-agent-budget-tests",
        )
    )


def _run(database: PostgresDatabase, suffix: str, limits: RunLimits) -> str:
    context = bootstrap_local_tenant(database)
    run_id = f"budget-{suffix}-{uuid.uuid4().hex[:8]}"
    spec = AgentRunSpec(
        run_id=run_id,
        task="budget",
        model=ModelRef(provider_id="lmstudio", model_id="test"),
        limits=limits,
    )
    with unit_of_work(database) as work:
        repository = PostgresAgentRunRepository(work.connection, context)
        created = repository.create_run(spec)
        repository.update_state(
            run_id,
            expected_revision=created.revision,
            status="running",
        )
        work.commit()
    return run_id


def test_agent_budgets_are_durable_and_fail_closed() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        manager = AgentBudgetManager(database, context=context)

        step_run = _run(
            database,
            "steps",
            RunLimits(max_steps=1, max_tool_calls=10, max_tokens=20),
        )
        manager.authorize_model_call(step_run, provider_id="lmstudio")
        with pytest.raises(AgentBudgetError, match="budget_max_steps_exceeded"):
            manager.authorize_model_call(step_run, provider_id="lmstudio")
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            step_snapshot = repository.get_run(step_run)
            step_events = repository.list_events(step_run, after_sequence=0, limit=100)
            work.rollback()
        assert step_snapshot is not None
        assert step_snapshot.status == "failed"
        assert step_snapshot.last_error == "budget_max_steps_exceeded"
        budget_failure = next(event for event in step_events if event.event_type == "run.failed")
        assert budget_failure.payload["source"] == "omnix_budget"
        assert budget_failure.payload["error"] == "budget_max_steps_exceeded"
        assert budget_failure.payload["provider_error_code"] == "agent_run_budget_exhausted"

        tool_run = _run(
            database,
            "tools",
            RunLimits(max_steps=10, max_tool_calls=1, max_tokens=20),
        )
        manager.authorize_tool_call(tool_run, tool_name="read")
        with pytest.raises(
            AgentBudgetError,
            match="budget_max_tool_calls_exceeded",
        ):
            manager.authorize_tool_call(tool_run, tool_name="read")

        token_run = _run(
            database,
            "tokens",
            RunLimits(max_steps=10, max_tool_calls=10, max_tokens=5),
        )
        manager.record_token_usage(token_run, input_tokens=3, output_tokens=5)
        with pytest.raises(
            AgentBudgetError,
            match="budget_max_output_tokens_exceeded",
        ):
            manager.record_output_tokens(token_run, 1)

        usage = manager.usage(token_run)
        assert usage["input_tokens"] == 3
        assert usage["output_tokens"] == 5
    finally:
        database.close()


def test_parent_execution_budget_is_reduced_by_child_reservations() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        parent_id = f"budget-parent-{uuid.uuid4().hex[:8]}"
        child_id = f"budget-child-{uuid.uuid4().hex[:8]}"
        parent_spec = AgentRunSpec(
            run_id=parent_id,
            task="parent",
            model=ModelRef(provider_id="lmstudio", model_id="test"),
            limits=RunLimits(
                max_steps=2,
                max_tool_calls=4,
                max_tokens=20,
            ),
        )
        child_spec = AgentRunSpec(
            run_id=child_id,
            parent_run_id=parent_id,
            task="child",
            model=ModelRef(provider_id="lmstudio", model_id="test"),
            limits=RunLimits(
                max_steps=1,
                max_tool_calls=1,
                max_tokens=5,
            ),
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            parent = repository.create_run(parent_spec)
            repository.update_state(
                parent_id,
                expected_revision=parent.revision,
                status="running",
            )
            repository.create_run(child_spec)
            work.commit()

        manager = AgentBudgetManager(database, context=context)
        manager.authorize_model_call(parent_id, provider_id="lmstudio")
        with pytest.raises(AgentBudgetError, match="budget_max_steps_exceeded"):
            manager.authorize_model_call(parent_id, provider_id="lmstudio")
    finally:
        database.close()


def test_resource_grant_replay_is_idempotent_but_conflicting_authority_fails_closed() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        parent_id = f"grant-parent-{uuid.uuid4().hex[:8]}"
        other_parent_id = f"grant-parent-other-{uuid.uuid4().hex[:8]}"
        child_id = f"grant-child-{uuid.uuid4().hex[:8]}"
        limits = RunLimits(
            max_steps=20,
            max_tool_calls=30,
            max_tokens=4000,
            max_wall_time_seconds=120,
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            repository.create_run(
                AgentRunSpec(
                    run_id=parent_id,
                    task="parent",
                    model=ModelRef(provider_id="lmstudio", model_id="test"),
                )
            )
            repository.create_run(
                AgentRunSpec(
                    run_id=other_parent_id,
                    task="other parent",
                    model=ModelRef(provider_id="lmstudio", model_id="test"),
                )
            )
            repository.create_run(
                AgentRunSpec(
                    run_id=child_id,
                    parent_run_id=parent_id,
                    task="child",
                    model=ModelRef(provider_id="lmstudio", model_id="test"),
                    limits=limits,
                )
            )
            grants = PostgresResourceGrantRepository(work.connection, context)
            first = grants.add_grant(
                parent_run_id=parent_id,
                child_run_id=child_id,
                limits=limits,
            )
            replay = grants.add_grant(
                parent_run_id=parent_id,
                child_run_id=child_id,
                limits=limits,
            )
            assert replay == first
            with pytest.raises(ResourceGrantError, match="resource_grant_identity_conflict"):
                grants.add_grant(
                    parent_run_id=parent_id,
                    child_run_id=child_id,
                    limits=limits.model_copy(update={"max_steps": limits.max_steps + 1}),
                )
            with pytest.raises(ResourceGrantError, match="resource_grant_identity_conflict"):
                grants.add_grant(
                    parent_run_id=other_parent_id,
                    child_run_id=child_id,
                    limits=limits,
                )
            work.rollback()
    finally:
        database.close()


def test_token_reporting_distinguishes_missing_from_reported_zero() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = _run(database, "reported-zero", RunLimits(max_steps=10, max_tool_calls=10))
        manager = AgentBudgetManager(database, context=context)
        before = manager.usage(run_id)
        assert before["input_tokens"] == 0
        assert before["output_tokens"] == 0
        assert before["input_tokens_reported"] is False
        assert before["output_tokens_reported"] is False

        manager.record_token_usage(run_id, input_tokens=0, output_tokens=0)
        after = manager.usage(run_id)
        assert after["input_tokens"] == 0
        assert after["output_tokens"] == 0
        assert after["input_tokens_reported"] is True
        assert after["output_tokens_reported"] is True
        with unit_of_work(database) as work:
            snapshot = PostgresAgentRunRepository(work.connection, context).get_run(run_id)
            work.rollback()
        assert snapshot is not None
        assert snapshot.usage.input_tokens_reported is True
        assert snapshot.usage.output_tokens_reported is True
    finally:
        database.close()
