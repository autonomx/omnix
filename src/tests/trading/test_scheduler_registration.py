"""Trading monitor ownership is composed as per-task scheduler work."""

import asyncio
import inspect
from datetime import datetime, timezone
from logging import getLogger
from types import SimpleNamespace

from app.config.runtime import RuntimeConfig
from app.runtime.capabilities import RuntimeCapabilities, RuntimeCapability
from app.runtime.features import FeatureContext
from app.runtime.scheduler import ScheduledTaskSpec, TaskContext
from app.trading.feature import FEATURE


def test_all_trading_monitors_are_declared_as_unique_scheduler_tasks(monkeypatch):
    monkeypatch.setenv("OMNIX_PERSISTENCE_MODE", "legacy_test")
    monkeypatch.setenv("OMNIX_ALLOW_LEGACY_TEST_PERSISTENCE", "1")
    assert FEATURE.background_workers == ()
    # 22 monitors, the generic strategy runner and the prospective-gap input import (WP-8.3).
    assert len(FEATURE.scheduled_tasks) == 24
    config = RuntimeConfig()
    context = FeatureContext(
        feature_id="trading",
        config=None,
        runtime=config,
        capabilities=RuntimeCapabilities.from_config(config),
        services=None,
        logger=getLogger("tests.trading.scheduler"),
        runtime_state=SimpleNamespace(),
    )

    *monitor_factories, runner_factory, handoff_import_factory = FEATURE.scheduled_tasks
    # No runner strategy is registered yet, so the runner has no task; the
    # prospective-gap input import runs by default.
    assert runner_factory(context) is None
    assert handoff_import_factory(context).task_id == "trading.prospective_gap_handoff_import"
    tasks = [factory(context) for factory in monitor_factories]

    assert all(isinstance(task, ScheduledTaskSpec) for task in tasks)
    task_ids = [task.task_id for task in tasks]
    assert len(task_ids) == len(set(task_ids)) == 22
    assert all(task.interval_seconds > 0 for task in tasks)
    assert any(task.executor.value == "async" for task in tasks)
    assert any(task.executor.value == "thread" for task in tasks)
    assert all(
        RuntimeCapability.RUN_SCHEDULERS in task.requires for task in tasks
    )
    # Every task marks its monitor running when it starts; these also prepare state.
    startup_tasks = {
        task.task_id.rsplit(".", 1)[-1]
        for task in tasks
        if len(task.on_startup) > 1
    }
    assert startup_tasks == {
        "metric_monitor",
        "strategy_monitor",
        "strategy_solana_ai_monitor",
        "strategy_universe_archive_monitor",
    }


def test_alpaca_status_stream_starts_from_its_scheduled_task(monkeypatch):
    from app.trading.providers import alpaca_iex_status

    started = []
    monkeypatch.setattr(alpaca_iex_status, "_enabled", lambda: True)
    monkeypatch.setattr(
        alpaca_iex_status.AlpacaIexStatusMonitor,
        "start",
        lambda self: started.append(self),
    )
    config = RuntimeConfig()
    context = FeatureContext(
        feature_id="trading",
        config=None,
        runtime=config,
        capabilities=RuntimeCapabilities.from_config(config),
        services=None,
        logger=getLogger("tests.trading.scheduler"),
        runtime_state=SimpleNamespace(),
    )
    tasks = [factory(context) for factory in FEATURE.scheduled_tasks]
    task = next(
        task
        for task in tasks
        if task is not None and task.task_id.endswith("alpaca_iex_status")
    )

    result = task.run(
        TaskContext(
            task_id=task.task_id,
            workspace_id="workspace-a",
            scheduled_at=datetime.now(timezone.utc),
        )
    )
    if inspect.isawaitable(result):
        asyncio.run(result)

    assert len(started) == 1


