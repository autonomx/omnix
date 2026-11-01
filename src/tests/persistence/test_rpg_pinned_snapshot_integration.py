"""A campaign's current state can be pinned as its pre-upgrade backup (RQ-1.7, migration 0170)."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=2,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-rpg-pinned-snapshot",
        )
    )


def _snapshots(database: PostgresDatabase, workspace_id: str, campaign_id: str) -> list[tuple]:
    with database.transaction() as connection:
        return connection.execute(
            "SELECT revision, pinned, document_version FROM omnix_rpg_snapshots "
            "WHERE workspace_id = %s AND campaign_id = %s ORDER BY revision",
            (workspace_id, campaign_id),
        ).fetchall()


def test_pinning_writes_a_snapshot_of_the_current_state_once_and_pins_an_existing_one() -> None:
    database = _database()
    try:
        apply_migrations(database)
        context = ensure_local_identity(database)
        campaign_id = f"campaign:pin-{uuid4().hex}"
        state = {"manifest": {"id": campaign_id, "schema_version": 5}, "simulation_state": {"tick": 1}}
        with unit_of_work(database) as work:
            work.rpg.create_campaign(context, campaign_id=campaign_id, title="Pin", state=state,
                                     engine_version="test", schema_version="test", seed="1")
            work.commit()

        with unit_of_work(database) as work:
            first = work.rpg.pin_current_state(context, campaign_id=campaign_id, document_version=5)
            work.commit()
        with unit_of_work(database) as work:
            again = work.rpg.pin_current_state(context, campaign_id=campaign_id, document_version=5)
            missing = work.rpg.pin_current_state(context, campaign_id=f"{campaign_id}:none")
            work.commit()

        assert first is not None and first["created"] is True and first["revision"] == 0
        assert again is not None and again["created"] is False and again["id"] == first["id"]
        assert missing is None
        assert _snapshots(database, context.workspace_id, campaign_id) == [(0, True, 5)]
    finally:
        database.close()
