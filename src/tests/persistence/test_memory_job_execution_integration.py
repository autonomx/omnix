"""Memory lease ownership and atomic results over disposable PostgreSQL."""
from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.assistant_memory import jobs
from app.jobs import CompleteJobRequest, CreateJobRequest, JobStatus, ResourceClass
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.execution_repositories import JobClaimConflict
from app.persistence.job_runtime_compat import PostgresJobStoreAdapter
from app.assistant_memory.persistence.memory_job_execution import MemoryJobExecution

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="requires disposable PostgreSQL test database",
)


@pytest.fixture
def runtime():
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_max=8,
    ))
    store = PostgresJobStoreAdapter(database)
    workspace_id = f"workspace:memory-lease-test:{uuid.uuid4().hex}"
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO omnix_workspaces (id, name, created_by) VALUES (%s, 'Memory lease test', %s)",
            (workspace_id, store.context.user_id),
        )
    store.context = replace(store.context, workspace_id=workspace_id)
    try:
        yield database, store
    finally:
        with database.transaction() as connection:
            connection.execute("DELETE FROM omnix_workspaces WHERE id = %s", (workspace_id,))
        database.close()


def memory_job(store):
    return store.create_job(jobs.create_memory_suggestion_job_request("chat:test", "msg:test"))


def test_processing_claims_and_completes_missing_session(runtime, monkeypatch):
    _, store = runtime
    monkeypatch.setenv("OMNIX_COMPANION_ROLLOUT_STAGE", "review_required")
    job = memory_job(store)
    result = jobs.process_memory_suggestion_job(
        job, chat_store=SimpleNamespace(get_session=lambda _: None), job_store=store,
    )
    assert result.skipped_reasons == ["session_missing"]
    assert store.get_job(job.id).status == JobStatus.COMPLETED
    assert [event.event_type for event in store.list_events(job.id)] == [
        "job.created", "job.claimed", "job.running", "job.completed",
    ]
    repeated = jobs.process_memory_suggestion_job(
        job, chat_store=SimpleNamespace(get_session=lambda _: pytest.fail("duplicate extraction")),
        job_store=store,
    )
    assert repeated.skipped_reasons == ["job_not_claimable"]


def test_logical_job_owner_is_separate_from_trusted_postgres_user(runtime):
    database, store = runtime
    job = memory_job(store)
    assert job.owner_id == "chat:test"
    with database.connection() as connection:
        assert connection.execute("SELECT owner_user_id FROM omnix_jobs WHERE id = %s", (job.id,)).fetchone()[0] == store.context.user_id


def test_concurrent_enqueue_uses_durable_identity_without_recent_job_scan(runtime, monkeypatch):
    _, store = runtime
    monkeypatch.setenv("OMNIX_COMPANION_ROLLOUT_STAGE", "review_required")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED", "1")
    monkeypatch.setattr(store, "list_jobs", lambda: pytest.fail("bounded recent-job scan"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: jobs.enqueue_memory_suggestion_job(
            "chat:test", "msg:test", job_store=store,
        ), range(2)))
    assert results[0].id == results[1].id
    assert len(store.list_events(results[0].id)) == 1
    with MemoryJobExecution(store, results[0]) as execution:
        with execution.write_result():
            execution.complete_job(execution.job.id, CompleteJobRequest(logs=[{"event": "completed"}]))
    repeated = jobs.enqueue_memory_suggestion_job("chat:test", "msg:test", job_store=store)
    assert repeated.status == JobStatus.COMPLETED
    assert repeated.logs == [{"event": "completed"}]


@pytest.mark.parametrize("fail_completion", [False, True])
def test_derived_candidate_and_job_result_commit_together(runtime, monkeypatch, fail_completion):
    database, store = runtime
    from app.assistant_memory.owner_service import OwnerAwareMemoryService
    from app.chat.models import ChatMessage, ChatSession
    from app.assistant_memory.persistence.owner_memory_compat import PostgresOwnerAwareMemoryRepository

    monkeypatch.setenv("OMNIX_COMPANION_ROLLOUT_STAGE", "review_required")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED", "1")
    repository = PostgresOwnerAwareMemoryRepository(database)
    repository.context = store.context
    service = OwnerAwareMemoryService(repository)
    session = ChatSession(
        id="chat:test", title="Memory lease test", created_at="2026-09-26T00:00:00Z",
        updated_at="2026-09-26T00:00:00Z", message_count=1,
        messages=[ChatMessage(id="msg:test", role="user", content="I prefer concise summaries",
                              created_at="2026-09-26T00:00:00Z")],
    )
    job = memory_job(store)
    if fail_completion:
        monkeypatch.setattr(MemoryJobExecution, "complete_job",
                            lambda *_: (_ for _ in ()).throw(RuntimeError("completion failed")))
        with pytest.raises(RuntimeError, match="completion failed"):
            jobs.process_memory_suggestion_job(job, chat_store=SimpleNamespace(get_session=lambda _: session),
                                               memory_service=service, job_store=store)
    else:
        result = jobs.process_memory_suggestion_job(job, chat_store=SimpleNamespace(get_session=lambda _: session),
                                                    memory_service=service, job_store=store)
        assert len(result.candidate_ids) == 1
    with database.connection() as connection:
        count = connection.execute("SELECT COUNT(*) FROM omnix_memory_candidates WHERE workspace_id = %s",
                                   (store.context.workspace_id,)).fetchone()[0]
    assert count == (0 if fail_completion else 1)
    assert store.get_job(job.id).status == (JobStatus.RETRYING if fail_completion else JobStatus.COMPLETED)


