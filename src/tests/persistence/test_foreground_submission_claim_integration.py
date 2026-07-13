from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.foreground_submission_compat import PostgresForegroundSubmissionStoreAdapter
from app.persistence.migrations import apply_migrations


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database(application_name: str) -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=4,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name=application_name,
        )
    )


def test_concurrent_postgresql_claims_select_one_authoritative_owner() -> None:
    first_database = _database("omnix-foreground-claim-first")
    second_database = _database("omnix-foreground-claim-second")
    session_id = f"campaign:claim:{uuid.uuid4().hex}"
    submission_id = f"submission:claim:{uuid.uuid4().hex}"

    try:
        apply_migrations(first_database)
        first = PostgresForegroundSubmissionStoreAdapter(first_database)
        second = PostgresForegroundSubmissionStoreAdapter(second_database)
        barrier = Barrier(2)

        def claim(store: PostgresForegroundSubmissionStoreAdapter):
            barrier.wait(timeout=5)
            return store.claim(
                session_id,
                submission_id,
                lease_seconds=300,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = list(executor.map(claim, (first, second)))

        owners = [claim for claim in claims if claim.owner]
        duplicates = [claim for claim in claims if not claim.owner]
        assert len(owners) == 1
        assert len(duplicates) == 1
        assert owners[0].claim_token
        assert duplicates[0].claim_token is None
        assert {claim.status for claim in claims} == {"claimed"}

        with first_database.connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*), MIN(status), COUNT(DISTINCT claim_token)
                  FROM omnix_rpg_foreground_submissions
                 WHERE session_id = %s AND submission_id = %s
                """,
                (session_id, submission_id),
            ).fetchone()
        assert int(row[0]) == 1
        assert str(row[1]) == "claimed"
        assert int(row[2]) == 1
    finally:
        first_database.close()
        second_database.close()
