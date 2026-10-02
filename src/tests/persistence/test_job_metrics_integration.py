"""The job queue snapshot behind /metrics (WP-10.3)."""
from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from app.jobs.models import CancelJobRequest, CreateJobRequest, ResourceClass
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.job_store import PostgresJobStoreAdapter
from app.persistence.unit_of_work import unit_of_work
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
    module = f"metrics-test-{uuid.uuid4().hex[:10]}"
    try:
        yield PostgresJobStoreAdapter(database=database), module
    finally:
        with psycopg.connect(admin_database_url(), autocommit=True) as admin:
            admin.execute(
                "DELETE FROM omnix_job_events WHERE job_id IN (SELECT id FROM omnix_jobs WHERE module = %s)", (module,),
            )
            admin.execute("DELETE FROM omnix_jobs WHERE module = %s", (module,))
        database.close()


def test_the_snapshot_counts_active_jobs_by_type_and_status(store) -> None:
    adapter, module = store
    job_type = f"{module}.probe"
    request = CreateJobRequest(module=module, type=job_type, resource_class=ResourceClass.CPU)
    adapter.create_job(request)
    adapter.create_job(request)
    finished = adapter.create_job(request)
    adapter.request_cancel(finished.id, CancelJobRequest(reason="metrics test"))

    with unit_of_work(adapter.database) as work:
        snapshot = work.jobs.metrics_snapshot(adapter.context)
        work.rollback()

    rows = [row for row in snapshot["active"] if row["job_type"] == job_type]
    assert [(row["status"], row["count"]) for row in rows] == [("queued", 2)]
    assert rows[0]["oldest_waiting_age_seconds"] >= 0
    assert rows[0]["expired_leases"] == 0
    assert snapshot["dead_letter_count"] >= 0


def test_metrics_read_the_pool_jobs_and_outbox_of_a_postgresql_runtime(store) -> None:
    from types import SimpleNamespace

    from app.observability.metrics import DurableStateCollector, PoolCollector, exposition
    from app.platform.runtime_diagnostics import durable_metrics_snapshot

    adapter, module = store
    adapter.create_job(CreateJobRequest(module=module, type=f"{module}.probe", resource_class=ResourceClass.CPU))
    services = SimpleNamespace(jobs=adapter)

    text = exposition(
        PoolCollector(adapter.database.pool_statistics),
        DurableStateCollector(lambda: durable_metrics_snapshot(services)),
    )[0].decode()

    assert "omnix_jobs_snapshot_up 1.0" in text
    assert f'omnix_jobs_active{{job_type="{module}.probe",status="queued"}} 1.0' in text
    assert "omnix_outbox_unpublished" in text
    assert "omnix_db_pool_in_use" in text and "omnix_db_pool_requests_total" in text
