"""Spawned-process certification of singleton ownership, loss and API isolation."""
import asyncio
import multiprocessing
import hashlib
import os
import time
import uuid
from datetime import datetime, timezone

import pytest

from app.chat.models import ChatMessage, ChatSession

pytestmark = pytest.mark.skipif(not os.environ.get('OMNIX_TEST_DATABASE_URL'), reason='requires disposable PostgreSQL')

_SCHEDULER_EVENTS = None


def _worker_acceptance_context():
    from app.security.tenant_context import local_tenant_context

    context = local_tenant_context()
    return (context.user_id, context.workspace_id, context.membership_id, tuple(context.roles))


def _worker_acceptance_types(run_id):
    # Workers claim by registered type, so each run gets its own job types;
    # otherwise concurrent acceptance tests claim each other's jobs.
    namespace = hashlib.sha256(run_id.encode()).hexdigest()[:12]
    return f"test.worker.acceptance.{namespace}.cpu", f"test.worker.acceptance.{namespace}.image"


def _worker_acceptance_registry(run_id):
    from app.jobs.handlers import Backoff, JobHandlerRegistry, JobHandlerSpec
    from app.jobs.models import ResourceClass

    cpu_type, image_type = _worker_acceptance_types(run_id)
    return JobHandlerRegistry((
        JobHandlerSpec(
            type=cpu_type,
            handler=_worker_acceptance_handler,
            resource_class=ResourceClass.CPU,
            retry_backoff=Backoff(base_seconds=0.01, factor=1, max_seconds=0.01, jitter=0),
        ),
        JobHandlerSpec(
            type=image_type,
            handler=_worker_acceptance_handler,
            resource_class=ResourceClass.GPU_IMAGE,
            retry_backoff=Backoff(base_seconds=0.01, factor=1, max_seconds=0.01, jitter=0),
        ),
    ))


