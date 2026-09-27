from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
import re
import secrets
from urllib.parse import urlsplit

import pytest

from app.agent_runtime.contracts import AgentRunSpec, ModelRef
from app.agent_runtime.repository import PostgresAgentRunRepository
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


@pytest.fixture
def run():
    url = os.environ["OMNIX_TEST_DATABASE_URL"]
    assert urlsplit(url).path in {"/omnix_test", "/omnix_refactor_baseline"}
    database = PostgresDatabase(DatabaseSettings(url=url, pool_min=1, pool_max=4))
    context = bootstrap_local_tenant(database)
    identifier = f"workspace-approval-{secrets.token_urlsafe(12)}"
    with unit_of_work(database) as work:
        repository = PostgresAgentRunRepository(work.connection, context)
        repository.create_run(AgentRunSpec(
            run_id=identifier, task="Inspect", model=ModelRef(provider_id="test", model_id="model"),
        ))
        work.commit()
    try:
        yield database, context, identifier
    finally:
        database.close()


def _propose(run, payload, capability="workspace.command"):
    database, context, identifier = run
    with unit_of_work(database) as work:
        repository = PostgresAgentRunRepository(work.connection, context)
        approval = repository.workspace_approval(identifier, capability, payload)
        work.commit()
        return approval


def test_identical_workspace_requests_share_an_opaque_random_identity(run):
    first = _propose(run, {"command": "python script.py", "cwd": "workspace"})
    repeated = _propose(run, {"cwd": "workspace", "command": "python script.py"})
    changed = _propose(run, {"command": "python different.py", "cwd": "workspace"})
    other_capability = _propose(run, first.request_payload, "workspace.write")
    assert repeated.approval_id == first.approval_id
    assert len({first.approval_id, changed.approval_id, other_capability.approval_id}) == 3
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{32}", approval.approval_id)
               for approval in (first, changed, other_capability))


def test_concurrent_identical_workspace_requests_create_one_approval_and_event(run):
    payload = {"command": "python script.py"}
    with ThreadPoolExecutor(max_workers=4) as executor:
        approvals = list(executor.map(lambda _: _propose(run, payload), range(4)))
    assert len({approval.approval_id for approval in approvals}) == 1
    database, context, identifier = run
    with unit_of_work(database) as work:
        repository = PostgresAgentRunRepository(work.connection, context)
        assert len(repository.list_approvals(identifier)) == 1
        assert len([event for event in repository.list_events(identifier)
                    if event.event_type == "approval.requested"]) == 1
        work.rollback()


@pytest.mark.parametrize("approved,state", [(True, "approved"), (False, "rejected")])
def test_exact_workspace_retry_preserves_the_durable_user_decision(run, approved, state):
    payload = {"command": "python script.py"}
    first = _propose(run, payload)
    database, context, identifier = run
    with unit_of_work(database) as work:
        repository = PostgresAgentRunRepository(work.connection, context)
        repository.resolve_approval(identifier, first.approval_id, approved=approved)
        work.commit()
    repeated = _propose(run, payload)
    assert repeated.approval_id == first.approval_id
    assert repeated.state == state


def test_workspace_approval_requires_a_run_in_the_current_workspace(run):
    database, context, _ = run
    with unit_of_work(database) as work:
        repository = PostgresAgentRunRepository(work.connection, context)
        with pytest.raises(KeyError):
            repository.workspace_approval("missing-run", "workspace.command", {})
        work.rollback()