def test_monitors_share_the_scheduled_base_and_have_no_loops_of_their_own(monkeypatch):
    """The scheduler owns the loop (WP-8.3): no monitor starts a task of its own."""
    from app.trading.monitor_task import ScheduledTradingMonitor

    monkeypatch.setenv("OMNIX_PERSISTENCE_MODE", "legacy_test")
    monkeypatch.setenv("OMNIX_ALLOW_LEGACY_TEST_PERSISTENCE", "1")
    config = RuntimeConfig()
    state = SimpleNamespace()
    context = FeatureContext(
        feature_id="trading",
        config=None,
        runtime=config,
        capabilities=RuntimeCapabilities.from_config(config),
        services=None,
        logger=getLogger("tests.trading.scheduler"),
        runtime_state=state,
    )
    for factory in FEATURE.scheduled_tasks[:-2]:
        factory(context)
    monitors = list(vars(state).values())
    assert len(monitors) == 22
    # Stream owners keep a connection open under their task; they are not loops.
    streams = {"AlpacaIexStatusMonitor"}
    for monitor in monitors:
        assert isinstance(monitor, ScheduledTradingMonitor), type(monitor)
        assert not hasattr(monitor, "_loop") or type(monitor).__name__ in streams
        assert not hasattr(monitor, "_run_loop")


def test_a_failed_cycle_is_logged_with_the_monitor_event_and_reaches_the_scheduler(monkeypatch):
    from app.trading import monitor_task
    from app.trading.monitor_task import ScheduledTradingMonitor, TradingMonitorTask, scheduled_task_spec

    logged = []
    monkeypatch.setattr(monitor_task, "trade_log", lambda *args, **fields: logged.append((args, fields)))

    class Failing(ScheduledTradingMonitor):
        error_event = "failing_monitor_error"

        async def run_once(self):
            raise RuntimeError("provider down")

    monitor = Failing()
    spec = scheduled_task_spec(TradingMonitorTask(name="tests.failing", monitor=monitor, enabled=lambda: True))
    context = TaskContext(task_id=spec.task_id, workspace_id="w", scheduled_at=datetime.now(timezone.utc))
    try:
        asyncio.run(spec.run(context))
    except RuntimeError:
        pass
    else:
        raise AssertionError("the scheduler must see the failure")
    assert monitor.last_error == "RuntimeError: provider down"
    assert logged == [(
        ("auto_trading", "failing_monitor_error"),
        {"error_type": "RuntimeError", "detail": "provider down", "execution_authority": False},
    )]

    # Running is reported only while the scheduler runs the task in this process.
    assert monitor.scheduled is False
    for callback in spec.on_startup:
        callback()
    assert monitor.scheduled is True
    for callback in spec.on_shutdown:
        callback()
    assert monitor.scheduled is False


def test_side_work_runs_once_per_key_beside_the_cycle_and_stops_with_the_task():
    from app.trading.monitor_task import SingleFlightTasks

    async def scenario():
        errors = []
        release = asyncio.Event()
        started = []
        tasks = SingleFlightTasks(on_error=errors.append)

        async def slow(name):
            started.append(name)
            await release.wait()

        async def failing():
            raise ValueError("model unavailable")

        assert tasks.start("strategy-a", lambda: slow("first")) is True
        # A second cycle does not wait for, or duplicate, the running annotation.
        assert tasks.start("strategy-a", lambda: slow("second")) is False
        assert tasks.start("strategy-b", failing) is True
        await asyncio.sleep(0.01)
        assert started == ["first"]
        assert [str(error) for error in errors] == ["model unavailable"]
        await tasks.close()
        return tasks

    tasks = asyncio.run(scenario())
    assert tasks._tasks == {}


def test_proposals_never_wait_on_the_intraday_llm():
    import inspect as source_inspect

    from app.trading.strategy_monitor import TradingStrategyMonitor

    evaluation = source_inspect.getsource(TradingStrategyMonitor._evaluate_candidates)
    assert "await self._run_intraday_llm" not in evaluation
    assert "intraday_llm_annotations.start" in evaluation
