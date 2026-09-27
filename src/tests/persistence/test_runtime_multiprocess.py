"""Spawned-process certification of singleton ownership, loss and API isolation."""
import asyncio
import multiprocessing
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get('OMNIX_TEST_DATABASE_URL'), reason='requires disposable PostgreSQL')


def _gateway_process(url, workspace, role, control):
    from app.runtime.background import GatewayBackgroundRuntime, BackgroundOwnershipUnavailable
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.runtime.config import RuntimeConfig, install_runtime_config

    config = RuntimeConfig.from_environment({'OMNIX_GATEWAY_BACKGROUND_ROLE': role, 'OMNIX_TTS_URL': 'http://127.0.0.1:5101'})
    install_runtime_config(config)
    database = PostgresDatabase(DatabaseSettings(url=url, pool_max=3))
    runtime = GatewayBackgroundRuntime(database, workspace, config=config, poll_seconds=.05)
    calls = []
    runtime.register('certification-worker', object(), (lambda: calls.append('started'),), (lambda: control.send({'event': 'worker_stopped'}),))

    async def run():
        try:
            async with runtime.lifespan():
                await runtime.startup()
                tts_remote = None
                if role == 'api':
                    from app import shared
                    from app.providers.qwen_http_gateway import QwenHttpGatewayProvider
                    shared.load_settings = lambda: {'audio_provider_tts': 'faster-qwen3-tts'}
                    def forbidden_registry():
                        raise AssertionError('API attempted local GPU provider construction')
                    shared.get_audio_registry = forbidden_registry
                    tts_remote = isinstance(shared.get_tts_provider(), QwenHttpGatewayProvider)
                backend_pid = runtime.connection.info.backend_pid if runtime.connection is not None else None
                control.send({'event': 'ready', 'role': role, 'workers_started': len(calls), 'owns_lock': runtime.healthy,
                              'backend_pid': backend_pid, 'tts_remote': tts_remote})
                await asyncio.to_thread(control.recv)
            control.send({'event': 'done', 'owns_lock': runtime.healthy})
        except BackgroundOwnershipUnavailable:
            control.send({'event': 'ownership_denied'})
    try:
        asyncio.run(run())
    finally:
        database.close()
        control.close()


def start_process(url, workspace, role):
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    process = context.Process(target=_gateway_process, args=(url, workspace, role, child))
    process.start()
    child.close()
    return process, parent


def receive(pipe, expected):
    assert pipe.poll(20), f'timed out waiting for {expected}'
    payload = pipe.recv()
    assert payload['event'] == expected, payload
    return payload


@pytest.fixture
def cohort():
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.runtime import ensure_postgresql_runtime_ready
    url = os.environ['OMNIX_TEST_DATABASE_URL']
    database = PostgresDatabase(DatabaseSettings(url=url))
    ensure_postgresql_runtime_ready(database)
    children = []
    def start(role, workspace):
        process, pipe = start_process(url, workspace, role)
        children.append((process, pipe))
        return process, pipe
    try:
        yield database, start, f'architecture-cohort:{uuid.uuid4().hex}'
    finally:
        for process, pipe in children:
            if process.is_alive():
                process.terminate()
            process.join(5)
            pipe.close()
        database.close()


def test_one_worker_two_api_replicas_remote_tts_and_graceful_handoff(cohort):
    _, start, workspace = cohort
    worker, control = start('worker', workspace)
    status = receive(control, 'ready')
    assert status['owns_lock'] and status['workers_started'] == 1
    for _ in range(2):
        _, pipe = start('api', workspace)
        api = receive(pipe, 'ready')
        assert api['workers_started'] == 0 and not api['owns_lock'] and api['tts_remote'] is True
        pipe.send('stop')
        receive(pipe, 'done')
    _, duplicate = start('worker', workspace)
    receive(duplicate, 'ownership_denied')
    control.send('stop')
    receive(control, 'worker_stopped')
    assert not receive(control, 'done')['owns_lock']
    worker.join(5)
    _, successor = start('worker', workspace)
    assert receive(successor, 'ready')['owns_lock']


def test_background_backend_loss_stops_workers_and_allows_successor(cohort):
    database, start, workspace = cohort
    _, control = start('worker', workspace)
    status = receive(control, 'ready')
    with database.connection() as connection:
        assert connection.execute('SELECT pg_terminate_backend(%s)', (status['backend_pid'],)).fetchone()[0]
    receive(control, 'worker_stopped')
    _, successor = start('worker', workspace)
    assert receive(successor, 'ready')['owns_lock']
    control.send('stop')
    assert not receive(control, 'done')['owns_lock']


def test_worker_process_crash_releases_singleton_authority(cohort):
    _, start, workspace = cohort
    worker, control = start('worker', workspace)
    assert receive(control, 'ready')['owns_lock']
    worker.terminate()
    worker.join(5)
    _, successor = start('worker', workspace)
    assert receive(successor, 'ready')['owns_lock']


