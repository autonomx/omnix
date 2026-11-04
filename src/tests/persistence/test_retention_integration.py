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


def test_a_job_a_record_still_needs_stays_and_the_rest_go(database) -> None:
    # Real: an audiobook export's foreign key failed every run for two weeks, and nothing after jobs was cleaned.
    export_id = f"export:retention:{uuid.uuid4().hex}"
    holder = f"retention_holder_{uuid.uuid4().hex[:10]}"
    with _admin() as admin:
        held_by_export = _job(admin, "completed", days_ago=400)
        held_by_new_table = _job(admin, "failed", days_ago=400)
        unheld = _job(admin, "completed", days_ago=400)
        # A table no code has heard of: what holds a job is read from the catalog.
        admin.execute(f"CREATE TABLE {holder} (job_ref TEXT NOT NULL REFERENCES omnix_jobs(id))")
        admin.execute(f"INSERT INTO {holder} (job_ref) VALUES (%s)", (held_by_new_table,))
        admin.execute(f"GRANT SELECT ON {holder} TO PUBLIC")
        # The export's own references and its immutability are not this test's subject.
        admin.execute("SET session_replication_role = replica")
        admin.execute(
            """INSERT INTO omnix_audiobook_exports
                   (id, workspace_id, project_id, source_revision_id, job_id, format, manifest, manifest_hash, output_asset_id)
               VALUES (%s, %s, 'project', 'revision', %s, 'wav', '{}'::jsonb, %s, %s)""",
            (export_id, WORKSPACE, held_by_export, "0" * 64, export_id),
        )
        admin.execute("SET session_replication_role = DEFAULT")

    try:
        report = RetentionWorker(database).run_once()

        assert report.failed == []
        with _admin() as admin:
            assert _exists(admin, "omnix_jobs", "id", held_by_export)
            assert _exists(admin, "omnix_job_events", "job_id", held_by_export)  # kept whole
            assert _exists(admin, "omnix_jobs", "id", held_by_new_table)
            assert not _exists(admin, "omnix_jobs", "id", unheld)
    finally:
        with _admin() as admin:
            admin.execute(f"DROP TABLE {holder}")
            admin.execute("SET session_replication_role = replica")
            admin.execute("DELETE FROM omnix_audiobook_exports WHERE id = %s", (export_id,))
            admin.execute("SET session_replication_role = DEFAULT")


