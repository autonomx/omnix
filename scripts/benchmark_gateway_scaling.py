"""Concurrent Chat transactions and process-loss recovery on disposable PostgreSQL."""
from __future__ import annotations

import argparse
import json
import multiprocessing
import os
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace
from urllib.parse import urlparse
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


def services(url, workspace_id):
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.job_runtime_compat import PostgresJobStoreAdapter
    from app.chat.persistence.chat_compat import PostgresChatRepositoryAdapter
    from app.chat.persistence.chat_runtime_compat import PostgresCharacterChatSessionStore
    from app.persistence.repositories import PostgresIdentityRepository
    from app.gateway import _install_required_rpg_turn_hooks
    from app.gateway import live_chat_postgres_fast_path as fast
    database = PostgresDatabase(DatabaseSettings(url=url, pool_max=4))
    store = PostgresJobStoreAdapter(database)
    with database.connection() as connection:
        store.context = PostgresIdentityRepository(connection).load_context(
            user_id=store.context.user_id, workspace_id=workspace_id)
    _install_required_rpg_turn_hooks()
    # Exercise real admission and transcript SQL while omitting model providers
    # and auxiliary assistant-turn bookkeeping from this controlled workload.
    fast.default_assistant_turn_coordinator = lambda: SimpleNamespace(get=lambda _: None)
    fast._start_assistant_turn = lambda session, message, request: message.metadata.update(user_turn_id=request.user_turn_id)
    fast.stream_log = lambda *args, **kwargs: None
    chat = PostgresCharacterChatSessionStore.__new__(PostgresCharacterChatSessionStore)
    chat._repository = PostgresChatRepositoryAdapter(database)
    chat._repository.context = store.context
    chat._run_post_turn_maintenance = lambda *args: None
    return database, store, chat


def submit(store, chat, session_id, submission_id):
    from app.chat.generation_jobs import chat_submission_lock, find_chat_generation_job
    from app.chat.models import SendChatMessageRequest
    from app.jobs.models import CreateJobRequest, ResourceClass
    with chat_submission_lock(session_id, submission_id, job_store=store, chat_store=chat):
        existing = find_chat_generation_job(store, session_id=session_id, submission_id=submission_id)
        if existing is not None:
            return existing, False
        session, message = chat.begin_user_message(session_id, SendChatMessageRequest(content='benchmark', user_turn_id=submission_id))
        job = store.create_job(CreateJobRequest(module='chatbot', type='chat.generate',
            resource_class=ResourceClass.GPU_LLM,
            input_payload={'session_id': session.id, 'message_id': message.id, 'submission_id': submission_id},
            compat={'inline_execution': True}))
        return job, True


def load_process(url, workspace_id, sessions, submissions, pipe):
    from app.persistence.gateway_runtime import GatewayRuntimeOwner
    from app.jobs.models import CompleteJobRequest
    database, store, chat = services(url, workspace_id)
    owner = GatewayRuntimeOwner(database, workspace_id, lease_seconds=120)
    owner.register()
    store.chat_execution_owner = owner
    timings = []
    created = 0
    try:
        pipe.send({'ready': True})
        pipe.recv()
        started = time.perf_counter()
        for index in range(submissions):
            session_id = sessions[index % len(sessions)]
            admission = time.perf_counter()
            job, new = submit(store, chat, session_id, f'submission:{index}')
            timings.append((time.perf_counter() - admission) * 1000)
            if new:
                created += 1
                deadline = time.monotonic() + 20
                while store.try_start_chat_job(job.id) is None:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Generation ordering did not advance')
                    time.sleep(.01)
                with store.chat_completion(chat, job.id):
                    chat.complete_streamed_reply(session_id, job.input_payload['message_id'], 'controlled reply', {})
                    store.complete_job(job.id, CompleteJobRequest())
        pipe.send({'admission_ms': timings, 'created': created, 'elapsed_seconds': time.perf_counter() - started})
    except BaseException as exc:
        pipe.send({'error': type(exc).__name__, 'message': str(exc)})
        raise
    finally:
        owner._mutate(lambda repository: repository.stop(owner.node_id))
        database.close()
        pipe.close()


def crash_process(url, workspace_id, session_id, pipe):
    from app.persistence.gateway_runtime import GatewayRuntimeOwner
    database, store, chat = services(url, workspace_id)
    owner = GatewayRuntimeOwner(database, workspace_id, lease_seconds=2, heartbeat_seconds=.5)
    owner.register()
    store.chat_execution_owner = owner
    job, _ = submit(store, chat, session_id, 'crash-submission')
    store.mark_running(job.id)
    pipe.send({'job_id': job.id, 'node_id': owner.node_id})
    # Parent terminates this exact child after acceptance; no graceful cleanup.
    pipe.recv()


