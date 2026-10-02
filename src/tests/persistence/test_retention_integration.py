"""Retention deletes eligible rows and keeps the rest (WP-5.2 acceptance)."""
from __future__ import annotations

import json
import os
import uuid

import psycopg
import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.retention import RetentionWorker
from tests.support.database import admin_database_url

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.xdist_group("retention"),
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]

WORKSPACE = "workspace:local"


@pytest.fixture
def database():
    db = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=4))
    ensure_local_identity(db)
    try:
        yield db
    finally:
        db.close()


def _admin():
    return psycopg.connect(admin_database_url(), autocommit=True)


def _job(admin, status: str, *, days_ago: int, events: int = 2) -> str:
    job_id = f"job:retention:{uuid.uuid4().hex}"
    admin.execute(
        """INSERT INTO omnix_jobs (id, workspace_id, module, job_type, resource_class, status, completed_at, updated_at)
           VALUES (%s, %s, 'test', 'retention.probe', 'cpu', %s,
                   CASE WHEN %s IN ('completed', 'failed', 'canceled') THEN now() - make_interval(days => %s) END,
                   now() - make_interval(days => %s))""",
        (job_id, WORKSPACE, status, status, days_ago, days_ago),
    )
    for index in range(events):
        admin.execute(
            """INSERT INTO omnix_job_events (workspace_id, job_id, event_type, created_at)
               VALUES (%s, %s, 'progress', now())""",
            (WORKSPACE, job_id),
        )
    return job_id


def _exists(admin, table: str, column: str, value: str) -> bool:
    return admin.execute(f"SELECT 1 FROM {table} WHERE {column} = %s", (value,)).fetchone() is not None


def test_terminal_jobs_go_with_their_events_and_live_ones_stay(database) -> None:
    with _admin() as admin:
        old_done = _job(admin, "completed", days_ago=40)
        old_running = _job(admin, "running", days_ago=40)
        recent_done = _job(admin, "failed", days_ago=2)
    RetentionWorker(database, batch_size=1).run_once()
    with _admin() as admin:
        assert not _exists(admin, "omnix_jobs", "id", old_done)
        assert not _exists(admin, "omnix_job_events", "job_id", old_done)
        assert _exists(admin, "omnix_jobs", "id", old_running)
        assert _exists(admin, "omnix_jobs", "id", recent_done)


