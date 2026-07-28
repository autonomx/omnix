from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.execution_repositories import JobClaimConflict
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
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
            pool_max=8,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-execution-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_foreground_submissions, omnix_outbox_events, "
            "omnix_dead_letters, omnix_job_events, omnix_job_attempts, omnix_jobs, "
            "omnix_chat_messages, omnix_chat_sessions, omnix_memory_snapshot_items, "
            "omnix_memory_snapshots, omnix_memory_candidates, omnix_memory_events, "
            "omnix_memory_records, omnix_conversation_segments, "
            "omnix_character_versions, omnix_characters, omnix_asset_versions, "
            "omnix_assets, omnix_settings, omnix_secret_references, "
            "omnix_audit_events, omnix_idempotency_keys, "
            "omnix_workspace_memberships, omnix_workspaces, omnix_users CASCADE"
        )


def _create_job(work, context, job_id: str, *, priority: int = 0, max_attempts: int = 3):
    return work.jobs.create_job(
        context,
        {
            "id": job_id,
            "module": "image",
            "job_type": "image.generate",
            "resource_class": "gpu:image",
            "priority": priority,
            "max_attempts": max_attempts,
            "input_payload": {"prompt": "redacted-test"},
        },
    )


def test_skip_locked_claims_distinct_jobs_and_completes() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            _create_job(work, context, "job:low", priority=1)
            _create_job(work, context, "job:high", priority=10)
            work.commit()

        first_work = unit_of_work(database)
        second_work = unit_of_work(database)
        with first_work as first, second_work as second:
            first_claim = first.jobs.claim_next(
                context,
                worker_id="worker:a",
                resource_classes=["gpu:image"],
                lease_seconds=60,
            )
            second_claim = second.jobs.claim_next(
                context,
                worker_id="worker:b",
                resource_classes=["gpu:image"],
                lease_seconds=60,
            )
            assert first_claim is not None and second_claim is not None
            assert first_claim["id"] == "job:high"
            assert second_claim["id"] == "job:low"
            assert first_claim["id"] != second_claim["id"]
            first.commit()
            second.commit()

        with unit_of_work(database) as work:
            running = work.jobs.mark_running(
                context,
                job_id="job:high",
                worker_id="worker:a",
                lease_token=first_claim["lease_token"],
            )
            renewed = work.jobs.renew_lease(
                context,
                job_id="job:high",
                worker_id="worker:a",
                lease_token=first_claim["lease_token"],
                lease_seconds=120,
            )
            completed = work.jobs.complete(
                context,
                job_id="job:high",
                worker_id="worker:a",
                lease_token=first_claim["lease_token"],
                output_refs=[{"asset_id": "asset:output"}],
            )
            work.commit()
        assert running["status"] == "running"
        assert renewed["lease_expires_at"] > first_claim["lease_expires_at"]
        assert completed["status"] == "completed"
        assert completed["output_refs"] == [{"asset_id": "asset:output"}]

        with unit_of_work(database) as work:
            with pytest.raises(JobClaimConflict):
                work.jobs.complete(
                    context,
                    job_id="job:high",
                    worker_id="worker:a",
                    lease_token="wrong",
                    output_refs=[],
                )
            work.rollback()
    finally:
        database.close()


def test_record_only_job_transitions_without_worker_lease() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            work.jobs.create_job(
                context,
                {
                    "id": "job:foreground-record",
                    "module": "rpg",
                    "job_type": "rpg.turn.foreground_record",
                    "resource_class": "cpu",
                    "input_payload": {"command": "ask Bran about business"},
                    "metadata": {
                        "compat_contract": {
                            "compat": {"record_only": True},
                            "logs": [],
                        }
                    },
                },
            )
            running = work.jobs.mark_record_only_running(
                context,
                job_id="job:foreground-record",
            )
            completed = work.jobs.complete_record_only(
                context,
                job_id="job:foreground-record",
                output_refs=[{"session_id": "rpg:test"}],
            )
            work.commit()

        assert running["status"] == "running"
        assert running["lease_token"] is None
        assert completed["status"] == "completed"
        assert completed["output_refs"] == [{"session_id": "rpg:test"}]
    finally:
        database.close()


def test_job_retry_then_dead_letter() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            _create_job(work, context, "job:retry", max_attempts=2)
            work.commit()

        with unit_of_work(database) as work:
            first = work.jobs.claim_next(
                context,
                worker_id="worker:a",
                resource_classes=["gpu:image"],
            )
            assert first is not None
            retried = work.jobs.fail(
                context,
                job_id=first["id"],
                worker_id="worker:a",
                lease_token=first["lease_token"],
                error={"code": "temporary"},
            )
            work.commit()
        assert retried["status"] == "retrying"

        with unit_of_work(database) as work:
            second = work.jobs.claim_next(
                context,
                worker_id="worker:b",
                resource_classes=["gpu:image"],
            )
            assert second is not None
            failed = work.jobs.fail(
                context,
                job_id=second["id"],
                worker_id="worker:b",
                lease_token=second["lease_token"],
                error={"code": "permanent"},
            )
            work.commit()
        assert failed["status"] == "failed"
        with database.connection() as connection:
            dead_letters = int(
                connection.execute(
                    "SELECT COUNT(*) FROM omnix_dead_letters WHERE job_id = 'job:retry'"
                ).fetchone()[0]
            )
            attempts = int(
                connection.execute(
                    "SELECT COUNT(*) FROM omnix_job_attempts WHERE job_id = 'job:retry'"
                ).fetchone()[0]
            )
        assert dead_letters == 1
        assert attempts == 2
    finally:
        database.close()


