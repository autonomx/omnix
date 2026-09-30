"""Focused scheduler contracts and lifecycle regression tests."""

import asyncio
from contextlib import AsyncExitStack, contextmanager, nullcontext
from datetime import datetime, timezone
import threading
import time

import pytest

from app.config.runtime import GatewayRole, RuntimeConfig
from app.runtime.capabilities import RuntimeCapabilities, RuntimeCapability
from app.runtime.scheduler import (
    ScheduledTaskSpec,
    SchedulerOwnershipUnavailable,
    SchedulerRuntime,
    TaskContext,
    next_cron_time,
)


class _FakeConnection:
    def __init__(self, database):
        self.database = database
        self.closed = False
        self.lock_key = None

    def execute(self, statement, parameters=()):
        if "pg_try_advisory_lock" in statement:
            key = parameters[0]
            with self.database.lock:
                acquired = key not in self.database.keys
                if acquired:
                    self.database.keys.add(key)
                    self.lock_key = key
            return _FakeCursor((acquired,))
        if "pg_advisory_unlock" in statement:
            with self.database.lock:
                self.database.keys.discard(parameters[0])
            self.lock_key = None
            return _FakeCursor((True,))
        return _FakeCursor((1,))

    def commit(self):
        return None

    def close(self):
        self.closed = True


class _FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _FakeDatabase:
    def __init__(self):
        self.lock = threading.Lock()
        self.keys = set()

    @contextmanager
    def connection(self):
        connection = _FakeConnection(self)
        try:
            yield connection
        finally:
            connection.closed = True


def _capabilities(role=GatewayRole.WORKER):
    return RuntimeCapabilities.from_config(RuntimeConfig(gateway_role=role))


def _execution_scope(_owner):
    return nullcontext()


def test_scheduled_task_requires_exactly_one_schedule_and_serial_async_callback():
    async def run(_context: TaskContext):
        return None

    with pytest.raises(ValueError, match="exactly one"):
        ScheduledTaskSpec(task_id="bad", run=run)
    with pytest.raises(ValueError, match="max_overlap=1"):
        ScheduledTaskSpec(task_id="bad", run=run, interval_seconds=1, max_overlap=2)
    with pytest.raises(ValueError, match="awaitable"):
        ScheduledTaskSpec(
            task_id="bad",
            run=lambda _context: None,
            interval_seconds=1,
        )


def test_cron_next_time_supports_ranges_steps_and_utc_weekdays():
    after = datetime(2026, 9, 30, 8, 58, tzinfo=timezone.utc)
    assert next_cron_time("*/15 9-10 * * 1-5", after) == datetime(
        2026, 9, 30, 9, 0, tzinfo=timezone.utc
    )
    friday = datetime(2026, 10, 2, 23, 59, tzinfo=timezone.utc)
    assert next_cron_time("0 8 * * 1", friday) == datetime(
        2026, 10, 5, 8, 0, tzinfo=timezone.utc
    )
    with pytest.raises(ValueError, match="five fields"):
        next_cron_time("*/5 * *", after)


def test_scheduler_owns_task_runs_serially_and_records_metrics():
    database = _FakeDatabase()
    calls = []

    async def run(context: TaskContext):
        calls.append(context.task_id)
        await asyncio.sleep(0.002)

    scheduler = SchedulerRuntime(
        database,
        "workspace-a",
        capabilities=_capabilities(),
        execution_scope=_execution_scope,
        startup_jitter_seconds=0,
        thread_workers=1,
        process_workers=1,
    )
    scheduler.register_task(
        ScheduledTaskSpec(
            task_id="test.serial",
            run=run,
            interval_seconds=0.005,
            timeout_seconds=0.1,
        )
    )
    async def scenario():
        await scheduler.startup()
        await asyncio.sleep(0.04)
        assert scheduler.diagnostics()["owned_tasks"] == ["test.serial"]
        await scheduler.shutdown()

    asyncio.run(scenario())
    diagnostics = scheduler.diagnostics()
    assert len(calls) >= 2
    assert diagnostics["tasks"]["test.serial"]["run_count"] == len(calls)
    assert diagnostics["owned_tasks"] == []
    assert database.keys == set()


