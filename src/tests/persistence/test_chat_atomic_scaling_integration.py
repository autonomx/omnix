"""Chat transactions and background ownership across independent gateways."""

from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from types import SimpleNamespace
import threading
import uuid

import pytest

from app.chat.generation_jobs import (
    chat_submission_lock,
    find_chat_generation_job,
    _run_chat_generation_job,
)
from app.chat.models import ChatMessage, ChatSession, SendChatMessageRequest
from app.runtime.background import (
    GatewayBackgroundRuntime,
    BackgroundOwnershipUnavailable,
)
from app.jobs.models import (
    CompleteJobRequest,
    CreateJobRequest,
    ResourceClass,
    JobStatus,
)
from app.persistence.chat_compat import PostgresChatRepositoryAdapter
from app.persistence.chat_runtime_compat import PostgresCharacterChatSessionStore
from app.persistence.execution_repositories import JobClaimConflict
from app.persistence.job_runtime_compat import PostgresJobStoreAdapter
from app.persistence.transaction_binding import share_transaction
from app.persistence.unit_of_work import unit_of_work
from src.tests.persistence import test_chat_execution_ownership_integration as ownership

pytestmark = ownership.pytestmark
owned_store = ownership.owned_store


@pytest.fixture(name="runtime")
def scaling_runtime():
    yield from ownership.runtime.__wrapped__()


def chat_store(database, store, monkeypatch):
    from app.gateway import live_chat_postgres_fast_path as fast
    from app.gateway import _install_required_rpg_turn_hooks

    _install_required_rpg_turn_hooks()
    monkeypatch.setattr(
        fast,
        "default_assistant_turn_coordinator",
        lambda: SimpleNamespace(get=lambda _: None),
    )

    def begin(session, message, request):
        message.metadata["user_turn_id"] = request.user_turn_id

    monkeypatch.setattr(fast, "_start_assistant_turn", begin)
    chat = PostgresCharacterChatSessionStore.__new__(PostgresCharacterChatSessionStore)
    chat._repository = PostgresChatRepositoryAdapter(database)
    chat._repository.context = store.context
    chat._run_post_turn_maintenance = lambda *args: None
    chat._generate_reply = lambda *args, **kwargs: {
        "content": "A durable reply",
        "metadata": {},
    }
    return chat


def session(store):
    with unit_of_work(store.database) as work:
        value = work.chats.create_session(
            store.context, {"id": f"chat:{uuid.uuid4().hex}", "title": "Atomic chat"}
        )
        work.commit()
    return value["id"]


def test_targeted_creation_preserves_concurrent_transcripts_and_large_workspace(runtime):
    database, store, _ = runtime
    adapter = PostgresChatRepositoryAdapter(database)
    adapter.context = store.context
    # Exceed the sidebar's 200-row page to catch snapshot-driven deletion.
    with unit_of_work(database) as work:
        for index in range(205):
            work.chats.create_session(store.context, {"id": f"chat:{uuid.uuid4().hex}", "title": str(index)})
        work.commit()
    barrier = threading.Barrier(2)

    def create(index):
        now = '2026-09-26T00:00:00+00:00'
        value = ChatSession(id=f'chat:{uuid.uuid4().hex}', title=f'New {index}',
                            created_at=now, updated_at=now, messages=[
                                ChatMessage(id=f'msg:{uuid.uuid4().hex}', role='system',
                                            content='Retained system prompt', created_at=now)])
        barrier.wait(5)
        adapter.create_session(value)
        return value

    with ThreadPoolExecutor(2) as executor:
        created = list(executor.map(create, range(2)))
    with database.connection() as connection:
        count = connection.execute("SELECT COUNT(*) FROM omnix_chat_sessions WHERE workspace_id = %s AND status = 'active'", (store.context.workspace_id,)).fetchone()[0]
    assert count == 207
    for value in created:
        assert adapter.get_session(value.id).messages[0].content == 'Retained system prompt'


def test_targeted_delete_is_scoped_idempotent_and_preserves_neighbors(runtime):
    database, store, new_store = runtime
    adapter = PostgresChatRepositoryAdapter(database)
    adapter.context = store.context
    target, neighbor = session(store), session(store)
    foreign = session(new_store())
    assert not adapter.delete_session(foreign)
    assert adapter.delete_session(target)
    assert not adapter.delete_session(target)
    with database.connection() as connection:
        rows = connection.execute('SELECT id, status FROM omnix_chat_sessions WHERE id = ANY(%s)', ([target, neighbor, foreign],)).fetchall()
    assert dict(rows) == {target: 'deleted', neighbor: 'active', foreign: 'active'}


