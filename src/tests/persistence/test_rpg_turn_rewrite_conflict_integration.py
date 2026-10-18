"""A turn may not rewrite the revision it committed; an edit outside a turn advances it (WP-5.6)."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest

from app.apps.rpg.session.persistence.session_records import (
    TurnStateRewriteConflict,
    load_session_version_from_postgres,
    save_session_to_postgres,
)
from app.jobs.foreground_execution import ForegroundExecution, foreground_execution
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.errors import RevisionConflict
from app.persistence.identity_service import ensure_local_identity
from app.persistence.migrations import apply_migrations
from app.runtime.tenant_context import install_process_tenant

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


@pytest.fixture
def tenant():
    database = PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=2,
            connect_timeout_seconds=10, statement_timeout_ms=30_000,
            application_name="omnix-rpg-turn-rewrite",
        )
    )
    apply_migrations(database)
    context = ensure_local_identity(database)
    install_process_tenant(context)
    try:
        yield context
    finally:
        database.close()


def _session(campaign_id: str, revision: int, note: str) -> dict:
    return {
        "manifest": {"session_id": campaign_id, "id": campaign_id, "title": "Rewrite"},
        "state": {"note": note},
        "runtime_state": {"state_revision": revision},
    }


def test_inside_its_turn_a_campaign_cannot_be_rewritten_at_the_committed_revision(tenant) -> None:
    campaign_id = f"session:rewrite-{uuid4().hex}"
    save_session_to_postgres(_session(campaign_id, 3, "committed"))
    execution = ForegroundExecution(
        workspace_id=tenant.workspace_id, session_id=campaign_id,
        submission_id="submit:1", job_id="job:1", claim_token="claim",
    )

    with foreground_execution(execution):
        with pytest.raises(TurnStateRewriteConflict):
            save_session_to_postgres(_session(campaign_id, 3, "rewritten after the commit"))
        # Saving what the turn committed again is harmless.
        save_session_to_postgres(_session(campaign_id, 3, "committed"))
    assert load_session_version_from_postgres(campaign_id)[0] == 3

    # Another campaign's turn does not block it, and an edit outside a turn advances it.
    other = ForegroundExecution(
        workspace_id=tenant.workspace_id, session_id="session:other",
        submission_id="submit:2", job_id="job:2", claim_token="claim",
    )
    with foreground_execution(other):
        save_session_to_postgres(_session(campaign_id, 3, "renamed"))
    assert load_session_version_from_postgres(campaign_id)[0] == 4
    assert issubclass(TurnStateRewriteConflict, RevisionConflict)


def test_the_turn_route_answers_a_revision_conflict_with_409(monkeypatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.apps.rpg.edge.api import turn_pipeline
    from app.apps.rpg.edge.api.feature_routes.rpg_session_routes import register_rpg_session_routes
    from tests.support.routers import include_router_registrar

    def conflicting(**_kwargs):
        raise TurnStateRewriteConflict("rewrote revision 3")

    monkeypatch.setattr(turn_pipeline, "_execute_foreground_rpg_turn", conflicting)
    app = FastAPI()
    include_router_registrar(app, register_rpg_session_routes)
    client = TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})

    response = client.post("/api/rpg/sessions/session:any/turn", json={"command": "look"})

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "rpg_state_revision_conflict"
