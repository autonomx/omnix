"""The launch gate reads a projection of the campaign, and decides as on the whole session (WP-5.6)."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest

from app.apps.rpg.genesis.forge.launch_readiness import campaign_launch_readiness
from app.apps.rpg.session.persistence.session_records import (
    load_launch_gate_source_from_postgres,
    save_session_to_postgres,
)
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.migrations import apply_migrations
from app.runtime.tenant_context import install_process_tenant

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

CASES = {
    "no world forge": ({}, {}, {}),
    "empty world forge": ({"world_forge": {}}, {}, {}),
    "world forge, gate ready": ({"world_forge": {"topic_graph": {"a": 1}}}, {}, {"ready": True}),
    "world forge, gate blocked": (
        {"world_forge": {"jobs": [1]}}, {},
        {"ready": False, "missing_requirements": ["places"], "required_before_first_turn": True},
    ),
    "campaign bible only": ({}, {"campaign_bible": {"documents": []}}, {"ready": False}),
    "empty campaign bible": ({}, {"campaign_bible": {}}, {}),
}


@pytest.fixture(autouse=True)
def tenant():
    database = PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=2,
            connect_timeout_seconds=10, statement_timeout_ms=30_000,
            application_name="omnix-rpg-launch-gate",
        )
    )
    apply_migrations(database)
    install_process_tenant(ensure_local_identity(database))
    try:
        yield
    finally:
        database.close()


@pytest.mark.parametrize("case", sorted(CASES))
def test_the_projection_decides_as_the_whole_session(case) -> None:
    setup, state, gate = CASES[case]
    campaign_id = f"session:gate-{uuid4().hex}"
    session = {
        "manifest": {"session_id": campaign_id, "id": campaign_id, "title": "Gate"},
        "setup_payload": setup,
        "state": {**state, "transcript": ["not read by the gate"] * 20},
        "runtime_state": {"state_revision": 1, "campaign_launch_gate": gate},
    }
    save_session_to_postgres(session)

    source = load_launch_gate_source_from_postgres(campaign_id)

    assert campaign_launch_readiness(source) == campaign_launch_readiness(session)


def test_a_missing_campaign_has_no_gate_source() -> None:
    assert load_launch_gate_source_from_postgres(f"session:missing-{uuid4().hex}") is None