def test_created_greeting_and_session_roll_back_together(runtime, monkeypatch):
    database, store, _ = runtime
    adapter = PostgresChatRepositoryAdapter(database)
    adapter.context = store.context
    now = '2026-09-26T00:00:00+00:00'
    value = ChatSession(id=f'chat:{uuid.uuid4().hex}', title='Rollback', created_at=now,
                        updated_at=now, messages=[ChatMessage(id='msg:test', role='system', content='hello', created_at=now)])
    from app.chat.persistence.repository import PostgresChatRepository

    monkeypatch.setattr(PostgresChatRepository, 'append_message', lambda *args: (_ for _ in ()).throw(RuntimeError('greeting failed')))
    with pytest.raises(RuntimeError, match='greeting failed'):
        adapter.create_session(value)
    assert adapter.get_session(value.id) is None


def test_runtime_schema_verification_does_not_acquire_migration_lock_in_chat_transaction(runtime, monkeypatch):
    from app.persistence import migrations

    database, _, _ = runtime
    monkeypatch.setattr(migrations, '_acquire_migration_lock', lambda _: (_ for _ in ()).throw(AssertionError('migration lock in domain transaction')))
    with unit_of_work(database) as work:
        with share_transaction(work):
            assert migrations.apply_migrations(database)['applied_now'] == []
        work.rollback()


def test_independent_turn_records_are_atomic_with_chat_transaction(runtime, monkeypatch):
    from app.persistence import runtime_document_compat as compat
    from app.persistence.document_store import PostgresDocumentStore

    database, store, _ = runtime
    documents = PostgresDocumentStore(database)
    documents.context = store.context
    monkeypatch.setattr(compat, 'PostgresDocumentStore', lambda: documents)
    coordinator_type = compat.postgres_assistant_turn_coordinator_class()
    first, second = coordinator_type(), coordinator_type()
    one = first.start(session_id='chat:1', user_message_id='msg:1', user_turn_id='turn:1')
    two = second.start(session_id='chat:2', user_message_id='msg:2', user_turn_id='turn:2')
    first.mark_streaming(one.assistant_turn_id)
    third = coordinator_type()
    with unit_of_work(database) as work:
        with share_transaction(work):
            rejected = third.start(session_id='chat:3', user_message_id='msg:3', user_turn_id='turn:3')
        work.rollback()
    reloaded = coordinator_type()
    assert reloaded.get(one.assistant_turn_id).lifecycle == 'streaming'
    assert reloaded.get(two.assistant_turn_id) is not None
    assert reloaded.get(rejected.assistant_turn_id) is None
    assert rejected.assistant_turn_id not in third._persisted_records


def accept(store, chat, session_id, submission_id):
    request = SendChatMessageRequest(content="hello", user_turn_id=submission_id)
    with chat_submission_lock(
        session_id, submission_id, job_store=store, chat_store=chat
    ):
        existing = find_chat_generation_job(
            store, session_id=session_id, submission_id=submission_id
        )
        if existing:
            return existing
        snapshot, message = chat.begin_user_message(session_id, request)
        return store.create_job(
            CreateJobRequest(
                module="chatbot",
                type="chat.generate",
                resource_class=ResourceClass.GPU_LLM,
                input_payload={
                    "session_id": snapshot.id,
                    "message_id": message.id,
                    "submission_id": submission_id,
                },
                compat={"inline_execution": True},
            )
        )


def test_cross_gateway_admission_creates_one_job_and_one_user_message(
    runtime, monkeypatch
):
    database, first, _ = runtime
    owned_store(database, first)
    second = PostgresJobStoreAdapter(database)
    second.context = first.context
    owned_store(database, second)
    chat = chat_store(database, first, monkeypatch)
    session_id = session(first)
    barrier = threading.Barrier(2)

    def submit(store):
        barrier.wait(2)
        return accept(store, chat, session_id, "one-browser-submission")

    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(submit, [first, second]))
    assert results[0].id == results[1].id
    assert len(chat.get_session(session_id).messages) == 1
    assert len(first.list_jobs()) == 1


