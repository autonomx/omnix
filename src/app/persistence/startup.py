"""Explicit PostgreSQL application startup boundary."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .database import PostgresDatabase, default_database
from .runtime import RuntimePersistenceStatus, ensure_postgresql_runtime_ready


def bootstrap_postgresql_runtime(
    database: PostgresDatabase | None = None,
) -> RuntimePersistenceStatus:
    """Verify PostgreSQL authority exactly once at process startup.

    This function is the supported persistence bootstrap for application
    processes. It is deliberately explicit so importing modules, running pip,
    collecting tests, or executing one-shot scripts does not contact the
    database unexpectedly.
    """

    db = database or default_database()
    return ensure_postgresql_runtime_ready(db)


def bootstrap_status_payload(
    database: PostgresDatabase | None = None,
) -> dict[str, Any]:
    status = bootstrap_postgresql_runtime(database)
    payload = asdict(status)
    payload["mode"] = status.mode.value
    return payload