def _worker_acceptance_handler(context, job):
    import time

    from app.jobs.models import CompleteJobRequest

    services = context.services
    database = services.database
    run_id = services.run_id
    attempt = max(1, int(getattr(job, "_attempt_count", 0) or 1))
    lease = job.lease
    pool_name = "image" if job.resource_class.value == "gpu:image" else "cpu"
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO omnix_test_job_worker_attempts
                (run_id, job_id, attempt, worker_id, pool_name, invocation_count)
            VALUES (%s, %s, %s, %s, %s, 1)
            ON CONFLICT (run_id, job_id, attempt)
            DO UPDATE SET invocation_count =
                omnix_test_job_worker_attempts.invocation_count + 1
            """,
            (run_id, job.id, attempt, lease.worker_id, pool_name),
        )
        connection.execute(
            """
            INSERT INTO omnix_test_job_worker_pool_counts
                (run_id, worker_id, pool_name, active_jobs, max_active_jobs)
            VALUES (%s, %s, %s, 1, 1)
            ON CONFLICT (run_id, worker_id, pool_name)
            DO UPDATE SET
                active_jobs = omnix_test_job_worker_pool_counts.active_jobs + 1,
                max_active_jobs = GREATEST(
                    omnix_test_job_worker_pool_counts.max_active_jobs,
                    omnix_test_job_worker_pool_counts.active_jobs + 1
                )
            """,
            (run_id, lease.worker_id, pool_name),
        )

    if services.pause_first_attempt and attempt == 1:
        services.started.set()
        time.sleep(30)
    else:
        time.sleep(0.025)

    with database.transaction() as connection:
        connection.execute(
            """
            UPDATE omnix_test_job_worker_pool_counts
               SET active_jobs = GREATEST(0, active_jobs - 1)
             WHERE run_id = %s AND worker_id = %s AND pool_name = %s
            """,
            (run_id, lease.worker_id, pool_name),
        )
    return context.job_store.complete_job(job.id, CompleteJobRequest()) or job


def _durable_job_worker_process(
    url,
    run_id,
    tenant_values,
    pools_text,
    start_gate,
    stop_event,
    control,
    started_event=None,
    pause_first_attempt=False,
    short_lease=False,
):
    from types import SimpleNamespace

    from app.chat.persistence.job_store import PostgresJobStoreAdapter
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.runtime.tenant_context import TenantContext
    from app.worker_runtime.durable_feature_worker import DurableFeatureJobWorker
    from app.worker_runtime.pools import parse_pools

    database = PostgresDatabase(DatabaseSettings(url=url, pool_max=8))
    user_id, workspace_id, membership_id, roles = tenant_values
    tenant = TenantContext(
        user_id=user_id,
        workspace_id=workspace_id,
        membership_id=membership_id,
        roles=frozenset(roles),
    )
    registry = _worker_acceptance_registry(run_id)
    store = PostgresJobStoreAdapter(database, context=tenant)
    store.configure_handler_registry(registry)
    services = SimpleNamespace(
        database=database,
        run_id=run_id,
        started=started_event,
        pause_first_attempt=pause_first_attempt,
    )

    class ShortLeaseWorker(DurableFeatureJobWorker):
        lease_seconds = 2
        renewal_seconds = 0.25

    worker_type = ShortLeaseWorker if short_lease else DurableFeatureJobWorker
    workers = []
    try:
        control.send({"event": "booted", "pid": os.getpid()})
        if not start_gate.wait(30):
            raise TimeoutError("job worker start gate timed out")
        for pool in parse_pools(pools_text):
            workers.append(worker_type(
                store,
                registry,
                pool_name=pool.name,
                resource_classes=pool.resource_classes,
                services=services,
                max_concurrency=pool.concurrency,
                poll_seconds=0.02,
                shutdown_grace_seconds=3,
                worker_id=f"job-worker:{os.getpid()}:{uuid.uuid4().hex}:{pool.name}",
            ))
        for worker in workers:
            worker.start()
        control.send({"event": "ready", "pid": os.getpid()})
        if not stop_event.wait(60):
            raise TimeoutError("job worker stop signal timed out")
        for worker in workers:
            worker.stop(grace_seconds=3)
        control.send({"event": "done", "pid": os.getpid()})
    except BaseException as error:
        try:
            control.send({"event": "error", "error": f"{type(error).__name__}: {error}"})
        except (BrokenPipeError, EOFError, OSError):
            pass
        raise
    finally:
        database.close()
        control.close()


def _prepare_worker_acceptance_tables(database):
    with database.transaction() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS omnix_test_job_worker_attempts (
                run_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                worker_id TEXT NOT NULL,
                pool_name TEXT NOT NULL,
                invocation_count INTEGER NOT NULL,
                PRIMARY KEY (run_id, job_id, attempt)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS omnix_test_job_worker_pool_counts (
                run_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                pool_name TEXT NOT NULL,
                active_jobs INTEGER NOT NULL,
                max_active_jobs INTEGER NOT NULL,
                PRIMARY KEY (run_id, worker_id, pool_name)
            )
            """
        )


def _create_worker_acceptance_jobs(database, count, *, run_id):
    from app.chat.persistence.job_store import PostgresJobStoreAdapter
    from app.jobs.models import CreateJobRequest, ResourceClass
    from app.runtime.tenant_context import local_tenant_context

    store = PostgresJobStoreAdapter(database, context=local_tenant_context())
    registry = _worker_acceptance_registry(run_id)
    store.configure_handler_registry(registry)
    cpu_type, image_type = _worker_acceptance_types(run_id)
    job_ids = []
    for index in range(count):
        is_image = index % 2 == 1
        job = store.create_job(CreateJobRequest(
            module="worker-acceptance",
            type=image_type if is_image else cpu_type,
            resource_class=ResourceClass.GPU_IMAGE if is_image else ResourceClass.CPU,
            input_payload={"run_id": run_id, "index": index},
        ))
        job_ids.append(job.id)
    return job_ids


def _wait_for_worker_jobs(database, tenant_values, job_ids, expected, *, timeout_seconds=60):
    deadline = time.monotonic() + timeout_seconds
    _, workspace_id, _, _ = tenant_values
    while time.monotonic() < deadline:
        with database.connection() as connection:
            rows = connection.execute(
                """
                SELECT status, count(*)
                  FROM omnix_jobs
                 WHERE workspace_id = %s AND id = ANY(%s)
                 GROUP BY status
                """,
                (workspace_id, job_ids),
            ).fetchall()
        completed = sum(int(count) for status, count in rows if status == "completed")
        if completed == expected:
            return
        time.sleep(0.05)
    raise TimeoutError(f"only {completed} of {expected} durable worker jobs completed")


