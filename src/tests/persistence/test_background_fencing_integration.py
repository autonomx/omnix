"""Fencing tokens stop a background owner that lost its lock (WP-8.3)."""
from __future__ import annotations

import threading

import pytest

from app.persistence.background_authority import background_execution
from app.persistence.unit_of_work import unit_of_work
from app.runtime.background import BackgroundOwnershipUnavailable, GatewayBackgroundRuntime
from app.runtime.scheduler import SchedulerOwnershipUnavailable, _SchedulerLockSession, _TaskOwner
from src.tests.persistence import test_chat_execution_ownership_integration as ownership

pytestmark = ownership.pytestmark


@pytest.fixture(name="runtime")
def fencing_runtime():
    yield from ownership.runtime.__wrapped__()


def _lose_lock(owner: GatewayBackgroundRuntime) -> None:
    """The lock goes (as when its connection drops) while the process still believes it owns it."""
    owner.connection.execute("SELECT pg_advisory_unlock(%s)", (owner.lock_key,))
    owner.connection.commit()


def test_a_stale_owner_cannot_write_after_another_process_takes_over(runtime) -> None:
    database, store, _ = runtime
    stale = GatewayBackgroundRuntime(database, store.context.workspace_id)
    successor = GatewayBackgroundRuntime(database, store.context.workspace_id)
    stale.acquire()
    try:
        with background_execution(stale):
            with unit_of_work(database) as work:
                work.commit()
        _lose_lock(stale)
        successor.acquire()
        assert successor.epoch == stale.epoch + 1

        with background_execution(stale):
            with pytest.raises(BackgroundOwnershipUnavailable, match="moved to another process"):
                with unit_of_work(database):
                    pytest.fail("a stale owner opened a unit of work")
        assert stale.healthy is False
        with background_execution(successor):
            with database.transaction() as connection:
                assert connection.execute("SELECT 1").fetchone() == (1,)
    finally:
        stale.release()
        successor.release()


def test_a_takeover_waits_for_the_stale_owners_open_transaction(runtime) -> None:
    database, store, _ = runtime
    stale = GatewayBackgroundRuntime(database, store.context.workspace_id)
    successor = GatewayBackgroundRuntime(database, store.context.workspace_id)
    stale.acquire()
    try:
        taken_over = threading.Event()
        with background_execution(stale):
            work = unit_of_work(database).__enter__()
            try:
                _lose_lock(stale)
                thread = threading.Thread(target=lambda: (successor.acquire(), taken_over.set()))
                thread.start()
                # The successor holds the advisory lock but its epoch bump waits
                # for the stale owner's transaction, which still holds the epoch.
                assert not taken_over.wait(0.5)
                work.commit()
            finally:
                work.__exit__(None, None, None)
        thread.join(10)
        assert taken_over.is_set()
        assert successor.epoch == stale.epoch + 1
    finally:
        stale.release()
        successor.release()


def test_a_scheduled_task_that_lost_its_lock_is_fenced(runtime) -> None:
    database, store, _ = runtime
    key = 7_340_000_000_000_000 + int(store.context.workspace_id.encode().hex()[:6], 16)
    first, second = (_SchedulerLockSession(database, store.context.workspace_id, lambda _c: None) for _ in range(2))
    first.open()
    second.open()
    try:
        stale = _TaskOwner(first, "fencing-test", key)
        assert stale.acquire()
        with background_execution(stale):
            with unit_of_work(database) as work:
                work.commit()
        first.connection.execute("SELECT pg_advisory_unlock(%s)", (key,))
        first.connection.commit()
        successor = _TaskOwner(second, "fencing-test", key)
        assert successor.acquire()

        with background_execution(stale):
            with pytest.raises(SchedulerOwnershipUnavailable, match="moved to another process"):
                with database.connection():
                    pytest.fail("a stale task checked out a connection")
        with background_execution(successor):
            with unit_of_work(database) as work:
                work.commit()
    finally:
        first.close()
        second.close()
