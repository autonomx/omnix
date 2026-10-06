"""Outbox consumer registry and run-stream wake-ups (WP-5.3)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.events.outbox_relay import (
    OutboxConsumer,
    OutboxConsumerRegistry,
    outbox_consumer_registry,
    retry_delay_seconds,
)
from app.events.run_streams import RUN_AGGREGATE_TYPES, RunEventWakeups


def _consumer(name: str, *kinds: str, pattern: str = "*") -> OutboxConsumer:
    return OutboxConsumer(name, frozenset(kinds), lambda connection, event: None, pattern)


def test_consumers_match_aggregate_type_and_event_pattern() -> None:
    registry = OutboxConsumerRegistry([_consumer("all", "agent_run"), _consumer("done", "agent_run", pattern="run.completed")])
    started = {"aggregate_type": "agent_run", "event_type": "run.started"}
    completed = {"aggregate_type": "agent_run", "event_type": "run.completed"}
    other = {"aggregate_type": "workflow_run", "event_type": "run.completed"}

    assert [c.consumer_name for c in registry.for_event(started)] == ["all"]
    assert [c.consumer_name for c in registry.for_event(completed)] == ["all", "done"]
    assert registry.for_event(other) == ()


def test_consumer_names_are_unique() -> None:
    registry = OutboxConsumerRegistry([_consumer("one", "agent_run")])
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(_consumer("one", "workflow_run"))


def test_the_kernel_registry_covers_run_events_and_feature_consumers() -> None:
    feature = SimpleNamespace(outbox_consumers=(_consumer("feature-consumer", "settings"),))
    registry = outbox_consumer_registry([feature])

    assert RUN_AGGREGATE_TYPES <= registry.consumed_aggregate_types()
    assert "settings" in registry.consumed_aggregate_types()


def test_retry_delay_grows_and_is_capped() -> None:
    assert retry_delay_seconds(1) < retry_delay_seconds(3)
    assert retry_delay_seconds(50) == 300


def test_a_notification_during_a_read_is_not_lost() -> None:
    wakeups = RunEventWakeups(None)  # no database: wake() stands in for NOTIFY

    async def scenario() -> tuple[bool, bool]:
        with wakeups.subscribe("ws:agent_run:run-1") as subscription:
            wakeups.wake("ws:agent_run:run-1")  # arrives while the stream reads
            await asyncio.sleep(0)
            woken = await subscription.wait(timeout=1)
            quiet = await subscription.wait(timeout=0.05)
        return woken, quiet

    assert asyncio.run(scenario()) == (True, False)


def test_wakeups_are_delivered_only_to_the_matching_run() -> None:
    wakeups = RunEventWakeups(None)

    async def scenario() -> bool:
        with wakeups.subscribe("ws:agent_run:run-1") as subscription:
            wakeups.wake("ws:agent_run:run-2")
            return await subscription.wait(timeout=0.05)

    assert asyncio.run(scenario()) is False
