"""Jobs keep the submitting request's id (WP-10.2)."""
from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from app.jobs.models import CreateJobRequest, ResourceClass
from app.observability.logging import log_context
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresConstraintError, PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.job_store import PostgresJobStoreAdapter
from app.runtime.tenant_context import install_process_tenant
from tests.support.database import admin_database_url

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]


@pytest.fixture
def store():
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=2))
    install_process_tenant(ensure_local_identity(database))
    module = f"correlation-test-{uuid.uuid4().hex[:10]}"
    try:
        yield PostgresJobStoreAdapter(database=database), module
    finally:
        with psycopg.connect(admin_database_url(), autocommit=True) as admin:
            admin.execute(
                "DELETE FROM omnix_job_events WHERE job_id IN (SELECT id FROM omnix_jobs WHERE module = %s)", (module,),
            )
            admin.execute("DELETE FROM omnix_jobs WHERE module = %s", (module,))
        database.close()


def _request(module: str) -> CreateJobRequest:
    return CreateJobRequest(module=module, type="correlation.probe", resource_class=ResourceClass.CPU)


def test_a_job_keeps_the_request_id_it_was_submitted_under(store) -> None:
    adapter, module = store

    with log_context(request_id="req-correlation-0001"):
        created = adapter.create_job(_request(module))
        once = adapter.create_job_once(_request(module), idempotency_key=uuid.uuid4().hex)
    outside = adapter.create_job(_request(module))

    assert created.correlation_id == once.correlation_id == "req-correlation-0001"
    assert adapter.get_job(created.id).correlation_id == "req-correlation-0001"
    assert outside.correlation_id is None


def test_the_column_rejects_oversized_ids(store) -> None:
    adapter, module = store

    with log_context(request_id="x" * 129), pytest.raises(PostgresConstraintError, match="CheckViolation"):
        adapter.create_job(_request(module))
