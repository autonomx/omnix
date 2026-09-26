"""Readiness must work when PostgreSQL itself forbids writes."""

from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.runtime import ensure_postgresql_runtime_ready

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="requires disposable PostgreSQL test database",
)


def test_gateway_readiness_succeeds_in_read_only_postgresql_sessions():
    url = os.environ["OMNIX_TEST_DATABASE_URL"]
    writable = PostgresDatabase(DatabaseSettings(url=url))
    try:
        ensure_postgresql_runtime_ready(writable)
    finally:
        writable.close()
    separator = "&" if "?" in url else "?"
    database = PostgresDatabase(
        DatabaseSettings(
            url=url + separator + "options=-c%20default_transaction_read_only%3Don"
        )
    )
    try:
        with database.connection() as connection:
            assert (
                connection.execute("SHOW transaction_read_only").fetchone()[0] == "on"
            )
        status = ensure_postgresql_runtime_ready(
            database, auto_initialize_fresh_install=False, apply_schema_changes=False
        )
        assert status.ready
        assert status.backend == "postgresql"
    finally:
        database.close()
