"""Trading monitor ownership is composed as per-task scheduler work."""

import asyncio
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
    assert len(FEATURE.scheduled_tasks) == 22
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

    assert all(isinstance(task, ScheduledTaskSpec) for task in tasks)
    task_ids = [task.task_id for task in tasks]
    assert len(task_ids) == len(set(task_ids)) == 22
    assert all(task.interval_seconds > 0 for task in tasks)
    assert all(
        RuntimeCapability.RUN_SCHEDULERS in task.requires for task in tasks
    )
    startup_tasks = {
        task.task_id.rsplit(".", 1)[-1]
        for task in tasks
        if task.on_startup
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

    asyncio.run(
        task.run(
            TaskContext(
                task_id=task.task_id,
                workspace_id="workspace-a",
                scheduled_at=datetime.now(timezone.utc),
            )
        )
    )

    assert len(started) == 1
