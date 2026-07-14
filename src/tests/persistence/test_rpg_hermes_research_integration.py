from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.narrative_engine import (
    HermesResearchPolicy,
    HermesResearchRequest,
    normalize_hermes_research,
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
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-rpg-hermes-research-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_hermes_research, omnix_rpg_world_forge_proposals, "
            "omnix_rpg_campaign_bible_revisions, omnix_rpg_campaign_bibles, "
            "omnix_rpg_participants, omnix_rpg_snapshots, omnix_rpg_interactions, "
            "omnix_rpg_turns, omnix_rpg_campaigns, omnix_outbox_events, "
            "omnix_audit_events, omnix_workspace_memberships, omnix_workspaces, "
            "omnix_users CASCADE"
        )


def test_hermes_research_is_append_only_campaign_scoped_and_idempotent() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        request = HermesResearchRequest(
            research_id="research:integration",
            campaign_id="campaign:hermes",
            query="East Road history",
        )
        result = normalize_hermes_research(
            request,
            {
                "provider": "fixture",
                "sources": [
                    {
                        "source_id": "source:ledger",
                        "title": "Road Ledger",
                        "citation": "ledger:12",
                    }
                ],
                "findings": [
                    {
                        "finding_id": "finding:mud",
                        "content": "The ledger records seasonal mud.",
                        "source_refs": ["source:ledger"],
                        "authority": "historical_record",
                    }
                ],
            },
            policy=HermesResearchPolicy(max_sources=2, max_findings=2),
        )
        with unit_of_work(database) as work:
            work.rpg.create_campaign(
                context,
                campaign_id="campaign:hermes",
                title="Hermes Research",
                state={"runtime_state": {"state_revision": 0}},
                engine_version="rne-test",
                schema_version="rpg-session-v1",
                seed="fixed",
            )
            created = work.hermes_research.create(
                context,
                research_id=request.research_id,
                campaign_id=request.campaign_id,
                request=request.as_dict(),
                result=result.as_dict(),
            )
            replay = work.hermes_research.create(
                context,
                research_id=request.research_id,
                campaign_id=request.campaign_id,
                request=request.as_dict(),
                result=result.as_dict(),
            )
            work.commit()

        assert created == replay
        assert created["source_count"] == 1
        assert created["finding_count"] == 1
        assert created["content_hash"] == result.content_hash
        assert created["result"]["metadata"]["read_only"] is True
        with unit_of_work(database) as work:
            rows = work.hermes_research.list_for_campaign(context, "campaign:hermes")
            work.rollback()
        assert [row["research_id"] for row in rows] == ["research:integration"]
    finally:
        database.close()