def test_claim_reconciles_a_stale_attempt_record() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            _create_job(work, context, "job:stale-attempt", max_attempts=2)
            work.connection.execute(
                "INSERT INTO omnix_job_attempts "
                "(job_id, attempt, worker_id, lease_token, status) "
                "VALUES ('job:stale-attempt', 1, 'worker:stale', 'stale-token', 'leased')"
            )
            claimed = work.jobs.claim_next(
                context,
                worker_id="worker:current",
                resource_classes=["gpu:image"],
            )
            work.commit()

        assert claimed is not None
        assert claimed["id"] == "job:stale-attempt"
        assert claimed["attempt_count"] == 1
        with database.connection() as connection:
            attempt = connection.execute(
                "SELECT worker_id, lease_token, status FROM omnix_job_attempts "
                "WHERE job_id = 'job:stale-attempt' AND attempt = 1"
            ).fetchone()
        assert tuple(attempt) == ("worker:current", claimed["lease_token"], "leased")
    finally:
        database.close()


def test_cancel_queued_and_active_jobs() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            _create_job(work, context, "job:queued")
            _create_job(work, context, "job:active", priority=5)
            queued = work.jobs.request_cancel(context, "job:queued")
            claimed = work.jobs.claim_next(
                context,
                worker_id="worker:a",
                resource_classes=["gpu:image"],
            )
            assert claimed is not None and claimed["id"] == "job:active"
            active = work.jobs.request_cancel(context, "job:active")
            work.commit()
        assert queued["status"] == "canceled"
        assert active["status"] == "cancel_requested"
    finally:
        database.close()


def test_outbox_is_transactional_claimable_and_retryable() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with pytest.raises(RuntimeError):
            with unit_of_work(database) as work:
                work.outbox.append(
                    context,
                    aggregate_type="job",
                    aggregate_id="job:rollback",
                    event_type="job.created",
                    payload={"status": "queued"},
                )
                raise RuntimeError("rollback")
        with database.connection() as connection:
            assert int(connection.execute("SELECT COUNT(*) FROM omnix_outbox_events").fetchone()[0]) == 0

        with unit_of_work(database) as work:
            first_id = work.outbox.append(
                context,
                aggregate_type="job",
                aggregate_id="job:1",
                event_type="job.created",
                payload={"status": "queued"},
                ordering_key="job:1",
            )
            second_id = work.outbox.append(
                context,
                aggregate_type="asset",
                aggregate_id="asset:1",
                event_type="asset.created",
                payload={"type": "image"},
            )
            work.commit()

        with unit_of_work(database) as work:
            batch = work.outbox.claim_batch(consumer_id="events:a", limit=10)
            assert [item["id"] for item in batch] == [first_id, second_id]
            assert work.outbox.mark_retry(
                event_id=first_id,
                claim_token=batch[0]["claim_token"],
                error="temporary",
            ) is True
            assert work.outbox.mark_published(
                event_id=second_id,
                claim_token=batch[1]["claim_token"],
            ) is True
            work.commit()

        with unit_of_work(database) as work:
            retry_batch = work.outbox.claim_batch(consumer_id="events:b", limit=10)
            assert [item["id"] for item in retry_batch] == [first_id]
            assert retry_batch[0]["attempt_count"] == 2
            assert work.outbox.mark_published(
                event_id=first_id,
                claim_token=retry_batch[0]["claim_token"],
            ) is True
            work.commit()
    finally:
        database.close()


def test_foreground_submission_reuses_committed_result() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            job = _create_job(work, context, "job:foreground")
            claim = work.foreground_submissions.claim(
                context,
                session_id="session:rpg",
                submission_id="submission:1",
                lease_seconds=60,
            )
            assert claim["owner"] is True
            assert claim["claim_token"]
            assert work.foreground_submissions.attach_job(
                context,
                session_id="session:rpg",
                submission_id="submission:1",
                claim_token=claim["claim_token"],
                job_id=job["id"],
            ) is True
            assert work.foreground_submissions.start_execution(
                context,
                session_id="session:rpg",
                submission_id="submission:1",
                claim_token=claim["claim_token"],
            ) is True
            assert work.foreground_submissions.complete(
                context,
                session_id="session:rpg",
                submission_id="submission:1",
                claim_token=claim["claim_token"],
                interaction_id="interaction:1",
                response={"ok": True, "interaction_id": "interaction:1"},
            ) is True
            work.commit()

        with unit_of_work(database) as work:
            replay = work.foreground_submissions.claim(
                context,
                session_id="session:rpg",
                submission_id="submission:1",
            )
            work.rollback()
        assert replay["owner"] is False
        assert replay["status"] == "completed"
        assert replay["interaction_id"] == "interaction:1"
        assert replay["response"] == {"ok": True, "interaction_id": "interaction:1"}
    finally:
        database.close()


def test_expired_pre_execution_submission_can_be_reclaimed() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            first = work.foreground_submissions.claim(
                context,
                session_id="session:rpg",
                submission_id="submission:expired",
                lease_seconds=60,
            )
            work.commit()
        with database.transaction() as connection:
            connection.execute(
                "UPDATE omnix_rpg_foreground_submissions "
                "SET lease_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second' "
                "WHERE workspace_id = %s AND session_id = %s AND submission_id = %s",
                (context.workspace_id, "session:rpg", "submission:expired"),
            )
        with unit_of_work(database) as work:
            reclaimed = work.foreground_submissions.claim(
                context,
                session_id="session:rpg",
                submission_id="submission:expired",
                lease_seconds=60,
            )
            work.commit()
        assert reclaimed["owner"] is True
        assert reclaimed["claim_token"] != first["claim_token"]
    finally:
        database.close()
