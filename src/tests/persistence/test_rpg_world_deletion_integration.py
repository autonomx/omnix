from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.worlds.contracts import ScenarioProjectCreate, WorldProjectCreate
from app.rpg.worlds.library_service import (
    save_world_topic,
    start_world_library_generation,
)
from app.rpg.worlds.lifecycle_service import (
    delete_world_project,
    world_deletion_eligibility,
)
from app.rpg.worlds.postgres_service import (
    create_scenario_project,
    create_world_project,
    publish_world_revision,
)
from app.rpg.worlds.service import compile_world_revision

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
            application_name="omnix-rpg-world-deletion",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_world_generation_runs, "
            "omnix_rpg_campaign_map_events, omnix_rpg_campaign_map_instances, "
            "omnix_rpg_map_definitions, omnix_rpg_campaign_world_bindings, "
            "omnix_rpg_scenario_revisions, omnix_rpg_scenarios, "
            "omnix_rpg_world_image_attempts, omnix_rpg_world_image_targets, "
            "omnix_rpg_world_entity_history, omnix_rpg_map_blueprint_revisions, "
            "omnix_rpg_world_topic_history, omnix_rpg_world_releases, "
            "omnix_rpg_world_revisions, omnix_rpg_world_topics, omnix_rpg_worlds, "
            "omnix_rpg_campaign_genesis_runs, omnix_rpg_narrative_responses, "
            "omnix_rpg_hermes_research, omnix_rpg_world_forge_proposals, "
            "omnix_rpg_campaign_bible_revisions, omnix_rpg_campaign_bibles, "
            "omnix_rpg_participants, omnix_rpg_snapshots, omnix_rpg_interactions, "
            "omnix_rpg_turns, omnix_rpg_campaigns, omnix_job_attempts, "
            "omnix_job_events, omnix_jobs, omnix_outbox_events, omnix_audit_events, "
            "omnix_workspace_memberships, omnix_workspaces, omnix_users CASCADE"
        )


def test_disposable_draft_world_is_deleted_with_audit_record() -> None:
    database = _database()
    try:
        _reset(database)
        world_id = "world:disposable"
        title = "Disposable Draft"
        create_world_project(
            WorldProjectCreate(world_id=world_id, title=title),
            database=database,
        )
        save_world_topic(
            world_id,
            topic_id="realm",
            content={"documents": [{"title": "Realm", "full_text": "Draft lore."}]},
            database=database,
        )
        create_scenario_project(
            ScenarioProjectCreate(
                scenario_id="scenario:disposable",
                world_id=world_id,
                title="Draft Opening",
            ),
            database=database,
        )
        start_world_library_generation(
            world_id,
            database=database,
            kick_worker=False,
        )

        eligibility = world_deletion_eligibility(world_id, database=database)[
            "eligibility"
        ]
        assert eligibility["can_delete"] is True
        assert eligibility["deleted_counts"]["topics"] == 1
        assert eligibility["deleted_counts"]["scenario_projects"] == 1

        with pytest.raises(ValueError, match="world_delete_confirmation_mismatch"):
            delete_world_project(
                world_id,
                confirmation_title="Wrong title",
                acknowledge_permanent=True,
                database=database,
            )

        result = delete_world_project(
            world_id,
            confirmation_title=title,
            acknowledge_permanent=True,
            database=database,
        )
        assert result["deleted"] is True
        assert result["world_id"] == world_id

        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            retained_world = work.world_scenarios.get_world(context, world_id)
            scenario_count = work.connection.execute(
                "SELECT COUNT(*) FROM omnix_rpg_scenarios "
                "WHERE workspace_id = %s AND world_id = %s",
                (context.workspace_id, world_id),
            ).fetchone()[0]
            queued_job_count = work.connection.execute(
                "SELECT COUNT(*) FROM omnix_jobs WHERE workspace_id = %s "
                "AND job_type = 'rpg.world_topic.generate' "
                "AND metadata->>'world_id' = %s",
                (context.workspace_id, world_id),
            ).fetchone()[0]
            audit = work.connection.execute(
                "SELECT action, payload FROM omnix_audit_events "
                "WHERE workspace_id = %s AND aggregate_type = 'rpg_world_project' "
                "AND aggregate_id = %s ORDER BY id DESC LIMIT 1",
                (context.workspace_id, world_id),
            ).fetchone()
            work.rollback()
        assert retained_world is None
        assert int(scenario_count) == 0
        assert int(queued_job_count) == 0
        assert audit is not None
        assert str(audit[0]) == "permanently_deleted"
        assert dict(audit[1])["decision"] == "explicit_typed_confirmation"
    finally:
        database.close()


def test_published_world_can_be_permanently_deleted() -> None:
    database = _database()
    try:
        _reset(database)
        world_id = "world:published-retained"
        title = "Published Retained World"
        create_world_project(
            WorldProjectCreate(world_id=world_id, title=title),
            database=database,
        )
        revision = compile_world_revision(
            world_id=world_id,
            revision=1,
            title=title,
            canon={},
            entity_manifest={},
            topology={"locations": [], "routes": []},
        )
        publish_world_revision(revision, expected_revision=0, database=database)

        eligibility = world_deletion_eligibility(world_id, database=database)[
            "eligibility"
        ]
        assert eligibility["can_delete"] is True
        assert eligibility["blockers"] == []

        result = delete_world_project(
            world_id,
            confirmation_title=title,
            acknowledge_permanent=True,
            database=database,
        )
        assert result["deleted"] is True

        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            retained_world = work.world_scenarios.get_world(context, world_id)
            work.rollback()
        assert retained_world is None
    finally:
        database.close()