def test_agent_run_noise_is_dropped_but_milestones_and_evidence_are_kept(database) -> None:
    run_id = f"retention-{uuid.uuid4().hex[:10]}"
    live_run = f"retention-live-{uuid.uuid4().hex[:10]}"
    with _admin() as admin:
        for rid, status in ((run_id, "completed"), (live_run, "running")):
            admin.execute(
                """INSERT INTO omnix_agent_runs (workspace_id, run_id, spec, status, completed_at, updated_at)
                   VALUES (%s, %s, '{}'::jsonb, %s, now() - interval '40 days', now() - interval '40 days')""",
                (WORKSPACE, rid, status),
            )
            for sequence, event_type in enumerate(("model.message", "tool.output", "evidence.receipt", "run.completed"), start=1):
                admin.execute(
                    """INSERT INTO omnix_agent_run_events (workspace_id, run_id, sequence, event_id, event_type)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (WORKSPACE, rid, sequence, uuid.uuid4().hex, event_type),
                )
    RetentionWorker(database).run_once()
    with _admin() as admin:
        kept = {row[0] for row in admin.execute(
            "SELECT event_type FROM omnix_agent_run_events WHERE run_id = %s", (run_id,)).fetchall()}
        live = admin.execute("SELECT count(*) FROM omnix_agent_run_events WHERE run_id = %s", (live_run,)).fetchone()[0]
    assert kept == {"evidence.receipt", "run.completed"}
    assert live == 4


def _deleted_rows_counted(record_type: str) -> float:
    from app.observability.metrics import exposition

    prefix = f'omnix_retention_rows_deleted_total{{record_type="{record_type}"}} '
    lines = [line for line in exposition()[0].decode().splitlines() if line.startswith(prefix)]
    return float(lines[0].split()[-1]) if lines else 0.0


def test_expired_sessions_and_stopped_nodes_are_removed(database) -> None:
    expired, active = f"session-{uuid.uuid4().hex}", f"session-{uuid.uuid4().hex}"
    stopped, live = f"node-{uuid.uuid4().hex}", f"node-{uuid.uuid4().hex}"
    with _admin() as admin:
        for session_id, offset in ((expired, "-10 days"), (active, "+1 day")):
            admin.execute(
                """INSERT INTO omnix_auth_sessions (id, user_id, workspace_id, auth_method, csrf_secret, expires_at, absolute_expires_at)
                   VALUES (%s, 'user:local', %s, 'local', 'x', now() + %s::interval, now() + %s::interval)""",
                (session_id, WORKSPACE, offset, offset),
            )
        admin.execute(
            """INSERT INTO omnix_runtime_nodes (id, node_type, software_version, status, lease_expires_at, stopped_at)
               VALUES (%s, 'worker', 'test', 'stopped', now() - interval '10 days', now() - interval '10 days'),
                      (%s, 'worker', 'test', 'active', now() + interval '1 minute', NULL)""",
            (stopped, live),
        )
    before = _deleted_rows_counted("auth_sessions")
    report = RetentionWorker(database).run_once()
    assert _deleted_rows_counted("auth_sessions") - before == report.deleted["auth_sessions"] >= 1
    with _admin() as admin:
        assert not _exists(admin, "omnix_auth_sessions", "id", expired)
        assert _exists(admin, "omnix_auth_sessions", "id", active)
        assert not _exists(admin, "omnix_runtime_nodes", "id", stopped)
        assert _exists(admin, "omnix_runtime_nodes", "id", live)
        admin.execute("DELETE FROM omnix_runtime_nodes WHERE id = %s", (live,))


def test_audit_retention_only_runs_on_the_maintenance_path(database) -> None:
    marker = f"retention-audit-{uuid.uuid4().hex}"
    with _admin() as admin:
        admin.execute(
            """INSERT INTO omnix_audit_events (workspace_id, aggregate_type, aggregate_id, action, created_at)
               VALUES (%s, 'test', %s, 'settings.update', now() - interval '400 days')""",
            (WORKSPACE, marker),
        )
    report = RetentionWorker(database).run_once()
    assert "audit_events" in report.skipped
    with _admin() as admin:
        assert _exists(admin, "omnix_audit_events", "aggregate_id", marker)
    # Maintenance runs from the operator CLI with the owner role; the runtime
    # role cannot delete audit rows (migration 0107).
    owner = PostgresDatabase(DatabaseSettings(url=admin_database_url(), pool_min=1, pool_max=2))
    try:
        RetentionWorker(owner).run_once(include_maintenance=True)
    finally:
        owner.close()
    with _admin() as admin:
        assert not _exists(admin, "omnix_audit_events", "aggregate_id", marker)
        run = admin.execute(
            "SELECT status, deleted_counts FROM omnix_lifecycle_cleanup_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert run[0] == "completed" and run[1]["audit_events"] >= 1


def test_published_outbox_growth_is_bounded(database) -> None:
    """N days of published events: after retention only the window remains."""
    aggregate = f"retention-outbox-{uuid.uuid4().hex}"
    with _admin() as admin:
        for day in range(30):
            admin.execute(
                """INSERT INTO omnix_outbox_events (workspace_id, aggregate_type, aggregate_id, event_type, payload,
                                                     status, published_at, created_at)
                   VALUES (%s, 'test', %s, 'retention.probe', %s::jsonb, 'published',
                           now() - make_interval(days => %s), now() - make_interval(days => %s))""",
                (WORKSPACE, aggregate, json.dumps({"day": day}), day, day),
            )
    RetentionWorker(database, batch_size=4).run_once()
    with _admin() as admin:
        remaining = admin.execute(
            "SELECT count(*) FROM omnix_outbox_events WHERE aggregate_id = %s", (aggregate,)
        ).fetchone()[0]
    assert remaining == 7  # published within the 7-day policy (days 0-6)