def test_failed_job_acceptance_rolls_back_user_message(runtime, monkeypatch):
    database, store, _ = runtime
    owned_store(database, store)
    chat = chat_store(database, store, monkeypatch)
    session_id = session(store)
    monkeypatch.setattr(
        store,
        "create_job",
        lambda _: (_ for _ in ()).throw(RuntimeError("cannot enqueue")),
    )
    with pytest.raises(RuntimeError, match="cannot enqueue"):
        accept(store, chat, session_id, "failed-acceptance")
    assert chat.get_session(session_id).messages == []


def test_completion_and_metadata_rollback_when_completion_validator_fails(
    runtime, monkeypatch
):
    database, store, _ = runtime
    owned_store(database, store)
    chat = chat_store(database, store, monkeypatch)
    session_id = session(store)
    job = accept(store, chat, session_id, "validator-failure")
    store.mark_running(job.id)

    def fail_hook(chat, session_id, message_id, *args):
        chat.update_user_message_metadata(
            session_id=session_id,
            message_id=message_id,
            metadata={"validator_partial": True},
        )
        raise RuntimeError("completion rejected")

    _run_chat_generation_job(
        chat_store=chat,
        job_store=store,
        job=job,
        request=SendChatMessageRequest(content="hello"),
        context_builder=None,
        completion_hook=fail_hook,
    )
    assert store.get_job(job.id).status == JobStatus.FAILED
    messages = chat.get_session(session_id).messages
    assert len(messages) == 1
    assert "validator_partial" not in messages[0].metadata
    assert messages[0].metadata["generation_status"] == "failed"


def test_successful_completion_is_atomic_and_cross_gateway_session_order_is_preserved(
    runtime, monkeypatch
):
    database, first, _ = runtime
    owned_store(database, first)
    second = PostgresJobStoreAdapter(database)
    second.context = first.context
    owned_store(database, second)
    chat = chat_store(database, first, monkeypatch)
    session_id = session(first)
    one = accept(first, chat, session_id, "one")
    two = accept(second, chat, session_id, "two")
    assert second.try_start_chat_job(two.id) is None
    assert first.try_start_chat_job(one.id).status == JobStatus.RUNNING
    with first.chat_completion(chat, one.id):
        chat.complete_streamed_reply(
            session_id, one.input_payload["message_id"], "answer", {}
        )
        first.complete_job(
            one.id, CompleteJobRequest(logs=[{"message": "committed with reply"}])
        )
    assert first.get_job(one.id).status == JobStatus.COMPLETED
    assert second.try_start_chat_job(two.id).status == JobStatus.RUNNING
    assert [message.role for message in chat.get_session(session_id).messages] == [
        "user",
        "user",
        "assistant",
    ]
    assert (
        sum(event.event_type == "job.completed" for event in first.list_events(one.id))
        == 1
    )


def test_expiry_after_reply_write_rolls_back_transcript_and_completion(
    runtime, monkeypatch
):
    database, store, _ = runtime
    owner = owned_store(database, store)
    chat = chat_store(database, store, monkeypatch)
    session_id = session(store)
    job = accept(store, chat, session_id, "expiry")
    store.mark_running(job.id)
    with pytest.raises((JobClaimConflict, RuntimeError)):
        with store.chat_completion(chat, job.id):
            chat.complete_streamed_reply(
                session_id, job.input_payload["message_id"], "must roll back", {}
            )
            with database.transaction() as connection:
                connection.execute(
                    "UPDATE omnix_runtime_nodes SET lease_expires_at = clock_timestamp() WHERE id = %s",
                    (owner.node_id,),
                )
            store.complete_job(job.id, CompleteJobRequest())
    assert len(chat.get_session(session_id).messages) == 1
    assert store.get_job(job.id).status == JobStatus.RUNNING


def test_shared_transaction_nested_rollback_is_a_savepoint_and_cannot_cross_threads(
    runtime,
):
    database, store, _ = runtime
    session_id = session(store)
    with unit_of_work(database) as root:
        with share_transaction(root):
            with unit_of_work(database) as nested:
                nested.connection.execute(
                    "UPDATE omnix_chat_sessions SET title = 'rollback' WHERE id = %s",
                    (session_id,),
                )
                nested.rollback()
            assert (
                root.chats.get_session(store.context, session_id)["title"]
                == "Atomic chat"
            )
            context = copy_context()
            with ThreadPoolExecutor(1) as executor:
                future = executor.submit(context.run, lambda: unit_of_work(database))
                with pytest.raises(RuntimeError, match="cross threads"):
                    future.result()
        root.commit()


