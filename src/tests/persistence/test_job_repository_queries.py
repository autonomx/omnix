from __future__ import annotations

import pytest

from app.persistence.job_repository import PostgresJobRepository
from app.persistence.tenant import TenantContext


class RecordingConnection:
    def __init__(self, *, row=None, rows=(), rowcount=0):
        self.row = row
        self.rows = list(rows)
        self.rowcount = rowcount
        self.calls = []

    def execute(self, sql, parameters=()):
        self.calls.append((sql, parameters))
        return self

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


def _context() -> TenantContext:
    return TenantContext(
        workspace_id="workspace:test",
        user_id="user:test",
        membership_id="membership:test",
        roles=frozenset({"owner"}),
    )


def test_query_jobs_filters_by_type_input_status_and_order() -> None:
    connection = RecordingConnection()
    repository = PostgresJobRepository(connection)

    assert repository.query_jobs(
        _context(),
        module="audiobook",
        job_types=("audiobook.analyze", "audiobook.ingest"),
        statuses=("queued", "running"),
        input_fields=(("project_id", "project:test"),),
        order_by="created_asc",
        limit=20,
        for_update=True,
    ) == []

    sql, parameters = connection.calls[0]
    assert "jobs.workspace_id = %s" in sql
    assert "jobs.job_type = ANY(%s)" in sql
    assert "jobs.status = ANY(%s)" in sql
    assert "jobs.input_payload ->> %s = %s" in sql
    assert "ORDER BY jobs.created_at ASC, jobs.id ASC" in sql
    assert sql.endswith("LIMIT %s FOR UPDATE")
    assert parameters == (
        "workspace:test",
        "audiobook",
        ["audiobook.analyze", "audiobook.ingest"],
        ["queued", "running"],
        "project_id",
        "project:test",
        20,
    )


def test_query_jobs_rejects_untrusted_ordering() -> None:
    repository = PostgresJobRepository(RecordingConnection())

    with pytest.raises(ValueError, match="unsupported job ordering"):
        repository.query_jobs(_context(), order_by="created_at; DROP TABLE omnix_jobs")


def test_patch_job_builds_scoped_metadata_and_status_mutation() -> None:
    connection = RecordingConnection()
    repository = PostgresJobRepository(connection)

    result = repository.patch_job(
        _context(),
        job_id="job:test",
        expected_statuses=("queued", "running"),
        status="paused",
        metadata_set={"paused": True},
        metadata_remove=("pause_requested",),
        available_at_now=True,
    )

    assert result is None
    sql, parameters = connection.calls[0]
    assert "UPDATE omnix_jobs AS jobs" in sql
    assert "jobs.status = ANY(%s)" in sql
    assert parameters == (
        "paused",
        ["pause_requested"],
        '{"paused":true}',
        "job:test",
        "workspace:test",
        ["queued", "running"],
    )