def test_targeted_claim_does_not_take_unrelated_cpu_work(runtime):
    _, store = runtime
    unrelated = store.create_job(CreateJobRequest(
        module="test", type="test.cpu", resource_class=ResourceClass.CPU, priority=100,
    ))
    job = memory_job(store)
    with MemoryJobExecution(store, job) as execution:
        assert execution.claimed
        assert execution.job.id == job.id
        with execution.write_result():
            execution.complete_job(job.id, CompleteJobRequest())
    assert store.get_job(unrelated.id).status == JobStatus.QUEUED


def test_only_one_concurrent_execution_can_claim(runtime):
    _, store = runtime
    job = memory_job(store)
    barrier = threading.Barrier(2)

    def attempt():
        with MemoryJobExecution(store, job) as execution:
            barrier.wait(timeout=10)
            if execution.claimed:
                with execution.write_result():
                    execution.complete_job(job.id, CompleteJobRequest())
            return execution.claimed

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == [False, True]
    assert store.get_job(job.id).status == JobStatus.COMPLETED


def test_expired_attempt_cannot_complete_or_fail_new_owner(runtime):
    database, store = runtime
    job = memory_job(store)
    with MemoryJobExecution(store, job) as stale:
        with database.transaction() as connection:
            connection.execute(
                "UPDATE omnix_jobs SET lease_expires_at = clock_timestamp() - INTERVAL '1 second' WHERE id = %s",
                (job.id,),
            )
        with MemoryJobExecution(store, job) as current:
            assert current.claimed
            assert current.lease_token != stale.lease_token
            with pytest.raises(JobClaimConflict):
                with stale.write_result():
                    stale.complete_job(job.id, CompleteJobRequest())
            # A late failure handler is fenced by the original token too.
            stale.__exit__(RuntimeError, RuntimeError("late provider failure"), None)
            assert store.get_job(job.id).lease.token == current.lease_token
            with current.write_result():
                current.complete_job(job.id, CompleteJobRequest())
    assert store.get_job(job.id).status == JobStatus.COMPLETED


def test_failed_result_rolls_back_domain_writes_and_retries(runtime):
    database, store = runtime
    job = memory_job(store)
    with pytest.raises(RuntimeError, match="consolidation failed"):
        with MemoryJobExecution(store, job) as execution:
            with execution.write_result():
                with database.transaction() as connection:
                    connection.execute("UPDATE omnix_workspaces SET name = 'uncommitted' WHERE id = %s",
                                       (store.context.workspace_id,))
                raise RuntimeError("consolidation failed")
    assert store.get_job(job.id).status == JobStatus.RETRYING
    with database.connection() as connection:
        assert connection.execute("SELECT name FROM omnix_workspaces WHERE id = %s",
                                  (store.context.workspace_id,)).fetchone()[0] == "Memory lease test"


def test_expiry_during_result_transaction_rolls_back(runtime):
    database, store = runtime
    job = memory_job(store)
    with MemoryJobExecution(store, job) as execution:
        with pytest.raises(JobClaimConflict):
            with execution.write_result():
                with database.transaction() as connection:
                    connection.execute("UPDATE omnix_workspaces SET name = 'uncommitted' WHERE id = %s",
                                       (store.context.workspace_id,))
                    connection.execute(
                        "UPDATE omnix_jobs SET lease_expires_at = clock_timestamp() - INTERVAL '1 second' WHERE id = %s",
                        (job.id,),
                    )
                execution.complete_job(job.id, CompleteJobRequest())
        with execution.write_result():
            execution.complete_job(job.id, CompleteJobRequest())
    with database.connection() as connection:
        assert connection.execute("SELECT name FROM omnix_workspaces WHERE id = %s",
                                  (store.context.workspace_id,)).fetchone()[0] == "Memory lease test"


def test_cancellation_prevents_derived_memory_commit(runtime):
    database, store = runtime
    job = memory_job(store)
    with MemoryJobExecution(store, job) as execution:
        from app.jobs import CancelJobRequest
        store.cancel_job(job.id, CancelJobRequest())
        with pytest.raises(JobClaimConflict):
            with execution.write_result():
                pytest.fail("canceled job reached memory writes")
    assert store.get_job(job.id).status == JobStatus.CANCELED


def test_lease_renews_during_provider_work(runtime, monkeypatch):
    database, store = runtime
    monkeypatch.setattr(MemoryJobExecution, "renewal_seconds", 0.02)
    job = memory_job(store)
    with MemoryJobExecution(store, job) as execution:
        with database.transaction() as connection:
            connection.execute(
                "UPDATE omnix_jobs SET lease_expires_at = clock_timestamp() + INTERVAL '2 seconds' WHERE id = %s",
                (job.id,),
            )
        # Wait on durable evidence instead of assuming thread scheduling.
        import time
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with database.connection() as connection:
                renewed = connection.execute(
                    "SELECT lease_expires_at > clock_timestamp() + INTERVAL '20 seconds' FROM omnix_jobs WHERE id = %s",
                    (job.id,),
                ).fetchone()[0]
            if renewed:
                break
            time.sleep(0.02)
        assert renewed
        with execution.write_result():
            execution.complete_job(job.id, CompleteJobRequest())
