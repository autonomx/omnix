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
from app.rpg.worlds.generation_coordinator import (
    reconcile_world_generation,
    start_world_generation,
)
from app.rpg.worlds.generation_jobs import (
    WORLD_TOPIC_JOB_TYPE,
    WorldTopicGenerationSettings,
)
from app.rpg.worlds.generation_worker import run_world_generation_worker_once

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
            application_name="omnix-rpg-world-generation-dag",
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
        graph_version="world-generation-test-v1",
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


def test_world_topic_jobs_resume_from_persisted_completed_topics() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            work.world_scenarios.create_world(
                context,
                world_id="world:durable",
                title="Durable World",
                source_mode="ai",
            )
            work.commit()

        settings = WorldTopicGenerationSettings(
            generator_version="deterministic-v1",
            prompt_version="test-prompt-v1",
            provider_route="deterministic",
            model="deterministic",
            seed=17,
        )
        started = start_world_generation(
            world_id="world:durable",
            draft_revision=1,
            graph=_graph(),
            generation_context={"genre": "fantasy", "tone": "mythic"},
            topic_directives={"regions": {"direction": "coastal regions"}},
            entity_manifest_hash="sha256:" + "e" * 64,
            settings=settings,
            database=database,
        )
        generator = ReferenceSafeWorldForgeGenerator(
            DeterministicWorldForgeGenerator()
        )

        assert started["status"] == "running"
        assert started["progress"]["active_topic_ids"] == ["realm"]

        first = run_world_generation_worker_once(
            database=database,
            generator=generator,
            worker_id="world-worker:test",
        )
        assert first is not None and first["ok"] is True
        assert first["topic_id"] == "realm"
        assert first["run"]["progress"]["active_topic_ids"] == ["regions"]

        resumed = reconcile_world_generation(started["run_id"], database=database)
        assert resumed["progress"]["completed_topics"] == 1
        assert resumed["progress"]["active_topic_ids"] == ["regions"]

        second = run_world_generation_worker_once(
            database=database,
            generator=generator,
            worker_id="world-worker:test",
        )
        assert second is not None and second["ok"] is True
        assert second["topic_id"] == "regions"
        assert second["run"]["status"] == "review"
        assert second["run"]["progress"]["generation_complete"] is True

        idle = run_world_generation_worker_once(
            database=database,
            generator=generator,
            worker_id="world-worker:test",
        )
        assert idle is None

        final = reconcile_world_generation(started["run_id"], database=database)
        with unit_of_work(database) as work:
            jobs = [
                job
                for job in work.jobs.list_jobs(context, limit=100)
                if job["job_type"] == WORLD_TOPIC_JOB_TYPE
            ]
            topics = work.world_generation.list_topics(
                context,
                world_id="world:durable",
                draft_revision=1,
            )
            work.rollback()
        assert final["status"] == "review"
        assert len(jobs) == 2
        assert {job["status"] for job in jobs} == {"completed"}
        assert [row["topic_id"] for row in topics] == ["realm", "regions"]
        assert all(row["content_hash"].startswith("sha256:") for row in topics)
        assert all(
            row["provenance"]["generation_fingerprint"].startswith("sha256:")
            for row in topics
        )
    finally:
        database.close()