def test_background_role_is_exclusive_and_api_role_cannot_start_monitor(runtime):
    database, store, _ = runtime
    first = GatewayBackgroundRuntime(database, store.context.workspace_id)
    second = GatewayBackgroundRuntime(database, store.context.workspace_id)
    api = GatewayBackgroundRuntime(database, store.context.workspace_id, role="api")
    first.acquire()
    try:
        with pytest.raises(BackgroundOwnershipUnavailable):
            second.acquire()
        api.acquire()
        assert api.ready()
        monitor = SimpleNamespace(
            start=lambda: pytest.fail("API process started monitor")
        )
        api.register("test", monitor, [], [])
        with pytest.raises(BackgroundOwnershipUnavailable):
            monitor.start()
    finally:
        first.release()
    second.acquire()
    second.release()


def test_background_database_mutations_fail_closed_after_ownership_loss(runtime):
    from app.persistence.background_authority import background_execution

    database, store, _ = runtime
    owner = GatewayBackgroundRuntime(database, store.context.workspace_id)
    owner.acquire()
    try:
        with background_execution(owner):
            owner.healthy = False
            with pytest.raises(BackgroundOwnershipUnavailable):
                with database.transaction():
                    pytest.fail("Lost owner obtained a database transaction")
    finally:
        owner.release()


def test_post_commit_callbacks_run_outside_transaction_and_rollback_discards_them(
    runtime,
):
    from app.persistence.transaction_binding import after_commit, shared_work
    from app.persistence.transaction_policy import in_transaction

    database, _, _ = runtime
    calls = []
    with unit_of_work(database) as root:
        with share_transaction(root):
            after_commit(
                database,
                lambda: calls.append((in_transaction(), shared_work(database))),
            )
            with unit_of_work(database) as nested:
                after_commit(database, lambda: calls.append("rolled back savepoint"))
                nested.rollback()
        assert calls == []
        root.commit()
    assert calls == [(False, None)]
    with unit_of_work(database) as root:
        with share_transaction(root):
            after_commit(database, lambda: calls.append("rolled back root"))
    assert calls == [(False, None)]


def test_background_connection_termination_revokes_execution_and_releases_cohort(
    runtime,
):
    database, store, _ = runtime
    owner = GatewayBackgroundRuntime(database, store.context.workspace_id)
    successor = GatewayBackgroundRuntime(database, store.context.workspace_id)
    owner.acquire()
    try:
        backend = owner.connection.execute("SELECT pg_backend_pid()").fetchone()[0]
        owner.connection.commit()
        with database.transaction() as connection:
            assert connection.execute(
                "SELECT pg_terminate_backend(%s)", (backend,)
            ).fetchone()[0]
        with pytest.raises(BackgroundOwnershipUnavailable):
            owner.require_live()
        assert not owner.healthy
        successor.acquire()
        successor.require_live()
    finally:
        owner.release()
        successor.release()


def test_rolled_back_admission_does_not_interrupt_previous_provider(runtime, monkeypatch):
    from app.chat import generation_jobs as jobs
    from app.jobs.models import CancelJobRequest

    database, store, _ = runtime
    owned_store(database, store)
    chat = chat_store(database, store, monkeypatch)
    session_id = session(store)
    job = accept(store, chat, session_id, 'prior-turn')
    store.mark_running(job.id)
    interrupted = []
    monkeypatch.setattr(jobs, '_interrupt_active_chat_provider', interrupted.append)
    with pytest.raises(RuntimeError, match='rejected admission'):
        with store.chat_transaction(chat, session_id):
            jobs.cancel_chat_generation_job(chat, store, job.id, CancelJobRequest(reason='new prompt'))
            raise RuntimeError('rejected admission')
    assert interrupted == []
    assert store.get_job(job.id).status == JobStatus.RUNNING
    assert chat.get_session(session_id).messages[0].metadata.get('generation_status') != 'canceled'
    jobs.cancel_chat_generation_job(chat, store, job.id, CancelJobRequest(reason='accepted cancel'))
    assert interrupted == [job.id]
    assert store.get_job(job.id).status == JobStatus.CANCELED
