from __future__ import annotations

import asyncio
import gc
import threading
from types import SimpleNamespace
import weakref

import pytest

from app.chat import generation_jobs as jobs
from app.persistence.gateway_runtime import GatewayRuntimeOwner


def work(job_id, store, session="session-1"):
    return jobs._ChatGenerationWork(
        chat_store=None,
        job_store=store,
        job=SimpleNamespace(id=job_id, input_payload={"session_id": session}),
        request=object(),
        context_builder=None,
        completion_hook=None,
    )


def test_dispatcher_counts_running_and_pending_work_and_releases_capacity(monkeypatch):
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = []

    def run(**kwargs):
        calls.append(kwargs["job"].id)
        if kwargs["job"].id == "one":
            entered.set()
            assert release.wait(3)
        else:
            finished.set()

    monkeypatch.setattr(jobs, "_run_chat_generation_job", run)
    store = SimpleNamespace(
        get_job=lambda job_id: SimpleNamespace(id=job_id, status=jobs.JobStatus.QUEUED),
        mark_running=lambda job_id: SimpleNamespace(
            id=job_id, status=jobs.JobStatus.RUNNING
        ),
    )
    dispatcher = jobs._ChatGenerationDispatcher(worker_count=1, outstanding_limit=2)
    try:
        dispatcher.submit(work("one", store))
        assert entered.wait(1)
        dispatcher.submit(work("two", store))
        with pytest.raises(jobs.ChatQueueFull):
            dispatcher.submit(work("three", store))
        assert dispatcher._outstanding == 2
        assert list(dispatcher._pending["session-1"])[0].job.id == "two"
    finally:
        release.set()
    assert finished.wait(1)
    dispatcher._ready_sessions.join()
    assert dispatcher._outstanding == 0
    assert calls == ["one", "two"]


def test_full_queue_returns_durable_failed_job_and_drops_cancel_event(monkeypatch):
    item = SimpleNamespace(
        id="capacity-rejected", status=jobs.JobStatus.QUEUED, input_payload={}
    )

    def submit(work):
        raise jobs.ChatQueueFull("capacity exhausted")

    def fail(job_id, request):
        assert request.code == "chat_queue_full"
        assert request.retryable is True
        item.status = jobs.JobStatus.FAILED
        return item

    monkeypatch.setattr(jobs, "_dispatcher", SimpleNamespace(submit=submit))
    store = SimpleNamespace(get_job=lambda _: item, fail_job=fail)
    result = jobs.start_chat_generation_job(
        chat_store=None, job_store=store, job=item, request=object()
    )
    assert result.status == jobs.JobStatus.FAILED
    assert jobs._job_cancel_event(item.id) is None


def test_idle_registry_locks_are_collected_without_changing_active_lock_identity():
    registry = weakref.WeakValueDictionary()
    lock = jobs._registry_lock(registry, "test")
    assert jobs._registry_lock(registry, "test") is lock
    del lock
    gc.collect()
    assert "test" not in registry


def test_terminal_recovery_interrupts_provider_and_cannot_become_canceled():
    current = SimpleNamespace(status=jobs.JobStatus.FAILED)
    store = SimpleNamespace(get_job=lambda _: current)
    assert jobs._cancel_requested(store, "failed")
    jobs._cancel_chat_turn(
        object(), store, SimpleNamespace(id="failed"), "session", "message"
    )
    assert current.status == jobs.JobStatus.FAILED


def test_durable_recovery_uses_paged_candidates_and_rechecks_transition():
    calls = []
    candidates = [SimpleNamespace(id=str(index)) for index in range(701)]

    def transition(job_id):
        calls.append(job_id)
        return (
            None
            if job_id == "0"
            else SimpleNamespace(status=jobs.JobStatus.FAILED, input_payload={})
        )

    store = SimpleNamespace(
        iter_recoverable_chat_jobs=lambda: iter(candidates), recover_chat_job=transition
    )
    assert jobs.recover_abandoned_chat_generation_jobs(None, store) == 700
    assert len(calls) == 701


def test_heartbeat_failure_latches_owner_unavailable(monkeypatch):
    owner = GatewayRuntimeOwner(object(), "workspace", heartbeat_seconds=0.001)
    owner.healthy = True

    def fail():
        raise RuntimeError("connection lost")

    monkeypatch.setattr(owner, "heartbeat", fail)
    asyncio.run(asyncio.wait_for(owner._heartbeats(), timeout=1))
    assert owner.healthy is False
    assert owner.ready() is False


def test_owner_lifespan_runs_recovery_and_stops_its_node(monkeypatch):
    owner = GatewayRuntimeOwner(
        object(), "workspace", heartbeat_seconds=0.001, recovery_seconds=0.001
    )
    recovered = threading.Event()
    operations = []
    repository = SimpleNamespace(
        register=lambda **kwargs: operations.append("register"),
        heartbeat=lambda **kwargs: operations.append("heartbeat"),
        stop=lambda node_id: operations.append("stop"),
    )
    monkeypatch.setattr(owner, "_mutate", lambda operation: operation(repository))
    owner.recover = recovered.set

    async def run():
        async with owner.lifespan():
            assert owner.healthy
            assert await asyncio.to_thread(recovered.wait, 1)
        assert not owner.healthy

    asyncio.run(run())
    assert operations[0] == "register"
    assert operations[-1] == "stop"


@pytest.mark.parametrize("workers,limit", [(0, 2), (2, 1)])
def test_invalid_dispatcher_capacity_is_rejected(workers, limit):
    with pytest.raises(ValueError):
        jobs._ChatGenerationDispatcher(worker_count=workers, outstanding_limit=limit)