def _cleanup_worker_acceptance_run(database, run_id):
    with database.transaction() as connection:
        connection.execute(
            "DELETE FROM omnix_test_job_worker_pool_counts WHERE run_id = %s",
            (run_id,),
        )
        connection.execute(
            "DELETE FROM omnix_test_job_worker_attempts WHERE run_id = %s",
            (run_id,),
        )



async def _scheduler_probe(context):
    _SCHEDULER_EVENTS.put((context.task_id, os.getpid()))


def _scheduler_process(url, workspace, events, start_gate, stop_gate, control):
    global _SCHEDULER_EVENTS
    from app.config.runtime import GatewayRole, RuntimeConfig
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.background_authority import background_execution
    from app.runtime.capabilities import RuntimeCapabilities
    from app.runtime.scheduler import ScheduledTaskSpec, SchedulerRuntime

    _SCHEDULER_EVENTS = events
    database = PostgresDatabase(DatabaseSettings(url=url, pool_max=3))

    async def run():
        control.send({'event': 'booted', 'pid': os.getpid()})
        if not await asyncio.to_thread(start_gate.wait, 20):
            raise TimeoutError('scheduler startup gate timed out')
        config = RuntimeConfig(gateway_role=GatewayRole.SCHEDULER)
        scheduler = SchedulerRuntime(
            database,
            workspace,
            capabilities=RuntimeCapabilities.from_config(config),
            execution_scope=background_execution,
            poll_seconds=0.05,
            startup_jitter_seconds=0.01,
            thread_workers=1,
            process_workers=1,
        )
        for index in range(24):
            scheduler.register_task(
                ScheduledTaskSpec(
                    task_id=f'acceptance.split-{index:02d}',
                    run=_scheduler_probe,
                    interval_seconds=0.05,
                    timeout_seconds=2,
                )
            )
        async with scheduler.lifespan():
            control.send({
                'event': 'ready',
                'pid': os.getpid(),
                'owned_tasks': scheduler.diagnostics()['owned_tasks'],
            })
            if not await asyncio.to_thread(stop_gate.wait, 30):
                raise TimeoutError('scheduler stop gate timed out')
        control.send({'event': 'done', 'pid': os.getpid()})

    try:
        asyncio.run(run())
    except BaseException as error:
        control.send({'event': 'error', 'error': f'{type(error).__name__}: {error}'})
        raise
    finally:
        database.close()
        control.close()


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
                    from app.providers import service as provider_service
                    from app.providers.qwen_http_gateway import QwenHttpGatewayProvider
                    provider_service.load_settings = lambda: {'audio_provider_tts': 'faster-qwen3-tts'}
                    def forbidden_registry():
                        raise AssertionError('API attempted local GPU provider construction')
                    provider_service.get_audio_registry = forbidden_registry
                    tts_remote = isinstance(provider_service.get_tts_provider(), QwenHttpGatewayProvider)
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
    from app.persistence.identity_service import ensure_local_identity
    ensure_local_identity(database)
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



@pytest.mark.postgres
@pytest.mark.multiprocess
def test_two_standalone_job_workers_process_100_jobs_once_with_pool_limits(cohort):
    database, _, _ = cohort
    tenant_values = _worker_acceptance_context()
    run_id = f"worker-pool-acceptance:{uuid.uuid4().hex}"
    _prepare_worker_acceptance_tables(database)
    job_ids = _create_worker_acceptance_jobs(database, 100, run_id=run_id)
    process_context = multiprocessing.get_context("spawn")
    start_gate = process_context.Event()
    stop_event = process_context.Event()
    processes = []
    controls = []
    try:
        for _ in range(2):
            parent, child = process_context.Pipe()
            process = process_context.Process(
                target=_durable_job_worker_process,
                args=(
                    database.settings.url,
                    run_id,
                    tenant_values,
                    "cpu=2,image=1",
                    start_gate,
                    stop_event,
                    child,
                ),
            )
            process.start()
            child.close()
            processes.append(process)
            controls.append(parent)
        for control in controls:
            receive(control, "booted")
        start_gate.set()
        worker_pids = {receive(control, "ready")["pid"] for control in controls}
        assert len(worker_pids) == 2

        _wait_for_worker_jobs(database, tenant_values, job_ids, 100)

        with database.connection() as connection:
            attempts = connection.execute(
                """
                SELECT job_id, attempt, worker_id, pool_name, invocation_count
                  FROM omnix_test_job_worker_attempts
                 WHERE run_id = %s
                """,
                (run_id,),
            ).fetchall()
            concurrency = connection.execute(
                """
                SELECT pool_name, max(max_active_jobs)
                  FROM omnix_test_job_worker_pool_counts
                 WHERE run_id = %s
                 GROUP BY pool_name
                """,
                (run_id,),
            ).fetchall()
        assert len(attempts) == 100
        assert {row[0] for row in attempts} == set(job_ids)
        assert all(row[1] == 1 and row[4] == 1 for row in attempts)
        assert {int(row[2].split(":")[1]) for row in attempts} == worker_pids
        assert dict(concurrency) == {"cpu": 2, "image": 1}
    finally:
        stop_event.set()
        for process in processes:
            process.join(10)
            if process.is_alive():
                process.terminate()
                process.join(5)
        for control in controls:
            control.close()
        _cleanup_worker_acceptance_run(database, run_id)


