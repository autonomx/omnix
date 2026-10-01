"""Job list cursor pagination and SQL filters (WP-5.5)."""
from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.job_compat import PostgresJobStoreAdapter
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
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=4))
    tenant = ensure_local_identity(database)
    install_process_tenant(tenant)
    module = f"paging-test-{uuid.uuid4().hex[:10]}"
    try:
        yield PostgresJobStoreAdapter(database=database), tenant, module
    finally:
        with psycopg.connect(admin_database_url(), autocommit=True) as admin:
            admin.execute("DELETE FROM omnix_job_events WHERE job_id LIKE %s", (f"{module}:%",))
            admin.execute("DELETE FROM omnix_jobs WHERE module = %s", (module,))
        database.close()


def _insert(tenant, module: str, count: int) -> list[str]:
    ids = [f"{module}:{index:04d}" for index in range(count)]
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        with admin.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO omnix_jobs (id, workspace_id, module, job_type, resource_class, status, created_at)
                   VALUES (%s, %s, %s, %s, 'cpu', %s,
                           TIMESTAMPTZ '2026-10-01T00:00:00Z' - (%s * INTERVAL '1 second'))""",
                [
                    (job_id, tenant.workspace_id, module, "paging.even" if index % 2 == 0 else "paging.odd",
                     "completed" if index % 3 == 0 else "queued", index // 5)
                    for index, job_id in enumerate(ids)
                ],
            )
    return ids


def test_job_pages_cover_every_matching_job_once(store) -> None:
    adapter, tenant, module = store
    ids = _insert(tenant, module, 450)
    expected = {job_id for index, job_id in enumerate(ids) if index % 2 == 0}

    seen: list[str] = []
    cursor = None
    while True:
        page = adapter.list_job_page(limit=33, modules=(module,), job_types=("paging.even",), cursor=cursor)
        seen.extend(job.id for job in page.jobs)
        if not page.has_more:
            break
        cursor = page.next_cursor

    assert len(seen) == len(set(seen))
    assert set(seen) == expected
    assert {job.id for job in adapter.iter_jobs(modules=(module,), job_types=("paging.even",))} == expected


def test_status_filter_runs_in_sql(store) -> None:
    adapter, tenant, module = store
    ids = _insert(tenant, module, 30)
    completed = {job_id for index, job_id in enumerate(ids) if index % 3 == 0}

    assert {job.id for job in adapter.iter_jobs(modules=(module,), status="completed")} == completed
    assert len(adapter.list_jobs(5, modules=(module,))) == 5