@pytest.mark.parametrize(
    "lease,heartbeat,recovery", [(0, 0.1, 1), (3601, 5, 15), (30, 30, 15), (30, 5, 0)]
)
def test_invalid_gateway_lease_intervals_are_rejected(lease, heartbeat, recovery):
    with pytest.raises(ValueError):
        GatewayRuntimeOwner(
            object(),
            "workspace",
            lease_seconds=lease,
            heartbeat_seconds=heartbeat,
            recovery_seconds=recovery,
        )


def test_provider_call_limit_must_accommodate_the_workers():
    with pytest.raises(ValueError):
        jobs._ChatGenerationDispatcher(worker_count=2, outstanding_limit=4, provider_call_limit=1)


def _provider_calls(monkeypatch, reply, *, limit=2, poll=30.0):
    """A dispatcher whose provider pool runs ``reply`` for every turn."""
    dispatcher = jobs._ChatGenerationDispatcher(
        worker_count=1, outstanding_limit=2, provider_call_limit=limit
    )
    monkeypatch.setattr(jobs, "_dispatcher", dispatcher)
    monkeypatch.setattr(jobs, "_CROSS_PROCESS_CANCEL_POLL_SECONDS", poll)
    monkeypatch.setattr(jobs, "_chat_provider_id", lambda *_args: "remote")
    monkeypatch.setattr(jobs, "_generate_reply", lambda *_args, **_kwargs: reply())
    return dispatcher


def _generate(job_id, store):
    return jobs._generate_reply_with_interrupt(
        chat_store=None, job_store=store, session=None, user_message=None,
        request=None, context_items=[], job=SimpleNamespace(id=job_id),
    )


def _running_store(reads=None):
    def get_job(job_id):
        if reads is not None:
            reads.append(job_id)
        return SimpleNamespace(status=jobs.JobStatus.RUNNING)

    return SimpleNamespace(get_job=get_job)


def test_a_cancelled_turn_wakes_at_once_and_interrupts_its_provider(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def reply():
        entered.set()
        release.wait(5)
        return {"content": "late"}

    dispatcher = _provider_calls(monkeypatch, reply)
    reads, interrupts, outcome = [], [], {}

    class Provider:
        def cancel_active_request(self, owner=None):
            interrupts.append(owner)
            release.set()
            return True

    def run():
        try:
            _generate("job-a", _running_store(reads))
        except jobs._ChatGenerationInterrupted:
            outcome["interrupted"] = True

    jobs._register_active_chat_provider("job-a", Provider())
    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert entered.wait(2)
        jobs._job_cancel_event("job-a").cancel()
        # The job store is polled every 30 s here, so finishing proves the
        # cancellation itself woke the turn.
        worker.join(2)
        assert not worker.is_alive()
        assert outcome == {"interrupted": True}
        assert interrupts == ["job-a"]
        assert reads == ["job-a"]  # only the check before the call
    finally:
        release.set()
        jobs._drop_active_chat_provider("job-a")
        jobs._drop_job_cancel_event("job-a")
        dispatcher.close(timeout=0)


def test_a_cancel_recorded_by_another_process_is_read_from_the_job_store(monkeypatch):
    release = threading.Event()
    dispatcher = _provider_calls(monkeypatch, lambda: release.wait(5) and None, poll=0.01)
    statuses = iter([jobs.JobStatus.RUNNING])
    store = SimpleNamespace(
        get_job=lambda _job_id: SimpleNamespace(status=next(statuses, jobs.JobStatus.CANCEL_REQUESTED))
    )
    try:
        with pytest.raises(jobs._ChatGenerationInterrupted):
            _generate("job-b", store)
    finally:
        release.set()
        jobs._drop_job_cancel_event("job-b")
        dispatcher.close(timeout=0)


def test_provider_calls_are_bounded_and_a_cancelled_queued_call_never_runs(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def reply():
        calls.append("call")
        entered.set()
        release.wait(5)
        return {"content": "done"}

    dispatcher = _provider_calls(monkeypatch, reply, limit=1)
    results, outcome = {}, {}
    submitted = []
    queued = threading.Event()
    submit = dispatcher.submit_provider_call

    def recording_submit(call):
        future = submit(call)
        submitted.append(future)
        if len(submitted) == 2:
            queued.set()
        return future

    monkeypatch.setattr(dispatcher, "submit_provider_call", recording_submit)

    def run_first():
        results["first"] = _generate("job-1", _running_store())

    def run_second():
        try:
            _generate("job-2", _running_store())
        except jobs._ChatGenerationInterrupted:
            outcome["interrupted"] = True

    first = threading.Thread(target=run_first)
    second = threading.Thread(target=run_second)
    try:
        first.start()
        assert entered.wait(2)
        second.start()
        # The second call waits in the pool's queue behind the first.
        assert queued.wait(2)
        assert dispatcher.diagnostics()["provider_calls_in_flight"] == 2
        jobs._job_cancel_event("job-2", create=True).cancel()
        second.join(2)
        assert outcome == {"interrupted": True}
        release.set()
        first.join(2)
        assert results["first"] == {"content": "done"}
        assert calls == ["call"]
        assert submitted[1].cancelled()
        # The count is released by the first done-callback, before the turn wakes.
        assert dispatcher.diagnostics()["provider_calls_in_flight"] == 0
    finally:
        release.set()
        for job_id in ("job-1", "job-2"):
            jobs._drop_job_cancel_event(job_id)
        dispatcher.close(timeout=0)