@pytest.mark.postgres
@pytest.mark.multiprocess
def test_killed_job_worker_releases_expired_lease_for_reclaim(cohort):
    database, _, _ = cohort
    from app.runtime.tenant_context import TenantContext
    from app.persistence.unit_of_work import unit_of_work

    tenant_values = _worker_acceptance_context()
    tenant = TenantContext(
        user_id=tenant_values[0],
        workspace_id=tenant_values[1],
        membership_id=tenant_values[2],
        roles=frozenset(tenant_values[3]),
    )
    run_id = f"worker-kill-reclaim:{uuid.uuid4().hex}"
    _prepare_worker_acceptance_tables(database)
    job_id = _create_worker_acceptance_jobs(database, 1, run_id=run_id)[0]
    process_context = multiprocessing.get_context("spawn")
    start_gate = process_context.Event()
    started = process_context.Event()
    # Separate stop events: signalling a multiprocessing.Event whose waiter was
    # terminated mid-wait blocks forever, so the killed worker's event is never set.
    first_stop = process_context.Event()
    successor_stop = process_context.Event()
    first_control = None
    successor_control = None
    first = None
    successor = None
    try:
        first_control, first_child = process_context.Pipe()
        first = process_context.Process(
            target=_durable_job_worker_process,
            args=(
                database.settings.url,
                run_id,
                tenant_values,
                "cpu=1",
                start_gate,
                first_stop,
                first_child,
                started,
                True,
                True,
            ),
        )
        first.start()
        first_child.close()
        receive(first_control, "booted")
        start_gate.set()
        receive(first_control, "ready")
        assert started.wait(20), "first worker did not begin the leased job"
        first.terminate()
        first.join(10)
        assert not first.is_alive()

        time.sleep(2.2)
        with unit_of_work(database) as work:
            expired = work.jobs.release_expired_leases(tenant, job_id=job_id)
            work.commit()
        assert [row["id"] for row in expired] == [job_id]

        successor_gate = process_context.Event()
        successor_gate.set()
        successor_control, successor_child = process_context.Pipe()
        successor = process_context.Process(
            target=_durable_job_worker_process,
            args=(
                database.settings.url,
                run_id,
                tenant_values,
                "cpu=1",
                successor_gate,
                successor_stop,
                successor_child,
            ),
        )
        successor.start()
        successor_child.close()
        receive(successor_control, "booted")
        receive(successor_control, "ready")
        _wait_for_worker_jobs(database, tenant_values, [job_id], 1)

        with database.connection() as connection:
            attempts = connection.execute(
                """
                SELECT attempt, worker_id, invocation_count
                  FROM omnix_test_job_worker_attempts
                 WHERE run_id = %s AND job_id = %s
                 ORDER BY attempt
                """,
                (run_id, job_id),
            ).fetchall()
            job = connection.execute(
                "SELECT status, attempt_count FROM omnix_jobs WHERE id = %s",
                (job_id,),
            ).fetchone()
        assert [row[0] for row in attempts] == [1, 2]
        assert all(row[2] == 1 for row in attempts)
        assert attempts[0][1] != attempts[1][1]
        assert job == ("completed", 2)
    finally:
        successor_stop.set()
        if first is not None and first.is_alive():
            first_stop.set()
        for process in (first, successor):
            if process is not None and process.is_alive():
                process.join(5)
                if process.is_alive():
                    process.terminate()
                    process.join(5)
        for control in (first_control, successor_control):
            if control is not None:
                control.close()
        _cleanup_worker_acceptance_run(database, run_id)



