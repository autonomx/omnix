"""Connection and transaction management (WP-5.10)."""
from __future__ import annotations

import os

import psycopg
import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.connection_budget import connection_budget, deployment_process_counts
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.unit_of_work import unit_of_work
from app.runtime.statement_class import statement_class
from app.runtime.tenant_context import install_process_tenant

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]


@pytest.fixture
def database():
    db = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=2))
    install_process_tenant(ensure_local_identity(db))
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def statements(monkeypatch):
    """Statements the application sends on its connections."""
    sent: list[str] = []
    original = psycopg.Connection.execute

    def counting(self, query, *args, **kwargs):
        sent.append(str(query))
        return original(self, query, *args, **kwargs)

    monkeypatch.setattr(psycopg.Connection, "execute", counting)
    return sent


def test_a_transaction_needs_no_preamble_round_trips(database, statements) -> None:
    with database.transaction() as connection:  # warm the pool and session scope
        connection.execute("SELECT 1")
    statements.clear()

    with database.transaction() as connection:
        isolation = connection.execute("SHOW transaction_isolation").fetchone()[0]

    # Before WP-5.10 every transaction also sent SET LOCAL ISOLATION and a
    # lock_timeout set_config; BEGIN now carries the isolation level.
    assert statements == ["SHOW transaction_isolation"]
    assert isolation == "read committed"


def test_a_unit_of_work_sends_only_the_authority_check_first(database, statements) -> None:
    with unit_of_work(database) as work:
        work.rollback()
    statements.clear()

    with unit_of_work(database) as work:
        work.connection.execute("SELECT 1")
        work.rollback()

    assert len(statements) == 2  # authority check, then the work itself


def test_statement_classes_set_their_timeout_only_when_it_differs(database) -> None:
    with database.transaction() as connection:
        default = connection.execute("SHOW statement_timeout").fetchone()[0]
    with statement_class("maintenance"), database.transaction() as connection:
        maintenance = connection.execute("SHOW statement_timeout").fetchone()[0]
    with statement_class("job"), unit_of_work(database) as work:
        job = work.connection.execute("SHOW statement_timeout").fetchone()[0]
        work.rollback()

    assert default == "30s"
    assert maintenance == "2min"
    assert job == "30s"  # equal to the session default: no extra statement


def test_dedicated_connections_stay_outside_the_pool(database) -> None:
    database.open()
    before = database.pool_statistics()
    with database.dedicated_connection() as connection:
        assert connection.execute("SELECT pg_try_advisory_lock(424242)").fetchone()[0] is True
        during = database.pool_statistics()
        connection.execute("SELECT pg_advisory_unlock(424242)")
    assert during.get("pool_size") == before.get("pool_size")


def test_connection_budget_warns_above_eighty_percent(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_DATABASE_POOL_MAX", raising=False)
    counts = deployment_process_counts("api=4, worker=1, job-worker=2, scheduler=1")
    assert counts == {"api": 4, "worker": 1, "job-worker": 2, "scheduler": 1}

    budget = connection_budget(100, counts)

    # (10+3)*4 + (10+3) + (5+3)*2 + (3+3) = 87 of 100
    assert budget["expected_connections"] == 87
    assert budget["warning"] is True
    assert connection_budget(200, counts)["warning"] is False
