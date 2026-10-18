"""A campaign stored before the current schema loads upcast from PostgreSQL (WP-5.6)."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest

from app.apps.rpg.session.campaign_state import CURRENT_SCHEMA_VERSION, CampaignState
from app.apps.rpg.session.persistence.session_records import load_session_from_postgres
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.runtime.tenant_context import install_process_tenant

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def test_a_version_two_campaign_loads_in_the_current_shape() -> None:
    database = PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=2,
            connect_timeout_seconds=10, statement_timeout_ms=30_000,
            application_name="omnix-rpg-campaign-upcast",
        )
    )
    try:
        apply_migrations(database)
        context = ensure_local_identity(database)
        install_process_tenant(context)
        campaign_id = f"session:upcast-{uuid4().hex}"
        stored = {
            "manifest": {"id": campaign_id, "session_id": campaign_id, "schema_version": 2, "title": "Old"},
            "state": {"location": "Old Road"},
            "simulation_state": {"tick": 1},
            "runtime_state": {"transcript": [{"role": "player", "text": "Hello", "turn_id": "turn:1", "tick": 1}]},
        }
        with unit_of_work(database) as work:
            work.rpg.create_campaign(
                context, campaign_id=campaign_id, title="Old", state=stored,
                engine_version="legacy", schema_version="rpg-session-v1", seed="1",
            )
            work.commit()

        loaded = load_session_from_postgres(campaign_id)
        assert loaded is not None
        state = CampaignState.model_validate(loaded)
        assert state.manifest.schema_version == CURRENT_SCHEMA_VERSION
        assert state.runtime_state["ambient_queue"] == []
        assert state.runtime_state["interaction_timeline"]["events"]
    finally:
        database.close()