@pytest.mark.postgres
@pytest.mark.multiprocess
def test_scheduler_processes_split_per_task_locks_without_duplicate_execution(cohort):
    _, _, workspace = cohort
    context = multiprocessing.get_context('spawn')
    events = context.Queue()
    start_gate = context.Event()
    stop_gate = context.Event()
    children = []
    receivers = []
    try:
        for _ in range(2):
            parent, child = context.Pipe()
            process = context.Process(
                target=_scheduler_process,
                args=(
                    os.environ['OMNIX_TEST_DATABASE_URL'],
                    workspace,
                    events,
                    start_gate,
                    stop_gate,
                    child,
                ),
            )
            process.start()
            child.close()
            children.append(process)
            receivers.append(parent)
        booted = [receive(pipe, 'booted') for pipe in receivers]
        start_gate.set()
        ready = [receive(pipe, 'ready') for pipe in receivers]
        assert len({item['pid'] for item in booted}) == 2

        task_owners = {}
        deadline = time.monotonic() + 20
        expected_tasks = {f'acceptance.split-{index:02d}' for index in range(24)}
        while set(task_owners) != expected_tasks and time.monotonic() < deadline:
            try:
                task_id, process_id = events.get(timeout=0.5)
            except Exception:
                continue
            task_owners.setdefault(task_id, set()).add(process_id)
        assert set(task_owners) == expected_tasks
        assert all(len(process_ids) == 1 for process_ids in task_owners.values())
        assert len({next(iter(value)) for value in task_owners.values()}) == 2
        assert sum(bool(item['owned_tasks']) for item in ready) == 2

        stop_gate.set()
        for receiver in receivers:
            receive(receiver, 'done')
        for process in children:
            process.join(10)
            assert process.exitcode == 0
    finally:
        stop_gate.set()
        start_gate.set()
        for process in children:
            if process.is_alive():
                process.terminate()
            process.join(5)
        for receiver in receivers:
            receiver.close()
        events.close()


def _claim_chat_process(url, workspace, user, session, control):
    from app.jobs.models import CreateJobRequest, ResourceClass
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.gateway_runtime import GatewayRuntimeOwner
    from app.chat.persistence.job_store import PostgresJobStoreAdapter
    from app.persistence.identity_service import PostgresIdentityRepository
    from app.runtime.tenant_context import pop_tenant, push_tenant

    database = PostgresDatabase(DatabaseSettings(url=url))
    try:
        with database.connection() as connection:
            context = PostgresIdentityRepository(connection).load_context(
                user_id=user, workspace_id=workspace
            )
        tenant_token = push_tenant(context)
        try:
            store = PostgresJobStoreAdapter(database)
            owner = GatewayRuntimeOwner(database, workspace)
            owner.register()
            store.chat_execution_owner = owner
            job = store.create_job(CreateJobRequest(
                module='chatbot',
                type='chat.generate',
                resource_class=ResourceClass.GPU_LLM,
                input_payload={'session_id': session},
                compat={'inline_execution': True},
            ))
            store.mark_running(job.id)
            control.send({'job_id': job.id, 'owner_id': owner.node_id})
            control.recv()
        finally:
            pop_tenant(tenant_token)
    finally:
        database.close()


