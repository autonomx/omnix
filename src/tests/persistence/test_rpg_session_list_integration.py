"""The RPG session list reads one page and only the summary fields (WP-7.6)."""
from __future__ import annotations

import json
import os
import uuid

import psycopg
import pytest

from app.apps.rpg.session.list_summaries import session_list_summary
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import PostgresIdentityRepository, ensure_local_identity
from app.runtime.tenant_context import pop_tenant, push_tenant
from tests.support.database import admin_database_url

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]

STATES = [
    # A saved game: environments, regions (one not an object), opening location and a large transcript.
    {
        "manifest": {"id": "placeholder", "title": "Harbor", "schema_version": 2, "status": "active"},
        "state": {
            "world": {
                "environment": {"weather": "rain", "wind": None},
                "regions": {"north": {"environment": {"weather": "fog"}, "lore": "x" * 500},
                            "south": {"lore": "no environment"}, "broken": "not a region"},
            },
            "scene": {"environment_context": {"light": "dim"}},
            "current_location_name": "Harbor",
            "published_world": {"world_id": "w1"},
            "location": None,
            "transcript": ["line"] * 200,
        },
    },
    # No state at all, and a manifest that is not an object.
    {"manifest": "broken"},
    # State that is not an object.
    {"manifest": {"title": "Odd"}, "state": ["not", "an", "object"]},
    # Regions that are not an object.
    {"manifest": {"title": "Plain"}, "state": {"world": {"regions": ["a"]}, "current_location": 3}},
]


@pytest.fixture
def workspace():
    """A workspace of its own, so other tests' campaigns stay out of the list."""
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=2))
    try:
        ensure_local_identity(database)
        with database.transaction() as connection:
            context = PostgresIdentityRepository(connection).create_account_with_workspace(
                user_id=f"user:rpg-list-{uuid.uuid4().hex}", display_name="RPG list", email=None,
                account_kind="standard", roles=("owner", "admin", "member"), seed_settings_from=None,
            )
    finally:
        database.close()
    token = push_tenant(context)
    try:
        yield context
    finally:
        pop_tenant(token)
        with psycopg.connect(admin_database_url(), autocommit=True) as admin:
            admin.execute("DELETE FROM omnix_workspaces WHERE id = %s", (context.workspace_id,))
            admin.execute("DELETE FROM omnix_users WHERE id = %s", (context.user_id,))


def _insert(admin, context, campaign_id: str, state: dict, *, status: str, minutes_ago: int) -> None:
    admin.execute(
        """INSERT INTO omnix_rpg_campaigns (id, workspace_id, owner_user_id, title, revision, state_jsonb, state_hash,
                                             engine_version, schema_version, seed, status, updated_at)
           VALUES (%s, %s, %s, 'List', 0, %s::jsonb, %s, 'test', 'test', 'seed', %s,
                   now() - make_interval(mins => %s))""",
        (campaign_id, context.workspace_id, context.user_id, json.dumps(state), "0" * 64, status, minutes_ago),
    )


def test_session_list_reads_one_page_with_the_summaries_full_states_give(workspace) -> None:
    from app.apps.rpg.session.persistence.session_records import (
        _campaign_state_for_listing,
        list_session_summaries_from_postgres,
    )

    expected = []
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        # Newest first: four active campaigns, then two archived ones (older updates come later).
        for index, (state, status) in enumerate([(state, "active") for state in STATES]
                                                + [(STATES[0], "archived"), (STATES[1], "archived")]):
            campaign_id = f"rpg:list:{index}:{uuid.uuid4().hex[:6]}"
            _insert(admin, workspace, campaign_id, state, status=status, minutes_ago=index)
            expected.append(session_list_summary(_campaign_state_for_listing({"id": campaign_id, "state": state})))

    assert list_session_summaries_from_postgres() == expected
    # A page that ends inside the archived campaigns, and one that ends before them.
    assert list_session_summaries_from_postgres(limit=5) == expected[:5]
    assert list_session_summaries_from_postgres(limit=2) == expected[:2]
    assert list_session_summaries_from_postgres(limit=0) == []
    first = list_session_summaries_from_postgres(limit=1)[0]
    assert first["manifest"]["session_id"] == first["manifest"]["id"]
    assert "transcript" not in first["state"]
