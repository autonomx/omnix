"""A turn's stages share one load of the saved game until the turn commits (WP-5.6)."""
from __future__ import annotations

import os
import threading
from uuid import uuid4

import pytest

from app.apps.rpg.foundation.persistence.rpg_session_save_policy import (
    forget_turn_session,
    rpg_session_save_policy,
)
from app.apps.rpg.session import durable_store, service
from app.apps.rpg.session.persistence.session_records import save_session_to_postgres
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.migrations import apply_migrations
from app.runtime.tenant_context import install_process_tenant

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


@pytest.fixture
def campaign_id():
    database = PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=2,
            connect_timeout_seconds=10, statement_timeout_ms=30_000,
            application_name="omnix-rpg-turn-session-cache",
        )
    )
    apply_migrations(database)
    install_process_tenant(ensure_local_identity(database))
    campaign = f"session:cache-{uuid4().hex}"
    save_session_to_postgres({
        "manifest": {"session_id": campaign, "id": campaign, "title": "Cache"},
        "state": {"note": "stored"},
        "runtime_state": {"state_revision": 1},
    })
    try:
        yield campaign
    finally:
        database.close()


def test_a_turn_reads_the_saved_game_once_until_it_commits(campaign_id, monkeypatch) -> None:
    reads: list[str] = []
    original = durable_store.load_session_from_disk

    def counting(session_id, **kwargs):
        reads.append(session_id)
        return original(session_id, **kwargs)

    monkeypatch.setattr(service, "load_session_from_disk", counting)

    with rpg_session_save_policy(defer=True):
        first = service.load_session(campaign_id)
        first["state"]["note"] = "changed by a stage"
        second = service.load_session(campaign_id)
        assert second["state"]["note"] == "stored", "each load is an independent copy"
        assert reads == [campaign_id], "the second load comes from the turn's shared load"

        # Another request saves meanwhile (a thread starts without the turn's
        # context): the turn keeps its load; its commit is revision-checked.
        edit = threading.Thread(target=save_session_to_postgres, args=({
            "manifest": {"session_id": campaign_id, "id": campaign_id, "title": "Cache"},
            "state": {"note": "edited elsewhere"},
            "runtime_state": {"state_revision": 1},
        },))
        edit.start()
        edit.join()
        assert service.load_session(campaign_id)["state"]["note"] == "stored"

        forget_turn_session(campaign_id)  # what the turn's commit does
        assert service.load_session(campaign_id)["state"]["note"] == "edited elsewhere"
    assert reads == [campaign_id, campaign_id]

    # Outside a turn every load reads.
    service.load_session(campaign_id)
    assert len(reads) == 3