def _mutate_chat_process(
    url,
    workspace,
    user,
    action,
    target_session_id,
    start_gate,
    finish_gate,
    control,
):
    from app.chat.models import ChatMessage, ChatSession
    from app.chat.persistence.chat_compat import PostgresChatRepositoryAdapter
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.identity_service import PostgresIdentityRepository
    from app.runtime.tenant_context import pop_tenant, push_tenant
    from app.assistant_memory.persistence.settings_store import assistant_memory_setting_spec
    from app.settings.access import install_settings_service
    from tests.support.in_memory_settings import InMemorySettingsService

    database = PostgresDatabase(DatabaseSettings(url=url, pool_max=2))
    try:
        with database.connection() as connection:
            context = PostgresIdentityRepository(connection).load_context(
                user_id=user,
                workspace_id=workspace,
            )
        tenant_token = push_tenant(context)
        try:
            settings_service = InMemorySettingsService()
            settings_service.register_specs((assistant_memory_setting_spec(),))
            install_settings_service(settings_service)
            adapter = PostgresChatRepositoryAdapter(database)
            if action == "create":
                assert start_gate.wait(20), "session creation barrier timed out"
                now = datetime.now(timezone.utc).isoformat()
                session_id = f"chat:multiprocess:{uuid.uuid4().hex}"
                adapter.create_session(
                    ChatSession(
                        id=session_id,
                        title="Created by process A",
                        created_at=now,
                        updated_at=now,
                        messages=[
                            ChatMessage(
                                id=f"msg:{uuid.uuid4().hex}",
                                role="user",
                                content="Created while another session changes",
                                created_at=now,
                            )
                        ],
                    )
                )
                control.send({"action": action, "session_id": session_id})
            elif action == "mutate":
                session = adapter.get_session(target_session_id)
                assert session is not None
                control.send({"action": action, "event": "loaded"})
                assert finish_gate.wait(20), "session mutation barrier timed out"
                session.title = "Mutated by process B"
                adapter.save_session(session)
                control.send({"action": action, "session_id": target_session_id})
            else:
                raise ValueError(f"unsupported chat mutation: {action}")
        finally:
            pop_tenant(tenant_token)
    except BaseException as error:
        control.send({"action": action, "error": f"{type(error).__name__}: {error}"})
        raise
    finally:
        database.close()


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


def test_two_process_chat_mutations_preserve_unrelated_session(chat_runtime):
    from app.chat.persistence.chat_compat import PostgresChatRepositoryAdapter

    database, store, _ = chat_runtime
    adapter = PostgresChatRepositoryAdapter(database)
    adapter.context = store.context
    target_id = f"chat:multiprocess-target:{uuid.uuid4().hex}"
    now = datetime.now(timezone.utc).isoformat()
    adapter.create_session(
        ChatSession(
            id=target_id,
            title="Original target",
            created_at=now,
            updated_at=now,
            messages=[
                ChatMessage(
                    id=f"msg:{uuid.uuid4().hex}",
                    role="user",
                    content="Existing transcript",
                    created_at=now,
                )
            ],
        )
    )

    context = multiprocessing.get_context("spawn")
    create_gate = context.Event()
    save_gate = context.Event()
    workers = []
    receivers = {}
    for action in ("mutate", "create"):
        parent, child = context.Pipe()
        process = context.Process(
            target=_mutate_chat_process,
            args=(
                os.environ["OMNIX_TEST_DATABASE_URL"],
                store.context.workspace_id,
                store.context.user_id,
                action,
                target_id,
                create_gate,
                save_gate,
                child,
            ),
        )
        process.start()
        child.close()
        workers.append(process)
        receivers[action] = parent

    try:
        assert receivers["mutate"].poll(30), "process B did not load its target session"
        loaded = receivers["mutate"].recv()
        assert loaded == {"action": "mutate", "event": "loaded"}
        create_gate.set()
        assert receivers["create"].poll(30), "process A did not create its session"
        created = receivers["create"].recv()
        save_gate.set()
        assert receivers["mutate"].poll(30), "process B did not save its target session"
        mutated = receivers["mutate"].recv()
        for process in workers:
            process.join(30)
            assert process.exitcode == 0
        assert "error" not in created, created
        assert "error" not in mutated, mutated
        created_id = created["session_id"]
        assert adapter.get_session(created_id) is not None
        mutated = adapter.get_session(target_id)
        assert mutated is not None
        assert mutated.title == "Mutated by process B"
        with database.connection() as connection:
            statuses = dict(
                connection.execute(
                    "SELECT id, status FROM omnix_chat_sessions WHERE id = ANY(%s)",
                    ([created_id, target_id],),
                ).fetchall()
            )
        assert statuses == {created_id: "active", target_id: "active"}
    finally:
        create_gate.set()
        save_gate.set()
        for process in workers:
            if process.is_alive():
                process.terminate()
            process.join(5)
        for receiver in receivers.values():
            receiver.close()


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
        released = work.jobs.release_expired_leases(store.context, job_id=job['id'])
        assert [row['id'] for row in released] == [job['id']]
        work.connection.execute(
            "UPDATE omnix_jobs SET available_at = clock_timestamp() - INTERVAL '1 second' WHERE id = %s",
            (job['id'],),
        )
        work.commit()
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