def run_load(url, workspace_id, sessions, submissions, workers):
    context = multiprocessing.get_context('spawn')
    children = []
    try:
        for _ in range(workers):
            parent, child = context.Pipe()
            process = context.Process(target=load_process, args=(url, workspace_id, sessions, submissions, child))
            process.start()
            child.close()
            children.append((process, parent))
        for process, pipe in children:
            if not pipe.poll(45) or pipe.recv() != {'ready': True}:
                raise RuntimeError('Load child did not become ready')
        started = time.perf_counter()
        for _, pipe in children:
            pipe.send('start')
        results = []
        for process, pipe in children:
            if not pipe.poll(45):
                raise RuntimeError('Load child timed out')
            result = pipe.recv()
            if 'error' in result:
                raise RuntimeError(result)
            results.append(result)
            process.join(5)
            assert process.exitcode == 0
        elapsed = time.perf_counter() - started
        values = sorted(value for result in results for value in result['admission_ms'])
        assert sum(result['created'] for result in results) == submissions
        return {'processes': workers, 'sessions': len(sessions), 'attempted': submissions * workers,
                'unique_jobs': submissions, 'elapsed_seconds': elapsed,
                'admission_p50_ms': statistics.median(values),
                'admission_p95_ms': values[min(len(values) - 1, int(len(values) * .95))],
                'attempts_per_second': len(values) / elapsed}
    finally:
        for process, pipe in children:
            if process.is_alive():
                process.terminate()
                process.join(5)
            pipe.close()


def measure(url, workers, submissions):
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.job_runtime_compat import PostgresJobStoreAdapter
    from app.persistence.repositories import PostgresIdentityRepository
    from app.persistence.unit_of_work import unit_of_work
    from app.chat.generation_jobs import recover_abandoned_chat_generation_jobs
    database = PostgresDatabase(DatabaseSettings(url=url))
    store = PostgresJobStoreAdapter(database)
    workspace_id = f'workspace:scaling-benchmark:{uuid.uuid4().hex}'
    try:
        with database.transaction() as connection:
            connection.execute("INSERT INTO omnix_workspaces (id, name, created_by) VALUES (%s, 'Scaling benchmark', %s)",
                               (workspace_id, store.context.user_id))
            connection.execute('INSERT INTO omnix_workspace_memberships (id, workspace_id, user_id, roles) VALUES (%s, %s, %s, %s)',
                (f'membership:{uuid.uuid4().hex}', workspace_id, store.context.user_id, ['owner', 'admin', 'member']))
            store.context = PostgresIdentityRepository(connection).load_context(user_id=store.context.user_id, workspace_id=workspace_id)
        sessions = []
        with unit_of_work(database) as work:
            for index in range(submissions + 2):
                row = work.chats.create_session(store.context, {'id': f'{workspace_id}:session:{index}', 'title': 'Load test'})
                sessions.append(row['id'])
            work.commit()
        distributed = run_load(url, workspace_id, sessions[:submissions], submissions, workers)
        contended = run_load(url, workspace_id, sessions[-2:-1], submissions, workers)
        with database.connection() as connection:
            counts = connection.execute("SELECT count(*), count(*) FILTER (WHERE status = 'completed') FROM omnix_jobs WHERE workspace_id = %s",
                                        (workspace_id,)).fetchone()
            messages = connection.execute('SELECT count(*) FROM omnix_chat_messages WHERE workspace_id = %s', (workspace_id,)).fetchone()[0]
        assert counts == (submissions * 2, submissions * 2)
        assert messages == submissions * 4

        context = multiprocessing.get_context('spawn')
        parent, child = context.Pipe()
        process = context.Process(target=crash_process, args=(url, workspace_id, sessions[-1], child))
        process.start()
        child.close()
        try:
            if not parent.poll(45):
                raise RuntimeError('Crash child failed to accept work')
            accepted = parent.recv()
            assert recover_abandoned_chat_generation_jobs(None, store) == 0
            process.terminate()
            process.join(5)
            started = time.perf_counter()
            recovered = 0
            while not recovered and time.perf_counter() - started < 10:
                recovered = recover_abandoned_chat_generation_jobs(None, store)
                if not recovered:
                    time.sleep(.1)
            assert recovered == 1
            job = store.get_job(accepted['job_id'])
            assert job.status.value == 'failed'
            assert sum(event.event_type == 'job.failed' for event in store.list_events(job.id)) == 1
            crash = {'terminated_child_exit_code': process.exitcode,
                     'configured_lease_seconds': 2, 'explicit_recovery_poll_seconds': .1,
                     'detected_after_termination_ms': (time.perf_counter() - started) * 1000,
                     'recovered_jobs': recovered, 'terminal_events': 1}
        finally:
            if process.is_alive():
                process.terminate()
                process.join(5)
            parent.close()
        return {'schema_version': 1, 'mode': 'multiprocess_disposable_postgresql_no_external_providers',
                'distributed_sessions': distributed, 'single_contended_session': contended,
                'completed_jobs': counts[1], 'persisted_messages': messages, 'process_loss': crash}
    finally:
        with database.transaction() as connection:
            connection.execute("DELETE FROM omnix_runtime_nodes WHERE metadata ->> 'workspace_id' = %s", (workspace_id,))
            connection.execute('DELETE FROM omnix_workspaces WHERE id = %s', (workspace_id,))
        database.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--submissions', type=int, default=40)
    parser.add_argument('--local-disposable', action='store_true')
    args = parser.parse_args()
    url = os.environ.get('OMNIX_BENCHMARK_DATABASE_URL', '')
    if args.local_disposable:
        url = 'postgresql://omnix_baseline:baseline_disposable@127.0.0.1:16432/omnix_refactor_baseline'
    if urlparse(url).path != '/omnix_refactor_baseline' or not 1 <= args.workers <= 8 or not 1 <= args.submissions <= 1000:
        parser.error('requires disposable omnix_refactor_baseline database, 1–8 workers and 1–1000 submissions')
    result = measure(url, args.workers, args.submissions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