def test_scheduler_lock_key_encodes_workspace_and_task_boundaries():
    database = _FakeDatabase()

    async def run(_context: TaskContext):
        return None

    schedulers = (
        SchedulerRuntime(
            database,
            "workspace:with-separator",
            capabilities=_capabilities(),
            execution_scope=_execution_scope,
            startup_jitter_seconds=0,
        ),
        SchedulerRuntime(
            database,
            "workspace",
            capabilities=_capabilities(),
            execution_scope=_execution_scope,
            startup_jitter_seconds=0,
        ),
    )
    schedulers[0].register_task(
        ScheduledTaskSpec(task_id="task", run=run, interval_seconds=10)
    )
    schedulers[1].register_task(
        ScheduledTaskSpec(task_id="with-separator:task", run=run, interval_seconds=10)
    )

    async def scenario():
        await schedulers[0].startup()
        await schedulers[1].startup()
        assert schedulers[0].owns_task("task")
        assert schedulers[1].owns_task("with-separator:task")
        await schedulers[1].shutdown()
        await schedulers[0].shutdown()

    asyncio.run(scenario())
    assert database.keys == set()


def test_api_role_registers_no_scheduler_authority():
    database = _FakeDatabase()
    calls = []

    async def run(_context: TaskContext):
        calls.append("ran")

    scheduler = SchedulerRuntime(
        database,
        "workspace-a",
        capabilities=_capabilities(GatewayRole.API),
        execution_scope=_execution_scope,
        startup_jitter_seconds=0,
    )
    scheduler.register_task(
        ScheduledTaskSpec(task_id="test.api-denied", run=run, interval_seconds=0.01)
    )
    async def scenario():
        await scheduler.startup()
        await asyncio.sleep(0.02)
        with pytest.raises(SchedulerOwnershipUnavailable, match="control authority"):
            await scheduler.pause_task("test.api-denied")
        with pytest.raises(SchedulerOwnershipUnavailable, match="control authority"):
            scheduler.resume_task("test.api-denied")
        await scheduler.shutdown()

    asyncio.run(scenario())
    assert calls == []
    assert database.keys == set()


def test_task_pause_waits_for_current_run_and_resume_triggers_a_new_run():
    database = _FakeDatabase()
    calls = []

    async def run(_context: TaskContext):
        calls.append("run")
        await asyncio.sleep(0.005)

    scheduler = SchedulerRuntime(
        database,
        "workspace-a",
        capabilities=_capabilities(),
        execution_scope=_execution_scope,
        startup_jitter_seconds=0,
    )
    scheduler.register_task(
        ScheduledTaskSpec(
            task_id="test.controls",
            run=run,
            interval_seconds=0.1,
        )
    )

    async def scenario():
        await scheduler.startup()
        for _ in range(100):
            if scheduler.diagnostics()["tasks"]["test.controls"]["run_count"]:
                break
            await asyncio.sleep(0.002)
        assert scheduler.diagnostics()["tasks"]["test.controls"]["run_count"] == 1
        await scheduler.pause_task("test.controls")
        paused_count = len(calls)
        await asyncio.sleep(0.15)
        assert len(calls) == paused_count
        scheduler.resume_task("test.controls")
        for _ in range(100):
            if len(calls) > paused_count:
                break
            await asyncio.sleep(0.002)
        assert len(calls) > paused_count
        await scheduler.shutdown()

    asyncio.run(scenario())
    assert database.keys == set()


def test_scheduler_skips_tasks_when_declared_capabilities_are_missing():
    database = _FakeDatabase()
    calls = []

    async def run(_context: TaskContext):
        calls.append("ran")

    scheduler = SchedulerRuntime(
        database,
        "workspace-a",
        capabilities=_capabilities(GatewayRole.SCHEDULER),
        execution_scope=_execution_scope,
        startup_jitter_seconds=0,
    )
    scheduler.register_task(
        ScheduledTaskSpec(
            task_id="test.capability-denied",
            run=run,
            interval_seconds=0.01,
            requires=frozenset(
                {
                    RuntimeCapability.RUN_SCHEDULERS,
                    RuntimeCapability.OWN_BACKGROUND_RUNTIME,
                }
            ),
        )
    )

    async def scenario():
        await scheduler.startup()
        await asyncio.sleep(0.02)
        assert scheduler.diagnostics()["owned_tasks"] == []
        await scheduler.shutdown()

    asyncio.run(scenario())
    assert calls == []
    assert database.keys == set()


