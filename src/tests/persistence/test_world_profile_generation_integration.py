from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.session.genesis.world_forge_profile_generation import (
    HeuristicWorldLocalProfileGenerator,
)
from app.rpg.worlds.contracts import WorldProjectCreate
from app.rpg.worlds.generation_worker import run_world_generation_worker_once
from app.rpg.worlds.postgres_service import create_world_project
from app.rpg.worlds.profile_generation_jobs import WORLD_PROFILE_JOB_TYPE

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
            application_name="omnix-world-profile-generation",
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


def test_unknown_world_profile_is_generated_and_pinned_before_lore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _database()
    try:
        _reset(database)
        monkeypatch.setenv("RPG_TEST_MODE", "deterministic")
        monkeypatch.setattr(
            "app.rpg.worlds.postgres_service.kick_world_generation_worker",
            lambda **_kwargs: False,
        )

        created = create_world_project(
            WorldProjectCreate(
                world_id="world:dream-ecology",
                title="The Migrating Dream",
                description="A surreal ecology where settlements migrate between dreams.",
                source_mode="ai",
                genre="migrating dream ecology",
                tone="surreal political mystery",
                seed=23,
                metadata={"campaign_mode": "persistent_living_world"},
            ),
            database=database,
        )
        initial_binding = created["metadata"]["genre_profile_binding"]
        assert initial_binding["status"] == "generating"
        assert initial_binding["profile_hash"] == ""

        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            jobs = [
                job
                for job in work.jobs.list_jobs(context, limit=20)
                if job["job_type"] == WORLD_PROFILE_JOB_TYPE
            ]
            work.rollback()
        assert len(jobs) == 1
        assert jobs[0]["status"] == "queued"

        completed = run_world_generation_worker_once(
            database=database,
            worker_id="world-profile-worker:test",
            profile_generator=HeuristicWorldLocalProfileGenerator(),
        )
        assert completed is not None
        assert completed["ok"] is True
        assert completed["status"] == "completed"

        with unit_of_work(database) as work:
            world = work.world_scenarios.get_world(context, "world:dream-ecology")
            job = work.jobs.get_job(context, jobs[0]["id"])
            runs = work.world_library.list_generation_runs(
                context,
                world_id="world:dream-ecology",
            )
            work.rollback()
        assert world is not None
        binding = world["metadata"]["genre_profile_binding"]
        assert binding["status"] == "ready"
        assert binding["source"] == "generated_world_local"
        assert binding["profile_id"] == "world_local:migrating_dream_ecology"
        assert binding["profile_hash"].startswith("sha256:")
        assert binding["profile"]["content_hash"] == binding["profile_hash"]
        assert "genre_elements" in {
            domain["domain_id"] for domain in binding["profile"]["domains"]
        }
        assert job is not None and job["status"] == "completed"
        assert runs == []
    finally:
        database.close()
