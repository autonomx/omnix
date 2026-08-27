from __future__ import annotations

import os
import threading
import time

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import apply_migrations
from app.persistence.runtime_document_compat import (
    load_legacy_chat_sessions,
    mutate_legacy_chat_sessions,
)


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=4,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-legacy-session-concurrency-tests",
        )
    )


def test_legacy_session_mutations_are_serialized_across_connections() -> None:
    database = _database()
    try:
        apply_migrations(database)

        def reset(current: dict[str, object]) -> None:
            current.clear()

        mutate_legacy_chat_sessions(reset)

        errors: list[BaseException] = []

        def mutate(name: str, delay: float) -> None:
            try:
                def apply(current: dict[str, object]) -> None:
                    time.sleep(delay)
                    current[name] = {"messages": []}

                mutate_legacy_chat_sessions(apply)
            except BaseException as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        first = threading.Thread(target=mutate, args=("first", 0.05))
        second = threading.Thread(target=mutate, args=("second", 0.0))
        first.start()
        time.sleep(0.01)
        second.start()
        first.join(timeout=2)
        second.join(timeout=2)

        assert not errors
        assert not first.is_alive()
        assert not second.is_alive()
        assert set(load_legacy_chat_sessions()) >= {"first", "second"}
    finally:
        database.close()
