from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
)
from app.rpg.session.genesis.world_forge_default import ReferenceSafeWorldForgeGenerator
from app.rpg.session.genesis.world_forge_deterministic import DeterministicWorldForgeGenerator
from app.rpg.worlds.generation_coordinator import start_world_generation
from app.rpg.worlds.generation_jobs import WorldTopicGenerationSettings
from app.rpg.worlds.generation_publication import publish_world_generation
from app.rpg.worlds.generation_worker import run_world_generation_worker_once

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


@pytest.fixture(autouse=True)
def _deterministic_world_forge_test_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RPG_TEST_MODE", "deterministic")


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-rpg-world-generation-publication",
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
            "omnix_rpg_world_releases, omnix_rpg_world_revisions, "
            "omnix_rpg_world_topics, omnix_rpg_worlds, "
            "omnix_rpg_campaign_genesis_runs, omnix_rpg_narrative_responses, "
            "omnix_rpg_hermes_research, omnix_rpg_world_forge_proposals, "
            "omnix_rpg_campaign_bible_revisions, omnix_rpg_campaign_bibles, "
            "omnix_rpg_participants, omnix_rpg_snapshots, omnix_rpg_interactions, "
            "omnix_rpg_turns, omnix_rpg_campaigns, omnix_job_attempts, "
            "omnix_job_events, omnix_jobs, omnix_outbox_events, omnix_audit_events, "
            "omnix_workspace_memberships, omnix_workspaces, omnix_users CASCADE"
        )


def _graph() -> CampaignTopicGraph:
    return CampaignTopicGraph(
        graph_version="world-publication-integration-v1",
        campaign_template="classic_fantasy",
        depth="quick",
        nodes=(
            CampaignTopicNode(
                topic_id="realm",
                title="Realm",
                category="lore",
                generator_role="realm_architect",
            ),
            CampaignTopicNode(
                topic_id="regions",
                title="Regions",
                category="regions",
                dependencies=("realm",),
                generator_role="geography_architect",
                target_count=2,
            ),
        ),
    )


def test_completed_generation_publishes_one_immutable_revision_and_release() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            work.world_scenarios.create_world(
                context,
                world_id="world:publication",
                title="Publication World",
                source_mode="ai",
                metadata={"starting_location": "location:harbor"},
            )
            work.commit()

        started = start_world_generation(
            world_id="world:publication",
            draft_revision=1,
            graph=_graph(),
            generation_context={
                "genre": "classic_fantasy",
                "tone": "mythic",
                "starting_location": "location:harbor",
            },
            topic_directives={},
            entity_manifest_hash="sha256:" + "a" * 64,
            settings=WorldTopicGenerationSettings(
                generator_version="deterministic-v1",
                prompt_version="publication-test-v1",
                provider_route="deterministic",
                model="deterministic",
                seed=23,
            ),
            database=database,
        )
        generator = ReferenceSafeWorldForgeGenerator(
            DeterministicWorldForgeGenerator()
        )

        first = run_world_generation_worker_once(
            database=database,
            generator=generator,
            worker_id="world-publication:test",
        )
        second = run_world_generation_worker_once(
            database=database,
            generator=generator,
            worker_id="world-publication:test",
        )

        assert first is not None and first["ok"] is True
        assert second is not None and second["ok"] is True
        assert second["run"]["status"] == "review"

        published = publish_world_generation(started["run_id"], database=database)
        repeated = publish_world_generation(started["run_id"], database=database)

        assert published["ok"] is True
        assert published["status"] == "ready"
        assert published["reused"] is False
        assert published["publication"]["world_revision"] == 1
        assert published["publication"]["world_release"] == 1
        assert published["publication"]["world_revision_hash"].startswith("sha256:")
        assert published["publication"]["world_release_hash"].startswith("sha256:")
        assert repeated["reused"] is True
        assert repeated["publication"] == published["publication"]

        with unit_of_work(database) as work:
            revision = work.world_scenarios.get_world_revision(
                context,
                "world:publication",
                1,
            )
            release = work.world_scenarios.get_world_release(
                context,
                "world:publication",
                1,
                1,
            )
            run = work.world_generation.get(context, started["run_id"])
            work.rollback()

        assert revision is not None
        assert release is not None
        assert run is not None and run["status"] == "ready"
        assert revision["content_hash"] == published["publication"]["world_revision_hash"]
        assert release["release_hash"] == published["publication"]["world_release_hash"]
    finally:
        database.close()
