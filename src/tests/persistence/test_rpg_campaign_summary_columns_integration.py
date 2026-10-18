"""Campaign summary columns match the Python projections of the full state (WP-5.6, migration 0157).

A trigger keeps a list row's projection and the turn count, player level and
location name next to the state, so a session list never reads saved games.
The projection lives in SQL; these tests hold it to the Python list summary
and the turn response's session summary.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest

from app.apps.rpg.narration.presentation.turn_response import _session_summary
from app.apps.rpg.session.list_summaries import session_list_summary
from app.apps.rpg.session.persistence.session_records import (
    _campaign_state_for_listing,
    list_session_summaries_from_postgres,
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


@pytest.fixture(autouse=True)
def tenant():
    database = PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=2,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-rpg-campaign-summary",
        )
    )
    apply_migrations(database)
    install_process_tenant(ensure_local_identity(database))
    try:
        yield database
    finally:
        database.close()


def _session(session_id: str, **state: object) -> dict:
    return {
        "manifest": {"session_id": session_id, "id": session_id, "title": "Harbor", "created_at": "2026-10-15T00:00:00+00:00"},
        "state": {
            "world": {
                "environment": {"weather": "fog", "season": "autumn"},
                "regions": {"region:coast": {"environment": {"weather": "rain"}, "name": "Coast"}, "region:none": "x"},
            },
            "scene": {"environment_context": {"light": "dim"}, "location_name": "Salt Harbor"},
            "current_location_id": "location:harbor",
            "published_world": {"world_id": "world:glass-sea"},
            "player": {"level": 3},
            "transcript": ["not part of a list row"] * 50,
            **state,
        },
        "runtime_state": {"state_revision": 1},
    }


def _listed(session_id: str) -> dict:
    rows = [row for row in list_session_summaries_from_postgres() if row["manifest"]["session_id"] == session_id]
    assert len(rows) == 1
    return rows[0]


def _expected(session_id: str, session: dict) -> dict:
    summary = session_list_summary(_campaign_state_for_listing({"id": session_id, "state": session}))
    typed = _session_summary(session)
    summary["manifest"].update(
        turn_count=typed.get("turn_count"),
        player_level=typed.get("player_level"),
        location_name=typed.get("location"),
    )
    return summary


def test_list_rows_and_typed_columns_follow_every_state_write() -> None:
    session_id = f"session:summary-{uuid4().hex}"
    created = _session(session_id)
    save_session_to_postgres(created)
    assert _listed(session_id) == _expected(session_id, created)

    updated = _session(session_id, scene={"location": "The Old Mill"}, player={"level": 4})
    updated["manifest"]["turn_count"] = 7
    updated["runtime_state"]["state_revision"] = 2
    save_session_to_postgres(updated)
    listed = _listed(session_id)
    assert listed == _expected(session_id, updated)
    assert listed["manifest"]["turn_count"] == 7
    assert listed["manifest"]["player_level"] == 4
    assert listed["manifest"]["location_name"] == "The Old Mill"


def test_typed_columns_fall_back_like_the_turn_summary() -> None:
    session_id = f"session:summary-{uuid4().hex}"
    session = _session(session_id, player={}, scene={})
    session["state"].pop("player")
    session["simulation_state"] = {"player_state": {"level": 9}, "location": "Crossroads"}
    session["turn_count"] = 12
    save_session_to_postgres(session)
    listed = _listed(session_id)
    assert listed == _expected(session_id, session)
    assert (listed["manifest"]["turn_count"], listed["manifest"]["player_level"]) == (12, 9)
    assert listed["manifest"]["location_name"] == "Crossroads"