def test_unowned_task_moves_to_another_scheduler_after_owner_stops():
    database = _FakeDatabase()
    calls = []
    active = 0
    maximum_active = 0
    active_lock = threading.Lock()

    def make_run(owner):
        async def run(_context: TaskContext):
            nonlocal active, maximum_active
            with active_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            try:
                calls.append(owner)
                await asyncio.sleep(0.01)
            finally:
                with active_lock:
                    active -= 1

        return run

    schedulers = []
    for owner in ("first", "second"):
        scheduler = SchedulerRuntime(
            database,
            "workspace-a",
            capabilities=_capabilities(),
            execution_scope=_execution_scope,
            startup_jitter_seconds=0,
            poll_seconds=0.005,
        )
        scheduler.register_task(
            ScheduledTaskSpec(
                task_id="test.failover",
                run=make_run(owner),
                interval_seconds=0.02,
            )
        )
        schedulers.append(scheduler)

    async def scenario():
        first, second = schedulers
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(first.lifespan())
            await stack.enter_async_context(second.lifespan())
            for _ in range(100):
                if calls:
                    break
                await asyncio.sleep(0.002)
            assert first.owns_task("test.failover")
            assert not second.owns_task("test.failover")
            await first.shutdown()
            for _ in range(100):
                if second.owns_task("test.failover"):
                    break
                await asyncio.sleep(0.002)
            assert second.owns_task("test.failover")
            for _ in range(100):
                if "second" in calls:
                    break
                await asyncio.sleep(0.002)
            assert "second" in calls

    asyncio.run(scenario())
    assert maximum_active == 1
    assert database.keys == set()


def test_thread_executor_keeps_task_lock_until_cancelled_work_exits():
    database = _FakeDatabase()
    first_started = threading.Event()
    first_finished = threading.Event()
    allow_first_finish = threading.Event()
    second_started = threading.Event()
    state_lock = threading.Lock()
    active = 0
    maximum_active = 0

    def make_run(owner):
        def run(_context: TaskContext):
            nonlocal active, maximum_active
            with state_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            try:
                if owner == "first":
                    first_started.set()
                    allow_first_finish.wait()
                    first_finished.set()
                else:
                    second_started.set()
            finally:
                with state_lock:
                    active -= 1

        return run

    schedulers = []
    for owner in ("first", "second"):
        scheduler = SchedulerRuntime(
            database,
            "workspace-a",
            capabilities=_capabilities(),
            execution_scope=_execution_scope,
            startup_jitter_seconds=0,
            poll_seconds=0.005,
            thread_workers=1,
        )
        scheduler.register_task(
            ScheduledTaskSpec(
                task_id="test.thread-cancellation",
                run=make_run(owner),
                interval_seconds=10,
                executor="thread",
            )
        )
        schedulers.append(scheduler)

    async def scenario():
        first, second = schedulers
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(first.lifespan())
            await stack.enter_async_context(second.lifespan())
            assert await asyncio.wait_for(
                asyncio.to_thread(first_started.wait), timeout=0.2
            )
            async def release_after_check():
                await asyncio.sleep(0.04)
                try:
                    assert not second.owns_task("test.thread-cancellation")
                    assert not second_started.is_set()
                finally:
                    allow_first_finish.set()

            release = asyncio.create_task(release_after_check())
            await first.shutdown()
            await release
            for _ in range(100):
                if second_started.is_set():
                    break
                await asyncio.sleep(0.002)
            assert first_finished.is_set()
            assert second_started.is_set()

    asyncio.run(scenario())
    assert maximum_active == 1
    assert database.keys == set()