def _claim_chat_process(url, workspace, user, session, control):
    from app.jobs.models import CreateJobRequest, ResourceClass
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.gateway_runtime import GatewayRuntimeOwner
    from app.persistence.job_runtime_compat import PostgresJobStoreAdapter
    from app.persistence.repositories import PostgresIdentityRepository
    database = PostgresDatabase(DatabaseSettings(url=url))
    store = PostgresJobStoreAdapter(database)
    with database.connection() as connection:
        store.context = PostgresIdentityRepository(connection).load_context(user_id=user, workspace_id=workspace)
    owner = GatewayRuntimeOwner(database, workspace)
    owner.register()
    store.chat_execution_owner = owner
    job = store.create_job(CreateJobRequest(module='chatbot', type='chat.generate',
                           resource_class=ResourceClass.GPU_LLM, input_payload={'session_id': session},
                           compat={'inline_execution': True}))
    store.mark_running(job.id)
    control.send({'job_id': job.id, 'owner_id': owner.node_id})
    control.recv()


@pytest.fixture
def chat_runtime():
    from src.tests.persistence import test_chat_execution_ownership_integration as ownership
    yield from ownership.runtime.__wrapped__()


def test_killed_chat_owner_recovers_once_without_duplicate_assistant_output(chat_runtime):
    from app.chat.generation_jobs import recover_abandoned_chat_generation_jobs
    from app.jobs.models import CompleteJobRequest, JobStatus
    from app.persistence.execution_repositories import JobClaimConflict
    from app.persistence.gateway_runtime import GatewayRuntimeOwner
    from app.persistence.unit_of_work import unit_of_work
    database, store, _ = chat_runtime
    session = 'chat:crash:' + uuid.uuid4().hex
    with unit_of_work(database) as work:
        work.chats.create_session(store.context, {'id': session, 'title': 'Crash certification'})
        work.commit()
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    process = context.Process(target=_claim_chat_process, args=(os.environ['OMNIX_TEST_DATABASE_URL'],
                              store.context.workspace_id, store.context.user_id, session, child))
    try:
        process.start()
        child.close()
        assert parent.poll(20)
        claim = parent.recv()
        assert store.get_job(claim['job_id']).status == JobStatus.RUNNING
        process.terminate()
        process.join(5)
        assert not process.is_alive()
        # Advance only the killed node's durable lease, avoiding wall-clock sleeps.
        with database.transaction() as connection:
            connection.execute("UPDATE omnix_runtime_nodes SET lease_expires_at = clock_timestamp() - INTERVAL '1 second' WHERE id = %s",
                               (claim['owner_id'],))
        successor = GatewayRuntimeOwner(database, store.context.workspace_id)
        successor.register()
        store.chat_execution_owner = successor
        with pytest.raises(JobClaimConflict):
            store.complete_job(claim['job_id'], CompleteJobRequest())
        assert recover_abandoned_chat_generation_jobs(None, store) == 1
        assert recover_abandoned_chat_generation_jobs(None, store) == 0
        assert store.get_job(claim['job_id']).status == JobStatus.FAILED
        with database.connection() as connection:
            assert connection.execute("SELECT count(*) FROM omnix_chat_messages WHERE session_id = %s AND role = 'assistant'", (session,)).fetchone()[0] == 0
            assert connection.execute("SELECT count(*) FROM omnix_job_events WHERE job_id = %s AND event_type = 'job.failed'", (claim['job_id'],)).fetchone()[0] == 1
    finally:
        if process.is_alive():
            process.terminate()
        process.join(5)
        parent.close()


def test_expired_job_attempt_is_fenced_after_another_worker_claims(chat_runtime):
    from app.persistence.execution_repositories import JobClaimConflict
    from app.persistence.unit_of_work import unit_of_work
    database, store, _ = chat_runtime
    with unit_of_work(database) as work:
        job = work.jobs.create_job(store.context, {'id': 'job:fencing:' + uuid.uuid4().hex,
                                  'module': 'image', 'job_type': 'image.generate', 'resource_class': 'gpu:image'})
        first = work.jobs.claim_next(store.context, worker_id='worker:a', resource_classes=['gpu:image'])
        work.commit()
    with database.transaction() as connection:
        connection.execute("UPDATE omnix_jobs SET lease_expires_at = clock_timestamp() - INTERVAL '1 second' WHERE id = %s", (job['id'],))
    with unit_of_work(database) as work:
        second = work.jobs.claim_next(store.context, worker_id='worker:b', resource_classes=['gpu:image'])
        work.commit()
    assert first['lease_token'] != second['lease_token']
    with unit_of_work(database) as work:
        with pytest.raises(JobClaimConflict):
            work.jobs.complete(store.context, job_id=job['id'], worker_id='worker:a',
                               lease_token=first['lease_token'], output_refs=[])
        work.rollback()
    with unit_of_work(database) as work:
        completed = work.jobs.complete(store.context, job_id=job['id'], worker_id='worker:b',
                                      lease_token=second['lease_token'], output_refs=[])
        work.commit()
    assert completed['status'] == 'completed'
