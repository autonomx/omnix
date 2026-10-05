"""The agent run limit holds across processes (WP-4.7)."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from uuid import uuid4

import pytest

from app.platform.agent_runtime.run_slots import AgentRunCapacityError, PostgresAgentRunSlots
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.xdist_group("agent-run-slots"),
    pytest.mark.skipif(not os.environ.get("OMNIX_TEST_DATABASE_URL"), reason="OMNIX_TEST_DATABASE_URL is required"),
]


@pytest.fixture
def database():
    """The slot count is global, so these tests take turns (also across xdist workers)."""
    # The database is migrated before the suite; the test role may not run DDL.
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=4))
    with database.dedicated_connection() as turn:
        turn.execute("SELECT pg_advisory_lock(hashtext('omnix-test-agent-run-slots'))")
        turn.commit()
        with database.transaction() as connection:
            connection.execute("DELETE FROM omnix_agent_run_slots")
        try:
            yield database
        finally:
            with database.transaction() as connection:
                connection.execute("DELETE FROM omnix_agent_run_slots")
            database.close()


def _hold_in_another_process(run_id: str, max_runs: int) -> subprocess.Popen[str]:
    script = textwrap.dedent(f"""
        import os, sys, time
        from app.platform.agent_runtime.run_slots import PostgresAgentRunSlots
        from app.persistence.config import DatabaseSettings
        from app.persistence.database import PostgresDatabase
        database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=2))
        slot = PostgresAgentRunSlots(database, max_runs={max_runs}).acquire({run_id!r}, wait_seconds=0)
        print("held", flush=True)
        sys.stdin.readline()
        slot.release()
        database.close()
    """)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [os.path.abspath("src"), env.get("PYTHONPATH", "")]))
    process = subprocess.Popen([sys.executable, "-c", script], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               text=True, env=env)
    assert process.stdout is not None and process.stdout.readline().strip() == "held"
    return process


def test_the_limit_holds_across_two_processes(database) -> None:
    other = _hold_in_another_process(f"run-{uuid4().hex}", max_runs=1)
    try:
        slots = PostgresAgentRunSlots(database, max_runs=1)
        with pytest.raises(AgentRunCapacityError, match="already running"):
            slots.acquire(f"run-{uuid4().hex}", wait_seconds=0)
        assert slots.active() == 1
    finally:
        assert other.stdin is not None
        other.stdin.write("\n")
        other.stdin.flush()
        other.wait(timeout=30)
    slot = PostgresAgentRunSlots(database, max_runs=1).acquire(f"run-{uuid4().hex}", wait_seconds=5)
    slot.release()


def test_a_waiting_run_starts_when_a_slot_frees(database) -> None:
    slots = PostgresAgentRunSlots(database, max_runs=1)
    first = slots.acquire(f"run-{uuid4().hex}", wait_seconds=0)
    started = time.monotonic()
    import threading

    threading.Timer(1.0, first.release).start()
    second = slots.acquire(f"run-{uuid4().hex}", wait_seconds=10, poll_seconds=0.2)
    assert time.monotonic() - started >= 0.9
    second.release()


def test_a_dead_holders_slot_expires(database) -> None:
    slots = PostgresAgentRunSlots(database, max_runs=1, lease_seconds=10)
    assert slots.try_acquire(f"run-{uuid4().hex}", "dead-host:1") is True
    with database.transaction() as connection:
        connection.execute("UPDATE omnix_agent_run_slots SET lease_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second'")
    assert slots.try_acquire(f"run-{uuid4().hex}", "live-host:2") is True


def test_the_same_run_restarting_keeps_its_slot(database) -> None:
    slots = PostgresAgentRunSlots(database, max_runs=1)
    run_id = f"run-{uuid4().hex}"
    assert slots.try_acquire(run_id, "host:1") is True
    assert slots.try_acquire(run_id, "host:2") is True
    assert slots.active() == 1
