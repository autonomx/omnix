"""Concurrent gateway recovery over real PostgreSQL, using isolated test workspaces."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
import threading
import uuid

import pytest

from app.jobs.models import (
    CompleteJobRequest,
    CreateJobRequest,
    FailJobRequest,
    JobStatus,
    ResourceClass,
)
from app.chat.generation_jobs import recover_abandoned_chat_generation_jobs
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.execution_repositories import JobClaimConflict
from app.persistence.gateway_runtime import GatewayRuntimeOwner
from app.persistence.job_runtime_compat import PostgresJobStoreAdapter
from app.persistence.repositories import PostgresIdentityRepository
from app.persistence.runtime_coordination import (
    PostgresRuntimeCoordinationRepository,
    RuntimeNodeConflict,
)
from app.persistence.unit_of_work import unit_of_work

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="requires disposable PostgreSQL test database",
)


@pytest.fixture
def runtime():
    database = PostgresDatabase(
        DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_max=8)
    )
    seed = PostgresJobStoreAdapter(database)
    workspaces = []

    def new_store():
        workspace_id = f"workspace:chat-ownership-test:{uuid.uuid4().hex}"
        with database.transaction() as connection:
            connection.execute(
                "INSERT INTO omnix_workspaces (id, name, created_by) VALUES (%s, 'Chat ownership test', %s)",
                (workspace_id, seed.context.user_id),
            )
            connection.execute(
                "INSERT INTO omnix_workspace_memberships (id, workspace_id, user_id, roles) VALUES (%s, %s, %s, %s)",
                (
                    f"membership:{uuid.uuid4().hex}",
                    workspace_id,
                    seed.context.user_id,
                    ["owner", "admin", "member"],
                ),
            )
            context = PostgresIdentityRepository(connection).load_context(
                user_id=seed.context.user_id, workspace_id=workspace_id
            )
        workspaces.append(workspace_id)
        store = PostgresJobStoreAdapter(database)
        store.context = context
        return store

    store = new_store()
    try:
        yield database, store, new_store
    finally:
        with database.transaction() as connection:
            for workspace_id in workspaces:
                connection.execute(
                    "DELETE FROM omnix_runtime_nodes WHERE metadata ->> 'workspace_id' = %s",
                    (workspace_id,),
                )
                connection.execute(
                    "DELETE FROM omnix_workspaces WHERE id = %s", (workspace_id,)
                )
        database.close()


def owned_store(database, store):
    owner = GatewayRuntimeOwner(database, store.context.workspace_id)
    owner.register()
    store.chat_execution_owner = owner
    return owner


def chat_job(store, **compat):
    return store.create_job(
        CreateJobRequest(
            module="chatbot",
            type="chat.generate",
            resource_class=ResourceClass.GPU_LLM,
            input_payload={},
            compat={"inline_execution": True, **compat},
        )
    )


def test_global_event_tail_is_scoped_to_the_current_workspace(runtime):
    _, store, new_store = runtime
    foreign = new_store()
    assert store.latest_event_id() == 0
    first = chat_job(store)
    tail = store.latest_event_id()
    assert tail > 0
    chat_job(foreign)
    assert foreign.latest_event_id() > tail
    assert store.latest_event_id() == tail
    assert [event.job_id for event in store.list_events(after_id=0)] == [first.id]


def test_second_gateway_preserves_live_owner_and_cannot_complete_its_job(runtime):
    database, first, _ = runtime
    owner = owned_store(database, first)
    second = PostgresJobStoreAdapter(database)
    second.context = first.context
    second_owner = owned_store(database, second)
    job = chat_job(first)
    first.mark_running(job.id)
    assert job.compat["execution_owner"] == owner.node_id
    assert recover_abandoned_chat_generation_jobs(None, second) == 0
    assert first.get_job(job.id).status == JobStatus.RUNNING
    with pytest.raises(JobClaimConflict):
        second.complete_job(job.id, CompleteJobRequest())
    with pytest.raises(JobClaimConflict):
        second.fail_job(job.id, FailJobRequest(message="foreign process"))
    spoofed = chat_job(second, execution_owner=owner.node_id)
    assert spoofed.compat["execution_owner"] == second_owner.node_id
    assert (
        first.complete_job(job.id, CompleteJobRequest()).status == JobStatus.COMPLETED
    )


def test_expired_owner_is_not_revived_and_cannot_accept_or_complete(runtime):
    database, store, _ = runtime
    owner = owned_store(database, store)
    job = chat_job(store)
    store.mark_running(job.id)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE omnix_runtime_nodes SET lease_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second' WHERE id = %s",
            (owner.node_id,),
        )
    with pytest.raises(RuntimeNodeConflict):
        owner.heartbeat()
    with pytest.raises(RuntimeNodeConflict):
        owner.register()
    with pytest.raises(RuntimeNodeConflict):
        chat_job(store)
    with pytest.raises(JobClaimConflict):
        store.complete_job(job.id, CompleteJobRequest())
    assert recover_abandoned_chat_generation_jobs(None, store) == 1
    assert store.get_job(job.id).status == JobStatus.FAILED
    assert store.finalize_cancel(job.id, "late provider cancellation") is None
    assert store.get_job(job.id).status == JobStatus.FAILED


def test_heartbeat_cannot_revive_lease_that_expired_during_transaction(runtime):
    database, store, _ = runtime
    owner = owned_store(database, store)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE omnix_runtime_nodes SET lease_expires_at = CURRENT_TIMESTAMP + INTERVAL '10 milliseconds' WHERE id = %s",
            (owner.node_id,),
        )
        connection.execute("SELECT pg_sleep(0.03)")
        with pytest.raises(RuntimeNodeConflict):
            PostgresRuntimeCoordinationRepository(connection).heartbeat(
                node_id=owner.node_id
            )


def test_generic_worker_cannot_claim_inline_chat_even_when_owner_is_abandoned(runtime):
    database, store, _ = runtime
    owner = owned_store(database, store)
    job = chat_job(store)
    with unit_of_work(database) as work:
        assert (
            work.jobs.claim_next(
                store.context, worker_id="generic-worker", resource_classes=["gpu:llm"]
            )
            is None
        )
        work.commit()
    with database.transaction() as connection:
        PostgresRuntimeCoordinationRepository(connection).stop(owner.node_id)
    with unit_of_work(database) as work:
        assert (
            work.jobs.claim_next(
                store.context, worker_id="generic-worker", resource_classes=["gpu:llm"]
            )
            is None
        )
        work.commit()
    assert store.get_job(job.id).status == JobStatus.QUEUED
    assert store.recover_chat_job(job.id).status == JobStatus.FAILED


def test_recovery_rechecks_liveness_and_emits_one_event_under_racing_gateways(runtime):
    database, store, _ = runtime
    owner = owned_store(database, store)
    job = chat_job(store)
    with database.transaction() as connection:
        PostgresRuntimeCoordinationRepository(connection).stop(owner.node_id)
    barrier = threading.Barrier(2)

    def recover():
        barrier.wait(timeout=3)
        return store.recover_chat_job(job.id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: recover(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert (
        sum(event.event_type == "job.failed" for event in store.list_events(job.id))
        == 1
    )
    assert store.recover_chat_job(job.id) is None


def test_cancel_requested_recovery_preserves_cancel_and_updates_message_atomically(
    runtime,
):
    database, store, _ = runtime
    with unit_of_work(database) as work:
        session = work.chats.create_session(
            store.context, {"id": f"chat:{uuid.uuid4().hex}", "title": "Recovery"}
        )
        message = work.chats.append_message(
            store.context,
            session["id"],
            {"id": f"msg:{uuid.uuid4().hex}", "role": "user", "content": "hello"},
        )
        work.commit()
    job = store.create_job(
        CreateJobRequest(
            module="chatbot",
            type="chat.generate",
            resource_class=ResourceClass.GPU_LLM,
            input_payload={"session_id": session["id"], "message_id": message["id"]},
            compat={"inline_execution": True},
        )
    )
    with database.transaction() as connection:
        connection.execute(
            "UPDATE omnix_jobs SET status = 'cancel_requested' WHERE id = %s", (job.id,)
        )
    result = store.recover_chat_job(job.id)
    assert result.status == JobStatus.CANCELED
    assert result.cancel.requested is True
    assert result.cancel.acknowledged_at is not None
    with database.connection() as connection:
        metadata = connection.execute(
            "SELECT metadata FROM omnix_chat_messages WHERE id = %s", (message["id"],)
        ).fetchone()[0]
    assert metadata["generation_status"] == "canceled"


def test_recovery_pages_past_500_newer_unrelated_jobs_and_respects_tenant(runtime):
    database, store, new_store = runtime
    other = new_store()
    foreign = chat_job(other)
    with database.transaction() as connection:
        connection.execute(
            """INSERT INTO omnix_jobs (id, workspace_id, owner_user_id, module, job_type, resource_class, metadata)
            SELECT %s || ':' || n::text, %s, %s, 'chatbot', 'chat.generate', 'gpu:llm',
                   '{"compat_contract":{"compat":{"inline_execution":true}}}'::jsonb
              FROM generate_series(1, 601) AS n""",
            (
                f"recovery:{uuid.uuid4().hex}",
                store.context.workspace_id,
                store.context.user_id,
            ),
        )
        connection.execute(
            """INSERT INTO omnix_jobs (id, workspace_id, owner_user_id, module, job_type, resource_class)
            SELECT %s || ':' || n::text, %s, %s, 'image', 'image.generate', 'gpu:image'
              FROM generate_series(1, 1000) AS n""",
            (
                f"noise:{uuid.uuid4().hex}",
                store.context.workspace_id,
                store.context.user_id,
            ),
        )
    assert len(list(store.iter_recoverable_chat_jobs(batch_size=71))) == 601
    assert recover_abandoned_chat_generation_jobs(None, store) == 601
    assert list(store.iter_recoverable_chat_jobs()) == []
    assert other.get_job(foreign.id).status == JobStatus.QUEUED
