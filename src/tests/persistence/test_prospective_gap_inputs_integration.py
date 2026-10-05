"""Prospective-gap inputs are imported into PostgreSQL with provenance (WP-8.3)."""
from __future__ import annotations

import os
import random
from datetime import date, timedelta

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.unit_of_work import unit_of_work
from app.trading.prospective_gap_inputs import HandoffConflict, ProspectiveGapInputs
from src.tests.trading.test_prospective_gap_end_to_end_runtime import _scheduler_handoff_fixture

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]


@pytest.fixture()
def inputs():
    database = PostgresDatabase(
        DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=2,
                         application_name="omnix-prospective-gap-inputs-tests")
    )
    try:
        ensure_local_identity(database)
        yield ProspectiveGapInputs(uow_factory=lambda: unit_of_work(database)), database
    finally:
        database.close()


def _handoff_for(session: date) -> str:
    return _scheduler_handoff_fixture().model_copy(update={"session_date": session}).model_dump_json()


def _session() -> date:
    # A future session nobody else uses, so tests may share the database.
    return date(2400, 1, 1) + timedelta(days=random.randrange(100_000))


def test_a_handoff_is_imported_once_with_its_provenance(inputs) -> None:
    store, database = inputs
    session = _session()
    content = _handoff_for(session)
    try:
        assert store.handoff(session) is None
        store.import_handoff(content, source="file:handoff.json", imported_by="test")
        store.import_handoff(content, source="file:again.json", imported_by="test")  # same content: no-op

        assert store.handoff(session).session_date == session
        with unit_of_work(database) as uow:
            row = uow.connection.execute(
                "SELECT source, content, content_sha256 FROM omnix_trading_premarket_handoffs WHERE session_date = %s",
                (session,),
            ).fetchone()
        assert row[0] == "file:handoff.json" and row[1] == content and len(row[2]) == 64

        changed = _scheduler_handoff_fixture().model_copy(
            update={"session_date": session, "cohort_id": "another-cohort"}
        ).model_dump_json()
        with pytest.raises(HandoffConflict):
            store.import_handoff(changed, source="file:changed.json")
        assert store.handoff(session).cohort_id != "another-cohort"
    finally:
        with unit_of_work(database) as uow:
            uow.connection.execute("DELETE FROM omnix_trading_premarket_handoffs WHERE session_date = %s", (session,))
            uow.commit()


def test_the_latest_climatology_before_a_session_is_used(inputs) -> None:
    store, database = inputs
    # Migration 0124 seeds the state that used to be committed as a file.
    seeded = store.climatology_before(date(2026, 9, 24))
    assert (seeded.through_session, seeded.observation_count, seeded.positive_count) == (date(2026, 9, 23), 50, 19)

    later = _session()
    try:
        store.import_climatology(
            '{"through_session": "%s", "observation_count": 60, "positive_count": 24, "probability": "0.4"}'
            % later.isoformat(),
            source="test",
        )
        assert store.climatology_before(later).through_session < later
        assert store.climatology_before(later + timedelta(days=1)).observation_count == 60
    finally:
        with unit_of_work(database) as uow:
            uow.connection.execute("DELETE FROM omnix_trading_climatology_states WHERE through_session = %s", (later,))
            uow.commit()