def test_scheduler_records_positive_lag_when_event_loop_misses_interval():
    database = _FakeDatabase()

    async def run(_context: TaskContext):
        return None

    scheduler = SchedulerRuntime(
        database,
        "workspace-a",
        capabilities=_capabilities(),
        execution_scope=_execution_scope,
        startup_jitter_seconds=0,
    )
    scheduler.register_task(
        ScheduledTaskSpec(
            task_id="test.lag",
            run=run,
            interval_seconds=0.05,
            timeout_seconds=0.5,
        )
    )

    async def scenario():
        await scheduler.startup()
        for _ in range(100):
            if scheduler.diagnostics()["tasks"]["test.lag"]["run_count"] >= 1:
                break
            await asyncio.sleep(0.002)
        await asyncio.sleep(0.002)
        time.sleep(0.08)
        for _ in range(100):
            if scheduler.diagnostics()["tasks"]["test.lag"]["run_count"] >= 2:
                break
            await asyncio.sleep(0.002)
        assert scheduler.diagnostics()["tasks"]["test.lag"]["run_count"] >= 2
        await scheduler.shutdown()

    asyncio.run(scenario())
    metric = scheduler.diagnostics()["tasks"]["test.lag"]
    assert metric["last_lag_seconds"] >= 0.02
    assert database.keys == set()


def test_scheduler_shutdown_cancels_an_active_async_callback():
    database = _FakeDatabase()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def run(_context: TaskContext):
        started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    scheduler = SchedulerRuntime(
        database,
        "workspace-a",
        capabilities=_capabilities(),
        execution_scope=_execution_scope,
        startup_jitter_seconds=0,
    )
    scheduler.register_task(
        ScheduledTaskSpec(
            task_id="test.shutdown-cancellation",
            run=run,
            interval_seconds=1,
        )
    )

    async def scenario():
        await scheduler.startup()
        await asyncio.wait_for(started.wait(), timeout=0.1)
        await scheduler.shutdown()

    asyncio.run(scenario())
    assert cancelled.is_set()
    assert database.keys == set()


def test_failed_task_startup_runs_shutdown_cleanup():
    database = _FakeDatabase()
    lifecycle = []

    async def run(_context: TaskContext):
        lifecycle.append("run")

    async def startup():
        lifecycle.append("started")
        raise RuntimeError("startup failed")

    async def shutdown():
        lifecycle.append("stopped")

    scheduler = SchedulerRuntime(
        database,
        "workspace-a",
        capabilities=_capabilities(),
        execution_scope=_execution_scope,
        startup_jitter_seconds=0,
    )
    scheduler.register_task(
        ScheduledTaskSpec(
            task_id="test.failed-startup",
            run=run,
            interval_seconds=1,
            on_startup=(startup,),
            on_shutdown=(shutdown,),
        )
    )

    async def scenario():
        await scheduler.startup()
        for _ in range(100):
            if not scheduler._runner_tasks:
                break
            await asyncio.sleep(0.002)
        assert not scheduler._runner_tasks
        await scheduler.shutdown()

    asyncio.run(scenario())
    assert lifecycle == ["started", "stopped"]
    assert database.keys == set()


def test_timeout_fails_closed_after_callback_finishes_without_rescheduling():
    database = _FakeDatabase()
    calls = []

    async def run(_context: TaskContext):
        calls.append("started")
        try:
            await asyncio.sleep(0.03)
        except asyncio.CancelledError:
            calls.append("cancelled")
            raise

    scheduler = SchedulerRuntime(
        database,
        "workspace-a",
        capabilities=_capabilities(),
        execution_scope=_execution_scope,
        startup_jitter_seconds=0,
        poll_seconds=0.005,
    )
    scheduler.register_task(
        ScheduledTaskSpec(
            task_id="test.timeout",
            run=run,
            interval_seconds=0.005,
            timeout_seconds=0.005,
        )
    )
    async def scenario():
        await scheduler.startup()
        for _ in range(200):
            if not scheduler._runner_tasks:
                break
            await asyncio.sleep(0.005)
        assert not scheduler._runner_tasks
        await scheduler.shutdown()

    asyncio.run(scenario())
    metric = scheduler.diagnostics()["tasks"]["test.timeout"]
    assert calls == ["started", "cancelled"]
    assert metric["timeout_count"] == 1
    assert metric["failure_count"] == 1
    assert database.keys == set()
