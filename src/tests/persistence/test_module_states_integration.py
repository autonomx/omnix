"""Job creation honors the module's lifecycle state in its own transaction (PA-4.3)."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.jobs.handlers import JobExecutionContext, JobHandlerRegistry, JobHandlerSpec
from app.jobs.models import CreateJobRequest, JobRecord
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.job_store import PostgresJobStoreAdapter
from app.persistence.module_states import ModuleNotAcceptingWork, read_module_state, set_module_state

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not os.environ.get("OMNIX_TEST_DATABASE_URL"), reason="OMNIX_TEST_DATABASE_URL is required"),
]


@pytest.fixture
def setup():
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=4))
    module = f"lifecycle-{uuid.uuid4().hex[:8]}"
    submitted: list[JobRecord] = []
    registry = JobHandlerRegistry()
    store = PostgresJobStoreAdapter(database)

    def follow_up(_context: JobExecutionContext, job: JobRecord) -> JobRecord:
        submitted.append(store.create_job(CreateJobRequest(module=module, type=f"{module}.work", resource_class="cpu")))
        return job

    registry.register(JobHandlerSpec(type=f"{module}.work", handler=follow_up), owner=module)
    store.configure_handler_registry(registry)
    try:
        yield database, module, registry, store, submitted
    finally:
        with database.transaction() as connection:
            connection.execute("DELETE FROM omnix_module_states WHERE module_id = %s", (module,))
        database.close()


def _set(database, module: str, state: str, deadline: datetime | None = None) -> None:
    with database.transaction() as connection:
        set_module_state(connection, module, state, drain_deadline=deadline, reason="test")


def test_a_draining_module_refuses_new_jobs_but_takes_its_own_follow_ups(setup) -> None:
    database, module, registry, store, submitted = setup
    parent = store.create_job(CreateJobRequest(module=module, type=f"{module}.work", resource_class="cpu"))
    _set(database, module, "draining", datetime.now(timezone.utc) + timedelta(minutes=5))

    with pytest.raises(ModuleNotAcceptingWork):
        store.create_job(CreateJobRequest(module=module, type=f"{module}.work", resource_class="cpu"))
    registry.execute(JobExecutionContext(job_store=store), parent)

    (follow_up,) = submitted
    with database.connection() as connection:
        metadata = connection.execute("SELECT metadata FROM omnix_jobs WHERE id = %s", (follow_up.id,)).fetchone()[0]
    assert metadata["parent_job_id"] == parent.id


def test_follow_ups_stop_at_the_drain_deadline_and_a_retired_module_takes_nothing(setup) -> None:
    database, module, registry, store, submitted = setup
    parent = store.create_job(CreateJobRequest(module=module, type=f"{module}.work", resource_class="cpu"))

    _set(database, module, "draining", datetime.now(timezone.utc) - timedelta(seconds=1))
    with pytest.raises(ModuleNotAcceptingWork):
        registry.execute(JobExecutionContext(job_store=store), parent)
    _set(database, module, "retired")
    with pytest.raises(ModuleNotAcceptingWork):
        registry.execute(JobExecutionContext(job_store=store), parent)
    assert submitted == []
    with database.connection() as connection:
        assert read_module_state(connection, module).state == "retired"


def test_an_active_or_unrecorded_module_takes_new_jobs(setup) -> None:
    database, module, _registry, store, _submitted = setup
    assert store.create_job(CreateJobRequest(module=module, type=f"{module}.work", resource_class="cpu")).id
    _set(database, module, "active")
    assert store.create_job(CreateJobRequest(module=module, type=f"{module}.work", resource_class="cpu")).id
