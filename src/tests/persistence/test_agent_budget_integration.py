from __future__ import annotations

import os
import uuid

import pytest

from app.agent_runtime.budget import AgentBudgetError, AgentBudgetManager
from app.agent_runtime.contracts import AgentRunSpec, ModelRef, RunLimits
from app.agent_runtime.repository import PostgresAgentRunRepository
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
        manager.record_output_tokens(token_run, 5)
        with pytest.raises(
            AgentBudgetError,
            match="budget_max_output_tokens_exceeded",
        ):
            manager.record_output_tokens(token_run, 1)

        usage = manager.usage(token_run)
        assert usage["output_tokens"] == 5
    finally:
        database.close()
