"""Recovery after a module is retired (PA-4.3): its jobs fail once; other unclaimed jobs only alert."""
from __future__ import annotations

import os
import uuid

import pytest

from app.jobs.models import CreateJobRequest
from app.persistence import declarations
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.job_store import PostgresJobStoreAdapter
from app.persistence.unit_of_work import unit_of_work
from app.runtime.tenant_context import current_tenant

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not os.environ.get("OMNIX_TEST_DATABASE_URL"), reason="OMNIX_TEST_DATABASE_URL is required"),
]


@pytest.fixture
def database():
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=4))
    try:
        yield database
    finally:
        database.close()


def _job(store: PostgresJobStoreAdapter, job_type: str) -> str:
    return store.create_job(CreateJobRequest(module="retired-test", type=job_type, resource_class="cpu")).id


def test_unfinished_jobs_of_a_retired_type_fail_once_and_others_are_left_alone(database) -> None:
    suffix = uuid.uuid4().hex[:8]
    retired, other = f"gone-{suffix}.work", f"kept-{suffix}.work"
    store = PostgresJobStoreAdapter(database)
    queued, running, untouched = _job(store, retired), _job(store, retired), _job(store, other)
    with database.transaction() as connection:
        connection.execute(
            """UPDATE omnix_jobs SET status = 'running', lease_owner = 'worker', lease_token = 'token',
                      lease_expires_at = clock_timestamp() + INTERVAL '1 minute' WHERE id = %s""",
            (running,),
        )
    context = current_tenant()

    with unit_of_work(database) as work:
        failed = work.jobs.fail_retired_jobs(context, [retired])
        again = work.jobs.fail_retired_jobs(context, [retired])
        work.commit()

    assert sorted(job["id"] for job in failed) == sorted([queued, running])
    assert {job["error"]["code"] for job in failed} == {"module_retired"} and again == []
    with database.connection() as connection:
        statuses = dict(connection.execute(
            "SELECT id, status FROM omnix_jobs WHERE id = ANY(%s)", ([queued, running, untouched],),
        ).fetchall())
        dead = connection.execute(
            "SELECT count(*) FROM omnix_dead_letters WHERE job_id = ANY(%s) AND reason = 'module_retired'", ([queued, running],),
        ).fetchone()[0]
    assert statuses == {queued: "failed", running: "failed", untouched: "queued"}
    assert dead == 2


def test_an_old_job_nobody_here_can_claim_is_reported_not_failed(database) -> None:
    suffix = uuid.uuid4().hex[:8]
    unknown, known = f"newer-{suffix}.work", f"local-{suffix}.work"
    store = PostgresJobStoreAdapter(database)
    waiting, local = _job(store, unknown), _job(store, known)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE omnix_jobs SET available_at = clock_timestamp() - INTERVAL '2 hours' WHERE id = ANY(%s)", ([waiting, local],),
        )

    with unit_of_work(database) as work:
        report = work.jobs.unclaimed_job_types(current_tenant(), older_than_seconds=3600, known_types=[known])
        work.rollback()

    assert report[unknown] >= 7200 - 60 and known not in report
    with database.connection() as connection:
        assert connection.execute("SELECT status FROM omnix_jobs WHERE id = %s", (waiting,)).fetchone()[0] == "queued"

    # A worker claims only the types it handles; once one handles the type (re-enabled, upgraded), the job runs.
    def claim(job_types: list[str]) -> str | None:
        with unit_of_work(database) as work:
            claimed = work.jobs.claim_next(current_tenant(), worker_id="w", resource_classes=["cpu"], job_types=job_types)
            work.commit()
        return claimed["id"] if claimed else None

    assert claim([known]) == local
    assert claim([known]) is None
    assert claim([unknown]) == waiting


def test_retired_job_types_come_from_tombstones(monkeypatch) -> None:
    tombstone = type("Tombstone", (), {"JOB_TYPES": ("gone.work", "gone.other")})
    monkeypatch.setattr(declarations, "_modules_declaring", lambda kind: [tombstone] if kind == "JOB_TYPES" else [])

    assert declarations.retired_job_types() == {"gone.work", "gone.other"}