def test_one_policy_failing_does_not_stop_the_others(database, monkeypatch) -> None:
    from app.persistence import retention

    def broken(_connection, _days, _batch):
        raise RuntimeError("this policy is broken")

    real_handler_for = retention.handler_for
    # agent_run_events comes first of all, so everything else runs after the failure.
    monkeypatch.setattr(
        retention, "handler_for", lambda record_type: broken if record_type == "agent_run_events" else real_handler_for(record_type),
    )
    with _admin() as admin:
        stale = _job(admin, "completed", days_ago=400)

    with pytest.raises(RuntimeError, match="this policy is broken"):
        RetentionWorker(database).run_once()

    with _admin() as admin:
        assert not _exists(admin, "omnix_jobs", "id", stale)
        status, error = admin.execute(
            "SELECT status, error FROM omnix_lifecycle_cleanup_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    # It still reads as failed, so a broken policy cannot go unnoticed.
    assert status == "failed"
    assert "this policy is broken" in error


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


def test_diagnostics_report_the_latest_run_without_its_error_text(database) -> None:
    from app.persistence.retention import latest_cleanup_run

    with _admin() as admin:
        run_id = admin.execute(
            """INSERT INTO omnix_lifecycle_cleanup_runs (status, completed_at, deleted_counts, error)
               VALUES ('failed', now(), '{"jobs": 3}'::jsonb,
                       'UndefinedTable: relation "omnix_private_table" does not exist')
               RETURNING id"""
        ).fetchone()[0]
    try:
        with database.transaction() as connection:
            run = latest_cleanup_run(connection)
    finally:
        with _admin() as admin:
            admin.execute("DELETE FROM omnix_lifecycle_cleanup_runs WHERE id = %s", (run_id,))

    assert run["status"] == "failed" and run["deleted"] == {"jobs": 3}
    assert run["error_class"] == "UndefinedTable"
    assert "omnix_private_table" not in str(run)


def _campaign_with_snapshots(admin, revisions: range, *, days_ago: int) -> str:
    from app.runtime.tenant_context import LOCAL_USER_ID

    campaign_id = f"campaign:retention:{uuid.uuid4().hex}"
    admin.execute(
        """INSERT INTO omnix_rpg_campaigns (id, workspace_id, owner_user_id, title, revision, state_jsonb,
                                             state_hash, engine_version, schema_version, seed)
           VALUES (%s, %s, %s, 'Retention', %s, '{}'::jsonb, %s, 'test', 'test', 'seed')""",
        (campaign_id, WORKSPACE, LOCAL_USER_ID, revisions[-1], "0" * 64),
    )
    for revision in revisions:
        admin.execute(
            """INSERT INTO omnix_rpg_snapshots (id, workspace_id, campaign_id, revision, snapshot_jsonb, state_hash,
                                                 engine_version, schema_version, created_at)
               VALUES (%s, %s, %s, %s, '{}'::jsonb, %s, 'test', 'test', now() - make_interval(days => %s))""",
            (f"snapshot:{campaign_id}:{revision}", WORKSPACE, campaign_id, revision, "0" * 64, days_ago),
        )
    return campaign_id


def _snapshot_revisions(admin, campaign_id: str) -> list[int]:
    rows = admin.execute(
        "SELECT revision FROM omnix_rpg_snapshots WHERE campaign_id = %s ORDER BY revision", (campaign_id,)
    ).fetchall()
    return [int(row[0]) for row in rows]


def test_rpg_snapshots_keep_the_newest_twenty_and_every_hundredth_revision(database) -> None:
    with _admin() as admin:
        long_game = _campaign_with_snapshots(admin, range(1, 251), days_ago=3)
        short_game = _campaign_with_snapshots(admin, range(1, 6), days_ago=3)
        recent_game = _campaign_with_snapshots(admin, range(1, 31), days_ago=0)
    try:
        report = RetentionWorker(database, batch_size=50).run_once()
        with _admin() as admin:
            assert _snapshot_revisions(admin, long_game) == [100, 200, *range(231, 251)]
            assert _snapshot_revisions(admin, short_game) == [1, 2, 3, 4, 5]
            # Inside the one-day grace period nothing goes, even past the newest 20.
            assert _snapshot_revisions(admin, recent_game) == list(range(1, 31))
        assert report.deleted["rpg_snapshots"] >= 228
    finally:
        with _admin() as admin:
            for campaign_id in (long_game, short_game, recent_game):
                admin.execute("DELETE FROM omnix_rpg_campaigns WHERE id = %s", (campaign_id,))


def test_pinned_rpg_snapshots_are_never_deleted(database) -> None:
    with _admin() as admin:
        campaign_id = _campaign_with_snapshots(admin, range(1, 61), days_ago=3)
        # A pre-upgrade backup and an upcast boundary (RQ-1.7), both outside the newest 20.
        admin.execute(
            "UPDATE omnix_rpg_snapshots SET pinned = true WHERE campaign_id = %s AND revision IN (7, 8)",
            (campaign_id,),
        )
    try:
        RetentionWorker(database, batch_size=50).run_once()
        with _admin() as admin:
            assert _snapshot_revisions(admin, campaign_id) == [7, 8, *range(41, 61)]
    finally:
        with _admin() as admin:
            admin.execute("DELETE FROM omnix_rpg_campaigns WHERE id = %s", (campaign_id,))


def _campaign_with_turns(admin, *, revision: int, status: str = "active", days_ago: int = 0) -> str:
    from app.runtime.tenant_context import LOCAL_USER_ID

    campaign_id = f"campaign:retention:{uuid.uuid4().hex}"
    admin.execute(
        """INSERT INTO omnix_rpg_campaigns (id, workspace_id, owner_user_id, title, revision, state_jsonb,
                                             state_hash, engine_version, schema_version, seed, status, updated_at)
           VALUES (%s, %s, %s, 'Retention', %s, '{}'::jsonb, %s, 'test', 'test', 'seed', %s,
                   now() - make_interval(days => %s))""",
        (campaign_id, WORKSPACE, LOCAL_USER_ID, revision, "0" * 64, status, days_ago),
    )
    admin.execute(
        """INSERT INTO omnix_rpg_turns (id, workspace_id, campaign_id, sequence, submission_id, expected_revision,
                                         resulting_revision, command_jsonb, state_hash_before, state_hash_after,
                                         engine_version, schema_version, interaction_id, compact_response)
           SELECT %s || ':' || n, %s, %s, n, 'submit:' || n, n - 1, n, '{}'::jsonb, %s, %s,
                  'test', 'test', 'interaction:' || %s || ':' || n, '{}'::jsonb
             FROM generate_series(1, %s) AS n""",
        (f"turn:{campaign_id}", WORKSPACE, campaign_id, "0" * 64, "0" * 64, campaign_id, revision),
    )
    admin.execute(
        """INSERT INTO omnix_rpg_snapshots (id, workspace_id, campaign_id, revision, snapshot_jsonb, state_hash,
                                             engine_version, schema_version, created_at)
           SELECT %s || ':' || n, %s, %s, n, '{}'::jsonb, %s, 'test', 'test', now() - make_interval(days => 3)
             FROM generate_series(20, %s, 20) AS n""",
        (f"snapshot:{campaign_id}", WORKSPACE, campaign_id, "0" * 64, revision),
    )
    return campaign_id


def _turn_revisions(admin, campaign_id: str) -> tuple[int, int, int]:
    row = admin.execute(
        "SELECT min(resulting_revision), max(resulting_revision), count(*) FROM omnix_rpg_turns WHERE campaign_id = %s",
        (campaign_id,),
    ).fetchone()
    return int(row[0] or 0), int(row[1] or 0), int(row[2])


def test_a_long_campaign_keeps_its_newest_thousand_turns_behind_a_pinned_snapshot(database) -> None:
    with _admin() as admin:
        long_game = _campaign_with_turns(admin, revision=5_210)
        under_threshold = _campaign_with_turns(admin, revision=4_990)
    try:
        report = RetentionWorker(database, batch_size=50).run_once()
        with _admin() as admin:
            # The newest snapshot at least 1,000 revisions old is 4,200: replay starts there.
            assert _turn_revisions(admin, long_game) == (4_201, 5_210, 1_010)
            pinned = admin.execute(
                "SELECT revision FROM omnix_rpg_snapshots WHERE campaign_id = %s AND pinned", (long_game,)
            ).fetchall()
            assert [int(row[0]) for row in pinned] == [4_200]
            assert min(_snapshot_revisions(admin, long_game)) == 4_200
            assert _turn_revisions(admin, under_threshold) == (1, 4_990, 4_990)
        assert report.deleted["rpg_turn_compaction"] >= 4_200
    finally:
        with _admin() as admin:
            for campaign_id in (long_game, under_threshold):
                admin.execute("DELETE FROM omnix_rpg_campaigns WHERE id = %s", (campaign_id,))


def test_a_deleted_campaign_goes_with_its_turns_after_thirty_days(database) -> None:
    with _admin() as admin:
        deleted_long_ago = _campaign_with_turns(admin, revision=40, status="archived", days_ago=31)
        deleted_recently = _campaign_with_turns(admin, revision=40, status="archived", days_ago=3)
        played_long_ago = _campaign_with_turns(admin, revision=40, days_ago=90)
    try:
        RetentionWorker(database, batch_size=50).run_once()
        with _admin() as admin:
            assert not _exists(admin, "omnix_rpg_campaigns", "id", deleted_long_ago)
            assert _turn_revisions(admin, deleted_long_ago)[2] == 0
            assert _snapshot_revisions(admin, deleted_long_ago) == []
            assert _exists(admin, "omnix_rpg_campaigns", "id", deleted_recently)
            assert _exists(admin, "omnix_rpg_campaigns", "id", played_long_ago)
            assert _turn_revisions(admin, played_long_ago)[2] == 40
    finally:
        with _admin() as admin:
            for campaign_id in (deleted_long_ago, deleted_recently, played_long_ago):
                admin.execute("DELETE FROM omnix_rpg_campaigns WHERE id = %s", (campaign_id,))
